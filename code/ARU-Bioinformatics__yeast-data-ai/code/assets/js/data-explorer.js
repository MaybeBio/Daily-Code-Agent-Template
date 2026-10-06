/* =====================================================================
   Data tab: browse the yeast gene table without code – search, sort,
   filter, read the data dictionary, open a gene card.
   ===================================================================== */
(function () {
  'use strict';
  const MG = window.MG;
  const { h, esc, bus, fmt } = MG;

  /** RFC 4180 CSV parser (quotes, doubled quotes, commas and newlines in fields) */
  function parseCSV(text) {
    const rows = [];
    let row = [], f = '', q = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (q) {
        if (c === '"') {
          if (text[i + 1] === '"') {
            f += '"';
            i++;
          } else q = false;
        } else f += c;
      } else if (c === '"') q = true;
      else if (c === ',') {
        row.push(f);
        f = '';
      } else if (c === '\n') {
        row.push(f);
        rows.push(row);
        row = [];
        f = '';
      } else if (c !== '\r') f += c;
    }
    if (f || row.length) {
      row.push(f);
      rows.push(row);
    }
    const head = rows.shift();
    return rows.filter((r) => r.length === head.length).map((r) => {
      const o = {};
      head.forEach((k, i) => {
        const v = r[i];
        o[k] = v === '' ? null : /^-?\d+(\.\d+)?(e-?\d+)?$/i.test(v) ? Number(v) : v;
      });
      return o;
    });
  }

  const SHOW = ['gene', 'orf', 'essential', 'protein_length', 'protein_abundance', 'interaction_partners', 'human_homolog', 'paralog_identity', 'plddt', 'location', 'description'];

  class DataExplorer {
    constructor(root, opts) {
      this.root = root;
      this.opts = opts;
      this.rows = [];
      this.sortKey = 'gene';
      this.sortDir = 1;
      this.page = 0;
      this.per = 50;
      this.f = { text: '', ess: 'any', loc: 'any' };
      root.classList.add('dx');
      root.innerHTML = '<div class="ex-empty"><span class="spinner"></span> Loading the gene table…</div>';
      MG.fetchText(opts.url)
        .then((t) => {
          this.rows = parseCSV(t);
          this.cols = Object.keys(this.rows[0] || {});
          this.render();
          bus.emit('dx:loaded', { n: this.rows.length });
        })
        .catch((e) => (root.innerHTML = `<div class="ex-empty"><h3>Could not load the data</h3><p>${esc(e.message)}</p></div>`));
    }
    dict(k) {
      const d = (this.opts.dictionary || []).find((x) => x[0] === k);
      return d ? d[1] : '';
    }
    filtered() {
      const t = this.f.text.toLowerCase();
      let v = this.rows.filter((r) => {
        if (this.f.ess !== 'any' && String(r.essential) !== this.f.ess) return false;
        if (this.f.loc !== 'any' && r.location !== this.f.loc) return false;
        if (t && !`${r.gene} ${r.orf} ${r.description || ''}`.toLowerCase().includes(t)) return false;
        return true;
      });
      const k = this.sortKey, d = this.sortDir;
      v = v.slice().sort((a, b) => {
        const x = a[k], y = b[k];
        if (x == null && y == null) return 0;
        if (x == null) return 1;
        if (y == null) return -1;
        return (x < y ? -1 : x > y ? 1 : 0) * d;
      });
      return v;
    }
    render() {
      const R = this.root;
      R.innerHTML = '';
      const locs = Array.from(new Set(this.rows.map((r) => r.location))).sort();
      const search = h('input', { type: 'search', placeholder: 'Search gene, ORF or description…', value: this.f.text, 'aria-label': 'Search the gene table' });
      search.addEventListener('input', MG.debounce(() => {
        this.f.text = search.value.trim();
        this.page = 0;
        this.renderTable();
      }, 200));
      const ess = h('select', { 'aria-label': 'Essential or not' }, h('option', { value: 'any' }, 'all genes'), h('option', { value: '1' }, 'essential only'), h('option', { value: '0' }, 'non-essential only'));
      ess.value = this.f.ess;
      ess.addEventListener('change', () => {
        this.f.ess = ess.value;
        this.page = 0;
        this.renderTable();
      });
      const loc = h('select', { 'aria-label': 'Location' }, h('option', { value: 'any' }, 'any location'), locs.map((l) => h('option', { value: l }, l)));
      loc.value = this.f.loc;
      loc.addEventListener('change', () => {
        this.f.loc = loc.value;
        this.page = 0;
        this.renderTable();
      });
      const dictBtn = h('button.btn.small', { type: 'button', html: MG.icon('book') + '<span>What the columns mean</span>' });
      dictBtn.addEventListener('click', () => this.showDictionary());
      R.appendChild(h('div.dx-bar', h('b', { html: MG.icon('table') + ' yeast_genes.csv' }), h('span.pill', `${fmt(this.rows.length)} genes · ${this.cols.length} columns`), search, ess, loc, h('span.grow'), dictBtn));
      this.tableBox = h('div.dx-body');
      R.appendChild(this.tableBox);
      this.renderTable();
    }
    renderTable() {
      const v = this.filtered();
      const pages = Math.max(1, Math.ceil(v.length / this.per));
      this.page = Math.min(this.page, pages - 1);
      const slice = v.slice(this.page * this.per, (this.page + 1) * this.per);
      const B = this.tableBox;
      B.innerHTML = '';
      const t = h('table.dx-table');
      const tr = h('tr');
      SHOW.forEach((k) => {
        const sortBtn = h('button.dx-sort', { type: 'button', title: this.dict(k) + ' – click to sort' }, k.replace(/_/g, ' '), this.sortKey === k ? (this.sortDir > 0 ? ' ▲' : ' ▼') : '');
        const th = h('th', { class: this.sortKey === k ? 'sorted' : '', 'aria-sort': this.sortKey === k ? (this.sortDir > 0 ? 'ascending' : 'descending') : 'none' }, sortBtn);
        sortBtn.addEventListener('click', () => {
          if (this.sortKey === k) this.sortDir *= -1;
          else {
            this.sortKey = k;
            this.sortDir = typeof (this.rows[0] || {})[k] === 'number' ? -1 : 1;
          }
          this.renderTable();
        });
        tr.appendChild(th);
      });
      t.appendChild(h('thead', tr));
      const tb = h('tbody');
      slice.forEach((r) => {
        const row = h('tr', { class: r.essential ? 'ess' : '', tabindex: '0', title: 'Show all about ' + r.gene });
        SHOW.forEach((k) => {
          let val = r[k];
          if (k === 'essential') val = r.essential ? 'yes' : 'no';
          else if (k === 'human_homolog') val = r.human_homolog ? 'yes' : 'no';
          else if (typeof val === 'number') val = fmt(val, Number.isInteger(val) ? 0 : k === 'disorder' ? 2 : 1);
          else if (val == null) val = '–';
          if (k === 'description') row.appendChild(h('td.desc', { title: String(val) }, h('div.clamp2', String(val))));
          else row.appendChild(h('td', { class: k === 'gene' ? 'gn' : '' }, String(val)));
        });
        row.addEventListener('click', () => this.card(r));
        row.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            this.card(r);
          }
        });
        tb.appendChild(row);
      });
      t.appendChild(tb);
      B.appendChild(h('div.dx-scroll', t));
      const prev = h('button.btn.small', { type: 'button', disabled: this.page === 0 }, '‹ Previous');
      const next = h('button.btn.small', { type: 'button', disabled: this.page >= pages - 1 }, 'Next ›');
      prev.addEventListener('click', () => {
        this.page--;
        this.renderTable();
      });
      next.addEventListener('click', () => {
        this.page++;
        this.renderTable();
      });
      B.appendChild(h('div.dx-pager', h('span.muted.small', `${fmt(v.length)} genes match · page ${this.page + 1} of ${pages} · click a column heading to sort, a row (or press Enter on it) for details`), h('span.grow'), prev, next));
      bus.emit('dx:view', { n: v.length, text: this.f.text, sort: this.sortKey });
    }
    card(r) {
      const rows = this.cols.map((k) => {
        let v = r[k];
        if (v == null) v = '–';
        return `<tr><th title="${esc(this.dict(k))}">${esc(k)}</th><td>${esc(typeof v === 'number' ? fmt(v, Number.isInteger(v) ? 0 : 3) : v)}</td></tr>`;
      });
      const links = [
        `<a class="chip" href="https://www.yeastgenome.org/locus/${encodeURIComponent(r.orf)}" target="_blank" rel="noopener">SGD ↗</a>`,
        r.uniprot ? `<a class="chip" href="https://www.uniprot.org/uniprotkb/${encodeURIComponent(r.uniprot)}" target="_blank" rel="noopener">UniProt ↗</a>` : '',
        r.uniprot ? `<a class="chip" href="https://alphafold.ebi.ac.uk/entry/${encodeURIComponent(r.uniprot)}" target="_blank" rel="noopener">AlphaFold DB ↗</a>` : ''
      ].join(' ');
      const m = MG.modal(`${r.gene}${r.gene !== r.orf ? ' (' + r.orf + ')' : ''} – ${r.essential ? 'essential' : 'not essential'}`, `<p>${esc(r.description || '')}</p><div class="dx-links">${links}</div><div class="prompt-actions left"><button class="btn small" data-x="af" type="button">${MG.icon('cube')}<span>AlphaFold model in 3D</span></button><button class="btn small" data-x="nb" type="button">${MG.icon('notebook')}<span>Look it up in the notebook</span></button></div><table class="table small dx-card">${rows.join('')}</table>`);
      m.box.querySelector('[data-x="af"]').addEventListener('click', () => {
        m.close();
        if (MG.actions && MG.actions.af && r.uniprot) MG.actions.af(r.uniprot);
      });
      m.box.querySelector('[data-x="nb"]').addEventListener('click', () => {
        m.close();
        MG.app.showWorkbench('notebook');
        MG.app.nb.insertCode(`df[df['gene'] == '${r.gene}']`, { run: true });
      });
      bus.emit('dx:card', { gene: r.gene, orf: r.orf, essential: r.essential });
    }
    showDictionary() {
      const rows = (this.opts.dictionary || []).map((d) => `<tr><th><code>${esc(d[0])}</code></th><td>${esc(d[1])}</td></tr>`).join('');
      MG.modal('What the columns mean', `<p class="muted small">One row per gene of <i>Saccharomyces cerevisiae</i> (strain S288C). Sources are listed in the Reference chapter.</p><table class="table small">${rows}</table>`);
      bus.emit('dx:dictionary', {});
    }
  }

  MG.parseCSV = parseCSV;
  MG.DataExplorer = DataExplorer;
})();
