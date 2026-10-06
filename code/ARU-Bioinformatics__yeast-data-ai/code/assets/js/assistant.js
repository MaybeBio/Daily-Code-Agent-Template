/* =====================================================================
   The AI coding assistant.
   - Guided mode (default): answers to the practical's prompts were
     generated in advance by an AI model and checked by the authors; some
     keep the kinds of mistake AI assistants really make, on purpose.
     Other questions get simple rule-based help, clearly labelled.
   - Live mode: a real model (Google Gemini, Anthropic Claude, or any
     OpenAI-compatible service) called directly from the browser with a key
     the user enters. Gemini is offered first: its API has a free tier.
   - "Copy prompt": a ready-made prompt for any AI tool the student has.
   ===================================================================== */
(function () {
  'use strict';
  const MG = window.MG;
  const { h, esc, bus, toast, store } = MG;

  /* ------------------------------------------------------------------
     tiny markdown renderer (paragraphs, lists, headings, code, links)
     ------------------------------------------------------------------ */
  function inline(s) {
    // code spans first (kept aside so that * inside code is not read as emphasis)
    const codes = [];
    let t = esc(s).replace(/`([^`]+)`/g, (m, c) => {
      codes.push(c);
      return '\u0000' + (codes.length - 1) + '\u0000';
    });
    t = t.replace(/(^|[^\w*])\*\*((?:[^*]|\*(?!\*))+?)\*\*(?![\w*])/g, '$1<b>$2</b>');
    t = t.replace(/(^|[^*\w])\*([^*\s](?:[^*]*[^*\s])?)\*(?![\w*])/g, '$1<i>$2</i>');
    t = t.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    return t.replace(/\u0000(\d+)\u0000/g, (m, k) => '<code>' + codes[+k] + '</code>');
  }
  function renderMarkdown(md) {
    const out = [];
    const lines = String(md || '').replace(/\r/g, '').split('\n');
    let i = 0;
    let list = null;
    const closeList = () => {
      if (list) {
        out.push({ html: `<${list.type}>${list.items.map((x) => `<li>${inline(x)}</li>`).join('')}</${list.type}>` });
        list = null;
      }
    };
    let para = [];
    const closePara = () => {
      if (para.length) {
        out.push({ html: `<p>${inline(para.join(' '))}</p>` });
        para = [];
      }
    };
    while (i < lines.length) {
      const L = lines[i];
      const fence = /^```\s*([\w+-]*)\s*$/.exec(L);
      if (fence) {
        closePara();
        closeList();
        const code = [];
        i++;
        while (i < lines.length && !/^```\s*$/.test(lines[i])) code.push(lines[i++]);
        i++;
        out.push({ code: code.join('\n'), lang: fence[1] || 'python' });
        continue;
      }
      const hd = /^(#{1,4})\s+(.*)$/.exec(L);
      const ul = /^\s*[-*]\s+(.*)$/.exec(L);
      const ol = /^\s*\d+[.)]\s+(.*)$/.exec(L);
      if (hd) {
        closePara();
        closeList();
        out.push({ html: `<h5>${inline(hd[2])}</h5>` });
      } else if (ul || ol) {
        closePara();
        const type = ul ? 'ul' : 'ol';
        if (!list || list.type !== type) {
          closeList();
          list = { type, items: [] };
        }
        list.items.push((ul || ol)[1]);
      } else if (!L.trim()) {
        closePara();
        closeList();
      } else if (list && /^\s{2,}\S/.test(L)) {
        list.items[list.items.length - 1] += ' ' + L.trim();
      } else {
        closeList();
        para.push(L.trim());
      }
      i++;
    }
    closePara();
    closeList();
    return out;
  }

  /* ------------------------------------------------------------------
     rule-based help (guided mode, questions without a prepared answer)
     ------------------------------------------------------------------ */
  const API_NOTES = [
    [/pd\.read_csv\(/, '`pd.read_csv(...)` reads a CSV file into a **DataFrame** – a table with named columns.'],
    [/\.merge\(/, '`.merge(...)` joins two tables on a shared column. Check the number of rows before and after – rows without a match are dropped by an inner join.'],
    [/\.head\(/, '`.head()` shows the first rows of a table.'],
    [/\.shape\b/, '`.shape` gives (number of rows, number of columns).'],
    [/\.describe\(/, '`.describe()` summarises each numeric column (count, mean, quartiles).'],
    [/\.value_counts\(/, '`.value_counts()` counts how often each distinct value occurs.'],
    [/\.groupby\(/, '`.groupby(...)` splits the rows into groups (for example essential and non-essential genes) so a summary can be calculated for each group.'],
    [/\.median\(/, '`.median()` is the middle value – robust to extreme values, unlike the mean.'],
    [/\.mean\(/, '`.mean()` is the average. For a 0/1 column such as `essential` it is the *proportion* of 1s.'],
    [/\.isna\(\)|\.isnull\(\)/, '`.isna()` finds missing values (NaN).'],
    [/\.dropna\(/, '`.dropna()` removes rows with missing values – check how many rows you lose.'],
    [/\.fillna\(/, '`.fillna(...)` replaces missing values. Think about what the filled value means: 0 is not the same as “unknown”.'],
    [/\.sort_values\(/, '`.sort_values(...)` sorts the rows by a column.'],
    [/np\.log10\(|np\.log\(|yscale\(['"]log/, 'A **log scale** spreads out values that span several orders of magnitude, such as protein abundance.'],
    [/\.corr\(|spearmanr|pearsonr/, 'A **correlation** measures how two variables vary together (Spearman uses ranks, so it is robust to skewed data).'],
    [/plt\.hist\(|\.hist\(/, 'A **histogram** shows the distribution of one variable.'],
    [/boxplot\(/, 'A **box plot** shows the median (line), the middle 50% (box) and the spread of each group.'],
    [/plt\.scatter\(|\.scatter\(/, 'A **scatter plot** shows one variable against another, one dot per gene.'],
    [/plt\.bar\(|\.plot\.bar|barh\(/, 'A **bar chart** – check that each bar’s label matches its value.'],
    [/xlabel|ylabel|set_title|plt\.title/, 'Axis labels and titles make the plot readable – always say what and in which units.'],
    [/ttest_ind\(/, '`ttest_ind` is a t-test comparing two means; it assumes roughly normal data.'],
    [/mannwhitneyu\(/, '`mannwhitneyu` compares two groups using ranks – suitable for skewed data.'],
    [/train_test_split\(/, '`train_test_split` keeps some genes aside as a **test set**, so the model is judged on genes it has never seen.'],
    [/LogisticRegression\(/, '**Logistic regression** combines the features in a weighted sum to give a probability of being essential.'],
    [/RandomForestClassifier\(/, 'A **random forest** is many decision trees voting together; it can capture non-linear patterns.'],
    [/StandardScaler\(/, '`StandardScaler` puts features on the same scale (mean 0, SD 1) – important for logistic regression.'],
    [/SimpleImputer\(/, '`SimpleImputer` fills in missing values (for example with the median) inside the model pipeline.'],
    [/make_pipeline\(|Pipeline\(/, 'A **pipeline** chains the steps (fill gaps → scale → model) so that they are learned from the training data only.'],
    [/\.fit\(/, '`.fit(X, y)` trains the model on the training data.'],
    [/predict_proba\(/, '`predict_proba` gives the predicted probability of each class; column 1 is the probability of being essential.'],
    [/\.predict\(/, '`.predict` gives yes/no predictions using a 0.5 probability threshold.'],
    [/roc_auc_score|roc_curve|'roc_auc'/, 'The **ROC AUC** is the chance that a randomly chosen essential gene is scored higher than a randomly chosen non-essential one (0.5 = guessing, 1 = perfect).'],
    [/accuracy_score/, '**Accuracy** is the fraction of predictions that are right. With 81% non-essential genes, always guessing “non-essential” already gives 81%.'],
    [/confusion_matrix/, 'A **confusion matrix** counts true/false positives and negatives.'],
    [/cross_val_score|cross_val_predict|StratifiedKFold/, '**Cross-validation** trains and tests the model several times on different splits, giving a more reliable estimate.'],
    [/feature_importances_|permutation_importance/, '**Feature importance** shows which features the model relies on most – a good way to spot suspicious features.'],
    [/PCA\(/, '**PCA** squeezes many numbers per gene into a few new axes that keep as much of the variation as possible, so the data can be drawn in 2D.'],
    [/cosine_similarity/, '**Cosine similarity** compares two embedding vectors: 1 = pointing the same way (very similar), 0 = unrelated.'],
    [/^\s*for\s.+:/m, 'A `for` loop repeats the indented lines once for each item.'],
    [/^\s*def\s/m, '`def` defines a function you can reuse.'],
    [/^\s*import\s|^\s*from\s.+\simport\s/m, '`import` lines load packages (pandas for tables, matplotlib for plots, scikit-learn for machine learning).']
  ];
  const ERROR_NOTES = {
    NameError: 'Python does not know that name. Either it is misspelt, or it was created in a cell that has not been run in this session (after a restart, run the cells again from the top).',
    KeyError: 'A column (or dictionary key) with that exact name does not exist. Names are case-sensitive – check `df.columns`.',
    AttributeError: 'The object does not have that attribute or method – often a typo, or calling a DataFrame method on something else (such as a NumPy array).',
    TypeError: 'A function received the wrong kind of input (for example text where a number was needed, or the wrong number of arguments).',
    ValueError: 'The input had the right type but an unsuitable value – for example text in a numeric column, missing values (NaN) given to a model, or arrays of different lengths.',
    SyntaxError: 'Python could not read the code: look for a missing bracket, quote, comma or colon on the line shown (or just above it).',
    IndentationError: 'Python uses indentation to group lines. Check that the lines inside `for`, `if` or `def` are indented consistently (4 spaces).',
    ModuleNotFoundError: 'That package is not available in this in-browser Python. Available: pandas, numpy, scipy, scikit-learn, matplotlib, statsmodels (and seaborn, installed on demand).',
    ZeroDivisionError: 'Something was divided by zero – check the denominator (for example an empty group).',
    IndexError: 'An index is out of range – you asked for an element that does not exist.',
    FileNotFoundError: 'The file path is wrong. The data files are in the `data/` folder, e.g. `data/yeast_genes.csv`.'
  };

  function ruleExplain(code) {
    const found = API_NOTES.filter(([re]) => re.test(code)).map(([, t]) => '- ' + t);
    if (!found.length) return 'I could not match this code to anything in my guide. Try the **Copy prompt** button to ask an AI tool you have access to, or connect a live model (⚙).';
    return `Here is what the main parts of this cell do:\n\n${found.slice(0, 9).join('\n')}\n\n*Guided mode explains code with a fixed set of notes, not a live AI. For a line-by-line explanation, connect a live model (⚙) or use **Copy prompt** with your own AI tool.*`;
  }
  function ruleFix(cell) {
    const e = cell.error || {};
    const lines = [];
    lines.push(`**${e.ename || 'Error'}**: ${e.evalue || ''}`.trim());
    lines.push('');
    lines.push(ERROR_NOTES[e.ename] || 'Read the last line of the error first: it names the problem. The line number points to where Python noticed it.');
    if (e.hints && e.hints.length) {
      lines.push('');
      e.hints.forEach((t) => lines.push('- ' + t));
    }
    const ln = /Cell line (\d+)/.exec(e.traceback || '');
    if (ln) {
      const src = cell.code.split('\n')[+ln[1] - 1];
      if (src) {
        lines.push('');
        lines.push(`The problem was noticed on line ${ln[1]}:`);
        lines.push('');
        lines.push('```text');
        lines.push(src);
        lines.push('```');
      }
    }
    lines.push('');
    lines.push('*This is guided help from a set of rules, not a live AI. If you are stuck, use **Copy prompt** to ask an AI tool you have access to, or connect a live model (⚙).*');
    return lines.join('\n');
  }

  /* ------------------------------------------------------------------
     matching free text to prepared prompts
     ------------------------------------------------------------------ */
  const STOP = new Set('a an the of to in on for and or with by is are be it this that these those how what which do does can could would should i me my we our you your please make show give using use from as at into than then there their its about all any some show also just like get plot plots'.split(' '));
  function tokens(s) {
    return String(s || '')
      .toLowerCase()
      .replace(/[^a-z0-9_%\s-]/g, ' ')
      .split(/\s+/)
      .map((w) => w.replace(/(ies)$/, 'y').replace(/([^s])s$/, '$1'))
      .filter((w) => w && !STOP.has(w));
  }
  function score(query, entry) {
    // some prepared answers only fit questions that name a particular thing (e.g. abundance)
    if (entry.requires && !new RegExp(entry.requires, 'i').test(query)) return 0;
    // … and some do not fit questions that name something else (e.g. another feature)
    if (entry.excludes && new RegExp(entry.excludes, 'i').test(query)) return 0;
    const q = new Set(tokens(query));
    if (!q.size) return 0;
    const p = new Set(tokens(entry.prompt + ' ' + (entry.alt || []).join(' ')));
    let hit = 0;
    q.forEach((w) => p.has(w) && hit++);
    let kw = 0;
    (entry.keywords || []).forEach((k) => {
      if (new RegExp(k, 'i').test(query)) kw++;
    });
    const need = entry.keywords && entry.keywords.length ? kw / entry.keywords.length : 0;
    return 0.55 * (hit / Math.max(q.size, 3)) + 0.45 * need;
  }

  /* ------------------------------------------------------------------
     the assistant panel
     ------------------------------------------------------------------ */
  const CFG = MG.config || {};
  const LIVE_DEFAULTS = {
    provider: CFG.liveProvider || 'gemini',
    model: CFG.anthropicModel || 'claude-sonnet-5-5',
    geminiModel: CFG.geminiModel || 'gemini-3.8-flash',
    baseURL: 'https://api.openai.com/v1',
    openaiModel: ''
  };
  /* the model of each service; an empty model in the saved settings means the site's default
     from config.js, so a model changed there (e.g. when one is retired) reaches every student
     who has not chosen a model of their own */
  const geminiModelOf = (s) => (s.geminiModel || LIVE_DEFAULTS.geminiModel).trim().replace(/^models\//, '');
  const anthropicModelOf = (s) => (s.model || LIVE_DEFAULTS.model).trim();
  const modelOf = (s) => (s.provider === 'gemini' ? geminiModelOf(s) : s.provider === 'anthropic' ? anthropicModelOf(s) : s.openaiModel || 'model');
  /** Gemini and Anthropic always need a key; an OpenAI-compatible server (e.g. a local one) may not */
  const needsKey = (s) => s.provider !== 'openai';
  /* A model can be "experiencing high demand" (HTTP 503), and each Gemini model has its own
     free-tier limits (HTTP 429). Live mode then asks these models in turn; the answer says which
     model replied. */
  const GEMINI_FALLBACKS = (Array.isArray(CFG.geminiFallbackModels) ? CFG.geminiFallbackModels : ['gemini-3.6-flash', 'gemini-3.5-flash-lite'])
    .map((m) => String(m).trim().replace(/^models\//, ''))
    .filter(Boolean);
  const BUSY = [500, 502, 503, 504, 529];
  const skipWord = (status) => (status === 404 ? 'not found' : status === 429 ? 'over its limit' : 'busy');
  /** a pause that the Stop button can cut short */
  const pause = (ms, signal) =>
    new Promise((resolve, reject) => {
      const t = setTimeout(resolve, ms);
      const stop = () => {
        clearTimeout(t);
        reject(new DOMException('Stopped', 'AbortError'));
      };
      if (signal && signal.aborted) stop();
      else if (signal) signal.addEventListener('abort', stop, { once: true });
    });

  class Assistant {
    constructor(root, opts) {
      this.root = root;
      this.opts = opts;
      this.nb = opts.notebook;
      this.script = opts.script || [];
      this.msgs = [];
      this.busy = false;
      this.settings = Object.assign({}, LIVE_DEFAULTS, store.get('ai:settings', {}));
      this.mode = store.get('ai:mode', (MG.config && MG.config.assistantDefaultMode) || 'guided');
      try {
        this.key = window.sessionStorage.getItem('yeast-ai-key') || '';
      } catch (e) {
        this.key = '';
      }
      if (this.mode === 'live' && !this.key && needsKey(this.settings)) this.mode = 'guided';
      this._build();
      this.welcome();
      bus.on('nb:ask', (d) => this.askAboutCell(d));
      bus.on('app:chapter', () => this.renderSuggestions());
    }

    _build() {
      const R = this.root;
      R.classList.add('ai');
      this.modeEl = h('button.ai-mode', { type: 'button', title: 'Change how the assistant works' });
      this.modeEl.addEventListener('click', () => this.settingsDialog());
      const copyBtn = h('button.tbtn', { type: 'button', title: 'Copy a ready-made prompt (with your notebook code) to paste into any AI tool you have access to', html: MG.icon('copy') + '<span>Copy prompt</span>' });
      copyBtn.addEventListener('click', () => this.copyPrompt());
      const newBtn = h('button.tbtn', { type: 'button', title: 'Start a new conversation', html: MG.icon('reset') + '<span>New chat</span>' });
      newBtn.addEventListener('click', () => {
        this.msgs = [];
        this.thread.innerHTML = '';
        this.welcome();
      });
      const setBtn = h('button.tbtn', { type: 'button', title: 'Assistant settings (guided or live AI)', html: MG.icon('gear') });
      setBtn.addEventListener('click', () => this.settingsDialog());
      this.thread = h('div.ai-thread', { role: 'log', 'aria-live': 'polite' });
      this.sugg = h('div.ai-sugg');
      this.input = h('textarea.ai-input', { rows: 2, placeholder: 'Ask the assistant – e.g. “How do I plot protein length for essential and non-essential genes?”', 'aria-label': 'Message to the AI assistant' });
      this.sendBtn = h('button.btn.primary.ai-send', { type: 'button', title: 'Send (Enter)', html: MG.icon('send') + '<span>Send</span>' });
      // the Send button becomes Stop while a live model is answering
      this.sendBtn.addEventListener('click', () => (this._abort ? this._abort.abort() : this.send()));
      this.input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
          e.preventDefault();
          this.send();
        }
      });
      R.append(
        h('div.ai-bar', h('span.ai-title', { html: MG.icon('sparkle') + ' AI assistant' }), this.modeEl, h('span.grow'), copyBtn, newBtn, setBtn),
        this.thread,
        h('div.ai-foot', this.sugg, h('div.ai-inrow', this.input, this.sendBtn))
      );
      this.renderMode();
      this.renderSuggestions();
    }
    renderMode() {
      if (this.mode === 'live') {
        this.modeEl.innerHTML = `<span class="kdot ok"></span> Live · ${esc(modelOf(this.settings))}`;
        this.modeEl.classList.add('live');
      } else {
        this.modeEl.innerHTML = '<span class="kdot"></span> Guided mode';
        this.modeEl.classList.remove('live');
      }
    }
    welcome() {
      const live = this.mode === 'live';
      this.addBubble('assistant', live
        ? 'Hi! I am a live AI model connected to this notebook. I see the code in your cells and, when you ask about a cell, the start of its output or error message – not the data files. The ▶ buttons in the instructions still give the practical’s prepared answers. Ask me to write, explain or fix code – and always check what I give you.'
        : 'Hi! I am the practical’s AI coding assistant, in **guided mode**: my answers to the practical’s questions were written in advance by an AI model and checked – and, like real AI output, some of them contain mistakes for you to catch. Pick a suggestion below or type a question. Code I give you can go straight into the notebook with **Insert into notebook**.', { intro: true });
    }

    /* ---------------- suggestions ---------------- */
    currentChapter() {
      const ch = Array.from(document.querySelectorAll('.chapter')).find((c) => !c.hidden);
      return ch ? ch.id : '';
    }
    renderSuggestions() {
      const ch = this.currentChapter();
      const used = new Set(this.msgs.filter((m) => m.entry).map((m) => m.entry));
      let list = this.script.filter((e) => e.chapter === ch && !e.hidden && !used.has(e.id));
      const follow = this.msgs.length ? this.script.filter((e) => (this.lastEntry && (this.lastEntry.next || []).includes(e.id)) && !used.has(e.id)) : [];
      list = follow.concat(list.filter((e) => !follow.includes(e) && !e.followOnly)).slice(0, 4);
      this.sugg.innerHTML = '';
      if (!list.length) return;
      this.sugg.appendChild(h('span.muted.small', 'Try:'));
      list.forEach((e) => {
        const b = h('button.chip', { type: 'button', title: 'Ask this' }, e.prompt);
        b.addEventListener('click', () => {
          this.sugg.querySelectorAll('button.chip').forEach((x) => (x.disabled = true));
          this.send(e.prompt, e, 'chip');
        });
        this.sugg.appendChild(b);
      });
    }

    /* ---------------- messages ---------------- */
    addBubble(role, md, meta = {}) {
      const b = h('div.ai-msg.' + role + (meta.intro ? '.intro' : ''));
      if (role === 'user') b.appendChild(h('div.ai-body', md));
      else {
        const body = h('div.ai-body');
        this.fill(body, md);
        b.appendChild(body);
        if (meta.badge) b.appendChild(h('div.ai-badge', { html: meta.badge }));
      }
      this.thread.appendChild(b);
      this.thread.scrollTop = this.thread.scrollHeight;
      return b;
    }
    fill(body, md) {
      body.innerHTML = '';
      renderMarkdown(md).forEach((blk) => {
        if (blk.html) body.insertAdjacentHTML('beforeend', blk.html);
        else {
          const pre = h('pre.ai-code', h('code', blk.code));
          const acts = h('div.ai-code-acts');
          if (blk.lang === 'python' || blk.lang === 'py' || blk.lang === '') {
            const ins = h('button.btn.small.primary', { type: 'button', html: MG.icon('plus') + '<span>Insert into notebook</span>' });
            ins.addEventListener('click', () => this.insert(blk.code));
            const run = h('button.btn.small', { type: 'button', html: MG.icon('play') + '<span>Insert and run</span>' });
            run.addEventListener('click', () => this.insert(blk.code, true));
            acts.append(ins, run);
          }
          const cp = h('button.btn.small', { type: 'button', html: MG.icon('copy') + '<span>Copy</span>' });
          cp.addEventListener('click', async () => ((await MG.copyText(blk.code)) ? toast('Code copied.') : toast('Could not copy.', 'error')));
          acts.appendChild(cp);
          body.appendChild(h('div.ai-codebox', pre, acts));
        }
      });
    }
    insert(code, run) {
      if (MG.app.showWorkbench) MG.app.showWorkbench('notebook');
      this.nb.insertCode(code, { run });
      bus.emit('ai:insert', { run: !!run, code });
    }

    async send(text, entry, source) {
      const q = (text != null ? text : this.input.value).trim();
      if (!q) return;
      if (this.busy) {
        if (this._abort) {
          toast('The assistant is still answering – wait for it to finish, or press Stop.', 'warn');
          return;
        }
        // guided mode: finish the answer that is being "typed" at once, then carry on
        this._skip = true;
        for (let i = 0; i < 100 && this.busy; i++) await new Promise((r) => setTimeout(r, 40));
        if (this.busy) return;
      }
      if (text == null) this.input.value = '';
      this.addBubble('user', q);
      this.msgs.push({ role: 'user', content: q });
      // ▶ buttons and suggestions always give the practical's prepared answers (with their
      // planted mistakes), also in live mode; typed questions go to the live model
      const e = entry || (this.mode === 'live' ? null : this.match(q));
      bus.emit('ai:ask', { text: q, mode: this.mode, entry: e ? e.id : '', source: source || (text == null ? 'typed' : 'button') });
      if (e) return this.playRecorded(e);
      if (this.mode === 'live') return this.live(q);
      const reply = 'In **guided mode** I only have prepared answers for the practical’s questions (see the suggestions below), so I can’t answer that one properly.\n\n- Try one of the suggested prompts, or rephrase using the words in the instructions.\n- Use **Copy prompt** to ask any AI tool you have access to (the prompt includes a description of the data and your notebook code).\n- With an API key (Google Gemini has a free tier), switch to a **live** model with ⚙.';
      this.msgs.push({ role: 'assistant', content: reply });
      this.addBubble('assistant', reply, { badge: 'guided mode · no prepared answer' });
      this.renderSuggestions();
    }
    match(q) {
      const ch = this.currentChapter();
      let best = null, bs = 0;
      this.script.forEach((e) => {
        if (e.kind && e.kind !== 'prompt') return;
        const s = score(q, e) + (e.chapter === ch ? 0.08 : 0);
        if (s > bs) {
          bs = s;
          best = e;
        }
      });
      return bs >= 0.42 ? best : null;
    }
    async playRecorded(e) {
      this.busy = true;
      this._skip = false;
      this.lastEntry = e;
      const b = this.addBubble('assistant', '', {});
      const body = b.querySelector('.ai-body');
      body.innerHTML = '<span class="ai-typing"><i></i><i></i><i></i></span>';
      await new Promise((r) => setTimeout(r, 450 + Math.random() * 400));
      // reveal the prepared answer progressively, as a live model would (click it to skip)
      const full = e.response;
      const skip = () => (stop = true);
      let stop = false;
      b.addEventListener('click', skip, { once: true });
      const words = full.split(/(\s+)/);
      let shown = '';
      for (let i = 0; i < words.length && !stop && !this._skip; i += 6) {
        shown = words.slice(0, i + 6).join('');
        this.fill(body, shown + (i + 6 < words.length ? ' ▍' : ''));
        this.thread.scrollTop = this.thread.scrollHeight;
        await new Promise((r) => setTimeout(r, 18));
      }
      this.fill(body, full);
      b.appendChild(h('div.ai-badge', { html: this.mode === 'live' ? 'prepared answer from the practical (▶ buttons and suggestions)' : 'prepared answer · guided mode' }));
      this.msgs.push({ role: 'assistant', content: full, entry: e.id });
      this.thread.scrollTop = this.thread.scrollHeight;
      this.busy = false;
      bus.emit('ai:answer', { entry: e.id, mode: 'guided' });
      this.renderSuggestions();
    }

    /* asked from a notebook cell: explain / fix / improve */
    async askAboutCell(d) {
      if (MG.app.showWorkbench) MG.app.showWorkbench('assistant');
      if (this.busy) {
        if (this.mode === 'live') {
          toast('The assistant is still answering – wait for it to finish, or press Stop.', 'warn');
          return;
        }
        this._skip = true;
        for (let i = 0; i < 100 && this.busy; i++) await new Promise((r) => setTimeout(r, 40));
        if (this.busy) return;
      }
      const c = d.cell;
      const what = d.kind === 'fix' ? 'Explain this error and how to fix it.' : d.kind === 'improve' ? 'How could this code be improved or extended?' : 'Explain what this code does.';
      const shortCode = c.code.length > 400 ? c.code.slice(0, 400) + '\n…' : c.code;
      const userText = `${what}\n\n${shortCode}${d.kind === 'fix' && c.error ? `\n\n${c.error.ename}: ${c.error.evalue}` : ''}`;
      if (this.mode === 'live') {
        this.addBubble('user', userText);
        this.msgs.push({ role: 'user', content: userText });
        return this.live(userText, c, d.kind);
      }
      this.addBubble('user', userText);
      this.msgs.push({ role: 'user', content: userText });
      const tagged = c.tag && this.script.find((e) => e.id === `${d.kind}:${c.tag}`);
      if (tagged) return this.playRecorded(tagged);
      const reply = d.kind === 'fix' ? ruleFix(c) : d.kind === 'improve' ? 'In **guided mode** I can’t suggest improvements to your own code. Good questions to ask yourself: Is every step needed? Are the axes labelled? Are missing values handled? Would someone else understand it? – Or use **Copy prompt** / a live model (⚙) to get suggestions.' : ruleExplain(c.code);
      this.msgs.push({ role: 'assistant', content: reply });
      this.addBubble('assistant', reply, { badge: 'guided mode · rule-based help' });
      bus.emit('ai:answer', { entry: 'rule:' + d.kind, mode: 'guided' });
    }

    /* ---------------- live mode ---------------- */
    systemPrompt() {
      return [
        'You are an AI coding assistant embedded in a browser-based Python notebook used in a practical for MSc Molecular Genetics & Bioinformatics students.',
        'The practical asks: which yeast (Saccharomyces cerevisiae) genes are essential, and can machine learning predict it? Students are learning data science and how to use AI assistants critically.',
        '',
        'Environment: Python ' + ((this.nb.kernel.versions && this.nb.kernel.versions.python) || '3.13') + ' running in the browser with Pyodide. Available: pandas, numpy, scipy, scikit-learn, matplotlib, statsmodels; seaborn installs automatically when imported. No internet access from Python and no other packages. Plots appear when a cell finishes (or with plt.show()).',
        'Files: data/yeast_genes.csv (one row per gene) and data/yeast_esm2.csv (orf plus esm_1…esm_32: PCA-reduced ESM-2 protein language model embeddings). Students usually load the gene table as df = pd.read_csv("data/yeast_genes.csv").',
        'Columns of yeast_genes.csv:',
        (this.opts.dictionary || []).map((d) => `- ${d[0]}: ${d[1]}`).join('\n'),
        '',
        'How to answer: be brief and friendly; explain in plain language for biologists; put runnable code in ONE ```python block that works as a notebook cell (include the imports it needs and assume df exists if the student has loaded it); label plot axes with units; use random_state=0 where relevant; mention assumptions and how the student can check the result (e.g. compare with the numbers, look for data leakage, class imbalance). Do not claim results you have not seen. If you cite literature, say that the student should verify the reference. Help students learn rather than just giving answers to their practical questions.'
      ].join('\n');
    }
    contextFor(cell, kind) {
      let ctx = '';
      const code = this.nb.codeContext(4500);
      if (code) ctx += `Code currently in the student's notebook:\n\`\`\`python\n${code}\n\`\`\`\n\n`;
      if (cell) {
        ctx += `The student is asking about this cell:\n\`\`\`python\n${cell.code}\n\`\`\`\n`;
        if (cell.error) ctx += `It raised:\n\`\`\`text\n${(cell.error.traceback || cell.error.ename + ': ' + cell.error.evalue).slice(0, 2500)}\n\`\`\`\n`;
        else if (cell.output) ctx += `Its text output began:\n\`\`\`text\n${cell.output.slice(0, 1200)}\n\`\`\`\n`;
      }
      return ctx;
    }
    async live(q, cell, kind) {
      if (!this.key && needsKey(this.settings)) {
        this.addBubble('assistant', 'No API key is set for live mode. Open ⚙ to add one, or switch back to guided mode.', { badge: 'live mode' });
        return;
      }
      this.busy = true;
      this._abort = new AbortController();
      this.sendBtn.innerHTML = MG.icon('stop') + '<span>Stop</span>';
      this.sendBtn.title = 'Stop the answer';
      const b = this.addBubble('assistant', '');
      const body = b.querySelector('.ai-body');
      body.innerHTML = '<span class="ai-typing"><i></i><i></i><i></i></span>';
      // conversation: last turns; the newest user turn carries the notebook context
      const hist = this.msgs.slice(-12).map((m) => ({ role: m.role, content: m.content }));
      while (hist.length && hist[0].role !== 'user') hist.shift();
      if (hist.length) hist[hist.length - 1] = { role: 'user', content: this.contextFor(cell, kind) + 'Question: ' + hist[hist.length - 1].content };
      let text = '';
      const t0 = performance.now();
      try {
        const res = await this.stream(
          hist,
          (delta) => {
            text += delta;
            this.fill(body, text + ' ▍');
            this.thread.scrollTop = this.thread.scrollHeight;
          },
          this._abort.signal,
          null,
          (note) => {
            if (!text) body.innerHTML = `<div class="muted" style="font-size:0.85em;margin-bottom:0.35em">${esc(note)}</div><span class="ai-typing"><i></i><i></i><i></i></span>`;
          }
        );
        this.fill(body, text || '(no reply)');
        const via = res.skipped.length ? ` (${res.skipped.map((x) => x.model + ' ' + skipWord(x.status)).join(', ')})` : '';
        b.appendChild(h('div.ai-badge', { html: `live · ${esc(res.model + via)} · ${((performance.now() - t0) / 1000).toFixed(1)} s` }));
        this.msgs.push({ role: 'assistant', content: text });
        bus.emit('ai:answer', { entry: 'live', mode: 'live' });
      } catch (e) {
        if (e.name === 'AbortError') {
          this.fill(body, (text || '') + '\n\n*(stopped)*');
          if (text) this.msgs.push({ role: 'assistant', content: text });
        } else {
          this.fill(body, '**The AI service returned an error.**\n\n' + e.message);
          b.classList.add('err');
        }
      } finally {
        this.busy = false;
        this._abort = null;
        this.sendBtn.innerHTML = MG.icon('send') + '<span>Send</span>';
        this.sendBtn.title = 'Send (Enter)';
      }
    }
    /* Stream an answer from the chosen service. For Gemini, when a model is busy (HTTP 5xx), over
       its free-tier limit (429) or not found (404), the fallback models are asked in turn; the last
       model asked (for other services, the only one) gets a second try after a short pause if it is
       busy. Returns { model, skipped }: the model that answered and the ones that could not. */
    async stream(messages, onDelta, signal, cfg, onNote) {
      const s = (cfg && cfg.settings) || this.settings;
      const key = cfg ? cfg.key : this.key;
      const note = onNote || (() => {});
      // turns must alternate between user and assistant: join neighbours of the same role
      messages = messages.reduce((out, m) => {
        const last = out[out.length - 1];
        if (last && last.role === m.role) last.content += '\n\n' + m.content;
        else out.push({ role: m.role, content: m.content });
        return out;
      }, []);
      const gemini = s.provider === 'gemini';
      const chain = gemini ? [geminiModelOf(s)].concat(GEMINI_FALLBACKS.filter((m, i, a) => a.indexOf(m) === i && m !== geminiModelOf(s))) : [modelOf(s)];
      const skipped = [];
      let first = null;
      for (let i = 0; i < chain.length; i++) {
        for (let attempt = 1; ; attempt++) {
          let started = false;
          try {
            await this.streamOnce(s, key, chain[i], messages, (d) => {
              started = true;
              onDelta(d);
            }, signal);
            return { model: chain[i], skipped };
          } catch (e) {
            // only an HTTP error that came before any text is worth another try
            if (e.name === 'AbortError' || started || !e.status) throw e;
            const busy = BUSY.includes(e.status);
            const last = i === chain.length - 1;
            if (i === 0 && attempt === 1) first = e;
            // "high demand" usually lasts minutes: go straight to the next model …
            if (gemini && !last && (busy || e.status === 429 || e.status === 404)) {
              skipped.push({ model: chain[i], status: e.status });
              note(`${chain[i]} ${e.status === 404 ? 'was not found' : e.status === 429 ? 'is over its free-tier limit' : 'is busy'} – asking ${chain[i + 1]} instead…`);
              break;
            }
            // … and give the last one a second try after a short pause
            if (last && busy && attempt === 1) {
              note(`${chain[i]} is busy – trying again…`);
              await pause(1500 + Math.random() * 1500, signal);
              continue;
            }
            // nothing answered: report the chosen model's error, and what the others said
            if (i === 0) throw e;
            first.message += ` (Also tried: ${skipped.slice(1).map((x) => x.model + ' – HTTP ' + x.status).concat(chain[i] + ' – HTTP ' + e.status).join('; ')}.)`;
            throw first;
          }
        }
      }
    }
    /** one request: the answer is passed to onDelta as it arrives; HTTP errors carry .status */
    async streamOnce(s, key, model, messages, onDelta, signal) {
      let r;
      if (s.provider === 'anthropic') {
        r = await fetch('https://api.anthropic.com/v1/messages', {
          method: 'POST',
          headers: {
            'content-type': 'application/json',
            'x-api-key': key,
            'anthropic-version': '2023-06-01',
            'anthropic-dangerous-direct-browser-access': 'true'
          },
          body: JSON.stringify({ model: anthropicModelOf(s), max_tokens: 2000, system: this.systemPrompt(), messages, stream: true }),
          signal
        }).catch((e) => {
          if (e.name === 'AbortError') throw e;
          throw new Error('Could not reach the Anthropic API (' + e.message + '). Check the internet connection.');
        });
      } else if (s.provider === 'gemini') {
        // Google's Gemini API (generateContent, streamed as server-sent events); the whole conversation is sent each time
        r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:streamGenerateContent?alt=sse`, {
          method: 'POST',
          headers: { 'content-type': 'application/json', 'x-goog-api-key': key },
          body: JSON.stringify({
            system_instruction: { parts: [{ text: this.systemPrompt() }] },
            contents: messages.map((m) => ({ role: m.role === 'assistant' ? 'model' : 'user', parts: [{ text: m.content }] }))
          }),
          signal
        }).catch((e) => {
          if (e.name === 'AbortError') throw e;
          throw new Error('Could not reach the Gemini API (' + e.message + '). Check the internet connection.');
        });
      } else {
        const base = (s.baseURL || '').replace(/\/+$/, '');
        r = await fetch(base + '/chat/completions', {
          method: 'POST',
          headers: Object.assign({ 'content-type': 'application/json' }, key ? { authorization: 'Bearer ' + key } : {}),
          body: JSON.stringify({ model: s.openaiModel, stream: true, messages: [{ role: 'system', content: this.systemPrompt() }].concat(messages) }),
          signal
        }).catch((e) => {
          if (e.name === 'AbortError') throw e;
          throw new Error('Could not reach ' + base + ' (' + e.message + '). Check the address; the service must allow requests from web pages (CORS).');
        });
      }
      if (!r.ok) {
        let detail = '';
        let reason = '';
        try {
          const j = await r.json();
          detail = (j.error && (j.error.message || j.error.type)) || JSON.stringify(j).slice(0, 300);
          reason = (j.error && ((j.error.details || []).map((d) => d.reason).filter(Boolean)[0] || j.error.status)) || '';
        } catch (e) {
          detail = r.statusText;
        }
        const badKey = r.status === 401 || r.status === 403 || reason === 'API_KEY_INVALID';
        const gem = s.provider === 'gemini';
        const why = badKey
          ? 'The API key was not accepted.'
          : r.status === 404
            ? `The model name${gem ? ' (' + model + ')' : ''} may be wrong, or the model has been retired – check the model name in ⚙.`
            : r.status === 429
              ? gem
                ? 'Too many requests: the free tier allows only a few requests per minute and per day – wait a minute and try again.'
                : 'Too many requests or no credit left – try again in a minute.'
              : BUSY.includes(r.status)
                ? gem
                  ? `Google’s servers are busy for ${model} (“high demand”). This is on Google’s side, not a problem with your key: wait a minute and try again, or choose another model in ⚙.`
                  : 'The service is busy or had a temporary problem – try again in a minute.'
                : '';
        throw Object.assign(new Error(`HTTP ${r.status}. ${why} ${detail}`.trim()), { status: r.status });
      }
      const reader = r.body.getReader();
      const dec = new TextDecoder();
      let buf = '';
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let k;
        while ((k = buf.indexOf('\n')) >= 0) {
          const line = buf.slice(0, k).trim();
          buf = buf.slice(k + 1);
          if (!line.startsWith('data:')) continue;
          const data = line.slice(5).trim();
          if (!data || data === '[DONE]') continue;
          let j;
          try {
            j = JSON.parse(data);
          } catch (e) {
            continue;
          }
          if (s.provider === 'anthropic') {
            if (j.type === 'content_block_delta' && j.delta && j.delta.type === 'text_delta') onDelta(j.delta.text);
            else if (j.type === 'error') throw Object.assign(new Error((j.error && j.error.message) || 'stream error'), { status: j.error && j.error.type === 'overloaded_error' ? 529 : undefined });
          } else if (s.provider === 'gemini') {
            if (j.error) throw Object.assign(new Error(j.error.message || 'stream error'), { status: j.error.code });
            if (j.promptFeedback && j.promptFeedback.blockReason) throw new Error('Gemini did not answer (' + j.promptFeedback.blockReason + ').');
            const parts = (j.candidates && j.candidates[0] && j.candidates[0].content && j.candidates[0].content.parts) || [];
            parts.forEach((p) => {
              if (p.text && !p.thought) onDelta(p.text);
            });
          } else {
            const d = j.choices && j.choices[0] && j.choices[0].delta;
            if (d && d.content) onDelta(d.content);
          }
        }
      }
    }

    /* ---------------- copy prompt for another AI tool ---------------- */
    buildPrompt(question) {
      const q = question || this.input.value.trim() || '[write your question here]';
      return [
        'I am working in a Python notebook (pandas, numpy, scipy, scikit-learn, matplotlib; Python in the browser, no internet access) on yeast gene data.',
        'The table data/yeast_genes.csv has one row per Saccharomyces cerevisiae gene with these columns:',
        (this.opts.dictionary || []).map((d) => `- ${d[0]}: ${d[1]}`).join('\n'),
        '',
        'My notebook so far:',
        '```python',
        this.nb.codeContext(3500) || '# (empty)',
        '```',
        '',
        'My question: ' + q,
        '',
        'Please answer briefly, explain the code in plain language, and give one complete code cell I can run.'
      ].join('\n');
    }
    async copyPrompt() {
      const text = this.buildPrompt();
      const ok = await MG.copyText(text);
      const m = MG.modal(
        'A prompt for any AI tool',
        `<p class="small">${ok ? '<b>Copied to the clipboard.</b> ' : ''}Paste it into an AI tool you are allowed to use, then paste the code it gives you into a notebook cell – and check it. The prompt describes the data and contains your notebook code and the question in the assistant’s box (if you typed one). Read it: what does it tell the AI, and what does it leave out?</p><textarea class="prompt-text" readonly aria-label="Prompt">${esc(text)}</textarea><div class="prompt-actions"><button class="btn" data-x="copy" type="button">${MG.icon('copy')}<span>Copy</span></button><button class="btn primary" data-x="ok" type="button">Done</button></div>`
      );
      m.box.querySelector('[data-x="copy"]').addEventListener('click', async () => toast((await MG.copyText(text)) ? 'Prompt copied.' : 'Could not copy – select the text and copy it yourself.', null, 2500));
      m.box.querySelector('[data-x="ok"]').addEventListener('click', () => m.close());
      bus.emit('ai:copyprompt', {});
    }

    /* ---------------- settings ---------------- */
    settingsDialog() {
      const s = this.settings;
      let remembered = false;
      try {
        remembered = !!window.sessionStorage.getItem('yeast-ai-key');
      } catch (e) {
        remembered = false;
      }
      const html = `
<div class="ai-set">
  <label class="ai-opt"><input type="radio" name="aimode" value="guided" ${this.mode === 'guided' ? 'checked' : ''}> <span><b>Guided</b> – prepared answers for the practical (no account needed). Some contain deliberate mistakes to find.</span></label>
  <label class="ai-opt"><input type="radio" name="aimode" value="live" ${this.mode === 'live' ? 'checked' : ''}> <span><b>Live AI</b> – connect a real model with your own API key, or one provided by your lecturer.</span></label>
  <div class="ai-live-box">
    <label>Service <select data-k="provider"><option value="gemini" ${s.provider === 'gemini' ? 'selected' : ''}>Google Gemini (free tier available)</option><option value="anthropic" ${s.provider === 'anthropic' ? 'selected' : ''}>Anthropic (Claude)</option><option value="openai" ${s.provider === 'openai' ? 'selected' : ''}>OpenAI-compatible service</option></select></label>
    <label data-show="gemini">Model <input data-k="geminiModel" value="${esc(geminiModelOf(s))}" spellcheck="false"></label>
    <p data-show="gemini" class="muted small">Make a free key with a Google account at <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener">aistudio.google.com/apikey</a> (you must be 18 or over). On the free tier Google may use what you send to improve its products, and human reviewers may read it. The free tier allows only a few requests per minute and per day.</p>
    <label data-show="anthropic">Model <input data-k="model" value="${esc(anthropicModelOf(s))}" spellcheck="false"></label>
    <label data-show="openai">Base URL <input data-k="baseURL" value="${esc(s.baseURL)}" spellcheck="false"></label>
    <label data-show="openai">Model <input data-k="openaiModel" value="${esc(s.openaiModel)}" placeholder="the model name your service uses" spellcheck="false"></label>
    <label>API key <input data-k="key" type="password" value="${esc(this.key)}" autocomplete="off" spellcheck="false" placeholder="paste the key here"></label>
    <label class="ai-cb"><input type="checkbox" data-k="remember" ${remembered ? 'checked' : ''}> Remember the key until I close this browser tab</label>
    <p class="muted small">In live mode your messages, the code in your notebook and – when you ask about a cell – the start of its output or error message are sent from your browser straight to the service you choose (the data files are not). The key stays in this browser. The ▶ buttons in the instructions keep using the practical’s prepared answers. A local service (e.g. Ollama) may not need a key. Never paste personal or patient data into an AI tool.</p>
  </div>
  <div class="prompt-actions"><span class="ai-test-out muted small"></span><button class="btn" data-x="test" type="button">Test</button><button class="btn primary" data-x="save" type="button">Save</button></div>
</div>`;
      const m = MG.modal('AI assistant settings', html);
      const B = m.box;
      const val = (k) => B.querySelector(`[data-k="${k}"]`);
      const sync = () => {
        const live = B.querySelector('input[name="aimode"]:checked').value === 'live';
        B.querySelector('.ai-live-box').classList.toggle('off', !live);
        const p = val('provider').value;
        B.querySelectorAll('[data-show]').forEach((el) => (el.hidden = el.dataset.show !== p));
      };
      B.querySelectorAll('input[name="aimode"]').forEach((r) => r.addEventListener('change', sync));
      val('provider').addEventListener('change', sync);
      sync();
      // a model left at the site's default is saved as '' (= follow config.js)
      const own = (k, dflt) => {
        const v = val(k).value.trim().replace(/^models\//, '');
        return v && v !== dflt ? v : '';
      };
      const read = () => ({
        settings: { provider: val('provider').value, model: own('model', LIVE_DEFAULTS.model), geminiModel: own('geminiModel', LIVE_DEFAULTS.geminiModel), baseURL: val('baseURL').value.trim(), openaiModel: val('openaiModel').value.trim() },
        key: val('key').value.trim()
      });
      const collect = () => {
        const r = read();
        this.settings = r.settings;
        this.key = r.key;
        store.set('ai:settings', this.settings);
        try {
          if (val('remember').checked && this.key) window.sessionStorage.setItem('yeast-ai-key', this.key);
          else window.sessionStorage.removeItem('yeast-ai-key');
        } catch (e) {
          /* storage may be blocked */
        }
      };
      B.querySelector('[data-x="test"]').addEventListener('click', async () => {
        // test with what is in the form, without saving it
        const out = B.querySelector('.ai-test-out');
        out.textContent = 'Testing…';
        let got = '';
        try {
          const res = await this.stream([{ role: 'user', content: 'Reply with the single word: ready' }], (d) => (got += d), undefined, read(), (note) => (out.textContent = note));
          out.textContent = '✓ Connected: “' + got.trim().slice(0, 40) + '”' + (res.skipped.length ? ` – from ${res.model} (${res.skipped.map((x) => x.model + ' ' + skipWord(x.status)).join(', ')})` : '');
        } catch (e) {
          out.textContent = '✗ ' + e.message;
        }
      });
      B.querySelector('[data-x="save"]').addEventListener('click', () => {
        collect();
        const want = B.querySelector('input[name="aimode"]:checked').value;
        if (want === 'live' && !this.key && needsKey(this.settings)) {
          toast('Add an API key for live mode (or choose guided mode).', 'warn');
          return;
        }
        const changed = want !== this.mode;
        this.mode = want;
        store.set('ai:mode', want);
        this.renderMode();
        m.close();
        if (changed) {
          this.addBubble('assistant', want === 'live' ? 'Switched to **live** mode – I am now a real AI model. Remember to check everything I tell you.' : 'Switched to **guided** mode.', {});
          bus.emit('ai:mode', { mode: want });
        }
      });
    }
  }

  MG.Assistant = Assistant;
  MG.renderMarkdown = renderMarkdown;
})();
