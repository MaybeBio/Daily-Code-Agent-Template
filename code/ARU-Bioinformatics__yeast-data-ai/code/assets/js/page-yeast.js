/* =====================================================================
   "Yeast, data and AI" – page set-up: the notebook, the AI assistant,
   the data explorer and the 3D viewer (AlphaFold models).
   ===================================================================== */
(function () {
  'use strict';
  const MG = window.MG;
  const { h, esc, bus, toast } = MG;
  MG.app = MG.app || {};
  MG.checks = MG.checks || {};
  MG.actions = MG.actions || {};
  const CFG = MG.config;

  const DICTIONARY = [
    ['orf', 'systematic gene name (e.g. YFL039C = the 39th gene on the left arm of chromosome VI, Crick strand)'],
    ['gene', 'standard gene name (e.g. ACT1); the ORF name if the gene has none'],
    ['essential', '1 = the deletion mutant cannot grow (inviable) in the S288C yeast deletion collection; 0 = it grows (viable). This is what we try to predict.'],
    ['protein_length', 'length of the protein in amino acids'],
    ['gc_content', 'percentage of G and C in the coding sequence'],
    ['codon_bias', 'codon adaptation index, 0–1: how much the gene uses the codons favoured in highly expressed (ribosomal protein) genes'],
    ['protein_abundance', 'protein molecules per million protein molecules in the cell (ppm; PaxDb integrated dataset)'],
    ['interaction_partners', 'number of different proteins it has been found to bind physically (BioGRID)'],
    ['transmembrane_helices', 'number of transmembrane helices (UniProt)'],
    ['human_homolog', '1 = a similar human protein exists (DIAMOND search of the human proteome, E ≤ 1e-10)'],
    ['paralog_identity', '% amino-acid identity to the most similar other yeast protein (0 = no paralogue found)'],
    ['plddt', 'AlphaFold average confidence for the predicted structure, 0–100'],
    ['disorder', 'fraction of residues with AlphaFold confidence (pLDDT) below 50 – likely intrinsically disordered'],
    ['conditional_mutant_phenotypes', 'number of phenotypes recorded in SGD for conditional or knock-down mutants of the gene (e.g. temperature-sensitive alleles, repressible promoters)'],
    ['location', 'main cellular compartment: the one with the most curated Gene Ontology annotations in SGD (Unknown = no location recorded)'],
    ['chromosome', 'chromosome number (1–16)'],
    ['uniprot', 'UniProt accession of the protein'],
    ['alphafold_id', 'AlphaFold database model identifier'],
    ['description', 'one-line description of the gene from SGD']
  ];
  MG.DICTIONARY = DICTIONARY;

  const STARTER = [
    {
      tag: 'load',
      source: "# Load the yeast gene table: one row per gene\nimport pandas as pd\n\ndf = pd.read_csv('data/yeast_genes.csv')\ndf.head()"
    },
    { tag: 'shape', source: '# How big is the table? (rows, columns)\ndf.shape' },
    { tag: 'count', source: "# How many genes are essential (1) and not essential (0)?\ndf['essential'].value_counts()" },
    { tag: null, source: '' }
  ];

  const page = (MG.page = MG.page || {});
  page.firstBench = 'notebook';

  page.init = function () {
    MG.app.nb = new MG.Notebook(document.getElementById('nbRoot'), {
      fileStem: 'yeast-essential-genes',
      starter: STARTER,
      kernel: {
        workerUrl: 'assets/js/py-worker.js',
        // absolute URL: the worker lives in assets/js/, so a relative path would resolve from there
        indexURL: new URL(CFG.pyodideBase || 'https://cdn.jsdelivr.net/pyodide/v0.29.5/full/', location.href).href,
        preload: ['numpy', 'pandas', 'matplotlib'],
        background: ['scikit-learn', 'scipy'],
        wheels: { seaborn: new URL('assets/vendor/wheels/seaborn-0.13.2-py3-none-any.whl', location.href).href },
        files: [
          { path: 'data/yeast_genes.csv', url: new URL('data/yeast_genes.csv', location.href).href },
          { path: 'data/yeast_esm2.csv', url: new URL('data/yeast_esm2.csv', location.href).href }
        ]
      }
    });
    MG.app.ai = new MG.Assistant(document.getElementById('aiRoot'), { notebook: MG.app.nb, script: [], dictionary: DICTIONARY });
    MG.fetchJSON('data/assistant.json')
      .then((s) => {
        MG.app.ai.script = s;
        MG.app.ai.renderSuggestions();
      })
      .catch((e) => console.error('assistant script', e));
  };

  page.lazy = {
    data: (pane) => (MG.app.dx = new MG.DataExplorer(pane.querySelector('#dxRoot'), { url: 'data/yeast_genes.csv', dictionary: DICTIONARY })),
    viewer: (pane) => MG.app.createViewer(pane.querySelector('#viewerRoot'))
  };

  /* ------------------------------------------------------------------
     ▶ buttons in the instructions
     data-nb="code"      put the code in a new notebook cell
     data-nb-run="code"  … and run it
     data-ai="prompt"    ask the assistant this prompt
     data-af="P60010"    show the AlphaFold model of a UniProt accession
     ------------------------------------------------------------------ */
  MG.actions.nb = async (code) => {
    MG.app.showWorkbench('notebook');
    await MG.app.nb.insertCode(code);
  };
  MG.actions.nbRun = async (code) => {
    MG.app.showWorkbench('notebook');
    await MG.app.nb.insertCode(code, { run: true });
  };
  MG.actions.ai = async (prompt) => {
    MG.app.showWorkbench('assistant');
    const A = MG.app.ai;
    const e = A.script.find((x) => x.id === prompt) || null;
    await A.send(e ? e.prompt : prompt, e);
  };
  MG.actions.af = async (acc) => {
    MG.app.showWorkbench('viewer');
    const tryRun = async () => {
      if (!MG.commands || !MG.app.viewer) return false;
      await MG.commands.run(`load af ${acc}`, { prefix: '▶ ' });
      return true;
    };
    for (let i = 0; i < 40; i++) {
      if (await tryRun()) return;
      await new Promise((r) => setTimeout(r, 150));
    }
    toast('The 3D viewer is not ready yet – try again in a moment.', 'warn');
  };
  /* state checks for tasks (data-check="name:arg"), so a step also ticks when it was
     done before the student opened its chapter */
  const okRuns = [];
  bus.on('nb:run', (d) => {
    if (d && d.ok) okRuns.push({ tag: d.tag || null });
  });
  MG.checks.kernelReady = () => !!(MG.app.nb && MG.app.nb.kernel && MG.app.nb.kernel.state === 'ready');
  MG.checks.ran = (type, d, tag) => okRuns.some((r) => r.tag === tag);

  /* data-download-notebook: save the notebook as .ipynb (opens in Jupyter, Colab, VS Code) */
  MG.actions.downloadNotebook = async () => {
    if (MG.app.nb) MG.app.nb.downloadIpynb();
  };

  /* help */
  page.help = function () {
    MG.modal(
      'How this page works',
      `<ul>
<li><b>Instructions</b> are on the left, the <b>workbench</b> on the right: Notebook, AI assistant, Data and 3D viewer. Drag the divider to resize.</li>
<li><b>Notebook</b>: real Python running in your browser. Run a cell with <b>▶</b> or <kbd>Shift</kbd>+<kbd>Enter</kbd>. Variables are remembered between cells until you press <b>Restart</b>. Your cells are saved in this browser; download the notebook (↓) to keep it.</li>
<li><b>AI assistant</b>: ask it for code, explanations or help with errors. In <b>guided mode</b> its answers were prepared in advance – some contain deliberate mistakes. <b>Copy prompt</b> gives you a ready-made prompt for any AI tool you have access to.</li>
<li><b>▶ buttons</b> in the instructions put code into the notebook or ask the assistant for you.</li>
<li>Tasks tick themselves when you do them; answers are saved in this browser. <b>My answers</b> downloads them.</li>
</ul><p class="muted small">Python ${esc((MG.app.nb && MG.app.nb.kernel.versions && MG.app.nb.kernel.versions.python) || '')} runs in your browser with Pyodide (CPython compiled to WebAssembly). Nothing you type is uploaded – except, if you connect a live AI model (⚙ in the assistant), your messages, your notebook code and, when you ask about a cell, the start of its output.</p>`
    );
  };
})();
