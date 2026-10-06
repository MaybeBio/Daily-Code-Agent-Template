/* =====================================================================
   Python in a Web Worker (Pyodide = CPython compiled to WebAssembly).
   The page talks to this worker with postMessage; the worker runs notebook
   cells one at a time and streams their output back.
   ===================================================================== */
/* global loadPyodide, importScripts */
'use strict';

let pyodide = null;
let runId = null;
let queue = Promise.resolve();

const post = (m) => self.postMessage(m);
const status = (text) => post({ type: 'status', text });

/* Output from Python. print() arrives in small pieces, so text is buffered per line and
   sent in batches; each cell's text output is capped so a runaway loop cannot freeze the page. */
const OUT_CAP = 200000;
let outChars = 0;
let outCut = false;
let sbuf = { name: null, text: '' };
function flushStream() {
  if (sbuf.text) post({ type: 'output', id: runId, payload: JSON.stringify({ type: 'stream', name: sbuf.name, text: sbuf.text }) });
  sbuf.text = '';
}
function resetOutput() {
  outChars = 0;
  outCut = false;
  sbuf = { name: null, text: '' };
}
self.nb_stream = (name, text) => {
  if (outCut || !text) return;
  if (outChars + text.length > OUT_CAP) {
    text = text.slice(0, Math.max(0, OUT_CAP - outChars)) + '\n… output cut after ' + OUT_CAP.toLocaleString('en') + ' characters (the cell carries on running; press Restart to stop it).\n';
    outCut = true;
  }
  outChars += text.length;
  if (sbuf.name !== name) flushStream();
  sbuf.name = name;
  sbuf.text += text;
  const nl = sbuf.text.lastIndexOf('\n');
  if (outCut || sbuf.text.length > 8192) flushStream();
  else if (nl >= 0) {
    const rest = sbuf.text.slice(nl + 1);
    sbuf.text = sbuf.text.slice(0, nl + 1);
    flushStream();
    sbuf.text = rest;
  }
};
// rich outputs (tables, plots, errors) as JSON text
self.nb_post_output = (json) => {
  flushStream();
  post({ type: 'output', id: runId, payload: json });
};

const PY_SETUP = String.raw`
import sys, io, json, base64, ast, inspect, linecache, traceback, difflib, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from js import nb_post_output, nb_stream

pd.set_option('display.max_rows', 20)
pd.set_option('display.min_rows', 10)
pd.set_option('display.max_columns', 30)
pd.set_option('display.width', 160)
pd.set_option('display.max_colwidth', 100)
plt.rcParams.update({'figure.figsize': (6.4, 4.2), 'figure.dpi': 100, 'axes.spines.top': False,
                     'axes.spines.right': False, 'font.size': 10, 'axes.titlesize': 11})

def _emit(obj):
    nb_post_output(json.dumps(obj))

class _Stream(io.TextIOBase):
    def __init__(self, name):
        self.name = name
    def writable(self):
        return True
    def write(self, s):
        if s:
            nb_stream(self.name, s)
        return len(s)
    def flush(self):
        pass

sys.stdout = _Stream('stdout')
sys.stderr = _Stream('stderr')
warnings.simplefilter('once')

def _png(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=110, bbox_inches='tight')
    return base64.b64encode(buf.getvalue()).decode('ascii')

def _flush_figures():
    for num in plt.get_fignums():
        fig = plt.figure(num)
        if fig.axes:
            _emit({'type': 'display', 'mime': 'image/png', 'data': _png(fig)})
    plt.close('all')

plt.show = lambda *a, **k: _flush_figures()

def _no_input(prompt=''):
    raise RuntimeError("input() cannot ask for typing in this notebook. Put the value in the code instead, e.g.  gene = 'ACT1'")

import builtins
builtins.input = _no_input

def _is_mpl(v):
    from matplotlib.artist import Artist
    from matplotlib.container import Container
    if isinstance(v, (Artist, Container)):
        return True
    if isinstance(v, np.ndarray) and v.dtype == object and v.size and all(isinstance(x, Artist) for x in v.ravel()):
        return True
    if isinstance(v, (list, tuple)) and v and any(_is_mpl(x) for x in v):
        return True
    if isinstance(v, dict) and v and all(isinstance(x, list) and all(isinstance(y, Artist) for y in x) for x in v.values()):
        return True
    return False

def _rich(o):
    from matplotlib.figure import Figure
    if isinstance(o, Figure):
        data = _png(o)
        plt.close(o)
        return {'type': 'display', 'mime': 'image/png', 'data': data}
    rh = getattr(o, '_repr_html_', None)
    if callable(rh) and not isinstance(o, type):
        try:
            h = rh()
            if h:
                return {'type': 'display', 'mime': 'text/html', 'data': h}
        except Exception:
            pass
    r = repr(o)
    if len(r) > 20000:
        r = r[:20000] + '\n… (output truncated)'
    return {'type': 'display', 'mime': 'text/plain', 'data': r}

def display(*objs, **kwargs):
    for o in objs:
        _emit(_rich(o))

from matplotlib.figure import Figure as _Figure
_Figure.show = lambda self, *a, **k: display(self)

_G = {'__name__': '__main__', '__builtins__': __builtins__, 'display': display}

def _hints(e):
    """simple, rule-based hints for common mistakes (shown under the error)"""
    hints = []
    name = type(e).__name__
    try:
        if name == 'KeyError' and e.args:
            key = str(e.args[0])
            frames = [v for vn, v in list(_G.items()) if isinstance(v, pd.DataFrame) and not vn.startswith('_')]
            names = [vn for vn, v in list(_G.items()) if isinstance(v, pd.DataFrame) and not vn.startswith('_')]
            for vn, v in zip(names, frames):
                close = difflib.get_close_matches(key, [str(c) for c in v.columns], n=3, cutoff=0.5)
                if close:
                    hints.append(f"'{key}' is not a column of {vn}. Did you mean: {', '.join(repr(c) for c in close)}?")
                    break
            if not hints:
                for vn, v in zip(names, frames):
                    for col in v.columns:
                        if v[col].dtype == object and (v[col] == key).any():
                            hints.append(f"'{key}' is a value in the column '{col}' of {vn}, not a column or row label. To select that row:  {vn}[{vn}['{col}'] == '{key}']")
                            break
                    if hints:
                        break
            if not hints:
                hints.append(f"'{key}' was not found. Names are case-sensitive: check the column names with  df.columns  (and row labels with  df.index).")
        elif name == 'NameError':
            import re
            m = re.search(r"name '([^']+)' is not defined", str(e))
            if m:
                n = m.group(1)
                import builtins as _b
                close = difflib.get_close_matches(n, [k for k in _G if not k.startswith('_')] + [k for k in dir(_b) if not k.startswith('_')], n=3, cutoff=0.6)
                if close:
                    hints.append(f"Did you mean {', '.join(close)}?")
                elif n in ('pd', 'np', 'plt'):
                    hints.append(f"'{n}' is an abbreviation that has to be imported first, e.g. import pandas as pd / import numpy as np / import matplotlib.pyplot as plt")
                else:
                    hints.append(f"'{n}' has not been created yet. Run the cell that defines it first (after a restart, Python forgets everything).")
        elif name in ('ModuleNotFoundError', 'ImportError'):
            hints.append('Only some packages are available in this browser notebook: pandas, numpy, scipy, scikit-learn, matplotlib, statsmodels and seaborn.')
        elif name == 'ValueError' and 'could not convert string to float' in str(e):
            hints.append('A text column is being used where numbers are needed – choose numeric feature columns only (e.g. drop orf, gene, location, description).')
        elif name == 'ValueError' and 'NaN' in str(e):
            hints.append('Some values are missing (NaN). Fill them (e.g. SimpleImputer or .fillna(...)) or drop those rows (.dropna()).')
    except Exception:
        pass
    return hints

def _emit_error(e, code):
    tb = traceback.TracebackException.from_exception(e)
    frames = [f for f in tb.stack if f.filename == '<cell>']
    lines = []
    if frames:
        lines.append('Traceback (most recent call last):')
        shown = frames if len(frames) <= 12 else frames[:5] + [None] + frames[-5:]
        for f in shown:
            if f is None:
                lines.append(f'  … {len(frames) - 10} more lines like these …')
                continue
            lines.append(f'  Cell line {f.lineno}' + (f', in {f.name}' if f.name != '<module>' else ''))
            if f.line:
                lines.append('    ' + f.line.strip())
    if isinstance(e, SyntaxError):
        lines.append(f'  Cell line {e.lineno}')
        if e.text:
            lines.append('    ' + e.text.rstrip('\n'))
            if e.offset:
                lines.append('    ' + ' ' * (max(e.offset, 1) - 1) + '^')
    only = [l for l in ''.join(tb.format_exception_only()).strip().split('\n') if l.strip()]
    msg = only[-1].strip() if isinstance(e, SyntaxError) else '\n'.join(l.rstrip() for l in only)
    if len(msg) > 3000:
        msg = msg[:3000] + ' …'
    lines.append(msg)
    hints = _hints(e)
    if 'Did you mean' in msg:  # Python already suggests a name: do not repeat it
        hints = [h for h in hints if not h.startswith('Did you mean')]
    _emit({'type': 'error', 'ename': type(e).__name__, 'evalue': str(e)[:2000], 'traceback': '\n'.join(lines),
           'lineno': (frames[-1].lineno if frames else getattr(e, 'lineno', None)), 'hints': hints})

_MAGIC = __import__('re').compile(r'^\s*[%!]')

async def _nb_run(code):
    if any(_MAGIC.match(l) for l in code.splitlines()):
        code = '\n'.join(('# ' + l) if _MAGIC.match(l) else l for l in code.splitlines())
        print('Note: lines starting with % or ! are Jupyter/IPython commands – they are not needed here and were skipped '
              '(plots appear by themselves; packages load when you import them).', file=sys.stderr)
    linecache.cache['<cell>'] = (len(code), None, code.splitlines(True), '<cell>')
    try:
        tree = ast.parse(code, filename='<cell>', mode='exec')
    except SyntaxError as e:
        _emit_error(e, code)
        return False
    last = None
    if tree.body and isinstance(tree.body[-1], ast.Expr) and not code.rstrip().endswith(';'):
        last = ast.Expression(tree.body.pop().value)
    flags = ast.PyCF_ALLOW_TOP_LEVEL_AWAIT
    try:
        r = eval(compile(tree, '<cell>', 'exec', flags=flags), _G)
        if inspect.iscoroutine(r):
            await r
        val = None
        if last is not None:
            val = eval(compile(last, '<cell>', 'eval', flags=flags), _G)
            if inspect.iscoroutine(val):
                val = await val
        _flush_figures()
        if val is not None and not _is_mpl(val):
            _G['_'] = val
            _emit(_rich(val))
        return True
    except BaseException as e:
        try:
            _flush_figures()
        except Exception:
            pass
        _emit_error(e, code)
        return False

def _nb_eval(expr):
    try:
        v = eval(expr, _G)
    except Exception:
        return 'null'
    try:
        if isinstance(v, (np.integer,)):
            v = int(v)
        elif isinstance(v, (np.floating,)):
            v = float(v)
        elif isinstance(v, np.ndarray):
            v = v.tolist()
        return json.dumps(v, default=str)
    except Exception:
        return json.dumps(str(v))

def _nb_vars():
    out = []
    for k, v in _G.items():
        if k.startswith('_') or k in ('display',) or inspect.ismodule(v) or callable(v) and not isinstance(v, (pd.DataFrame, pd.Series)):
            continue
        t = type(v).__name__
        if isinstance(v, pd.DataFrame):
            d = f'{v.shape[0]} rows × {v.shape[1]} columns'
        elif isinstance(v, pd.Series):
            d = f'{len(v)} values'
        elif isinstance(v, np.ndarray):
            d = 'shape ' + ' × '.join(str(x) for x in v.shape)
        elif isinstance(v, (int, float, str, bool)):
            d = repr(v)[:60]
        elif isinstance(v, (list, tuple, dict, set)):
            d = f'{len(v)} items'
        else:
            d = type(v).__module__.split('.')[0]
        out.append({'name': k, 'type': t, 'desc': d})
    return json.dumps(out)
`;

async function init(m) {
  status('Downloading Python (Pyodide)…');
  try {
    importScripts(m.indexURL + 'pyodide.js');
  } catch (e) {
    throw new Error('Could not download Python from ' + m.indexURL + ' – check the internet connection.');
  }
  WHEELS = m.wheels || {};
  pyodide = await loadPyodide({ indexURL: m.indexURL });
  status('Loading numpy, pandas and matplotlib…');
  await pyodide.loadPackage(m.preload || ['numpy', 'pandas', 'matplotlib'], { messageCallback: () => {}, errorCallback: () => {} });
  status('Loading the yeast data…');
  pyodide.FS.mkdirTree('/home/pyodide/data');
  for (const f of m.files || []) {
    const r = await fetch(f.url);
    if (!r.ok) throw new Error('Could not load ' + f.url);
    const buf = new Uint8Array(await r.arrayBuffer());
    pyodide.FS.writeFile('/home/pyodide/' + f.path, buf);
  }
  pyodide.FS.chdir('/home/pyodide');
  await pyodide.runPythonAsync(PY_SETUP);
  const versions = JSON.parse(await pyodide.runPythonAsync(
    "import sys, pandas, numpy, matplotlib; json.dumps({'python': sys.version.split()[0], 'pandas': pandas.__version__, 'numpy': numpy.__version__, 'matplotlib': matplotlib.__version__})"
  ));
  post({ type: 'ready', versions });
  // load the heavier packages in the background so they are ready when needed
  if (m.background && m.background.length) {
    pyodide.loadPackage(m.background, { messageCallback: () => {}, errorCallback: () => {} }).then(() => post({ type: 'background', done: true })).catch(() => {});
  }
}

let WHEELS = {}; // importable name -> URL of a pure-Python wheel hosted with the site (installed on demand)

async function run(m) {
  runId = m.id;
  resetOutput();
  const t0 = performance.now();
  try {
    await pyodide.loadPackagesFromImports(m.code, {
      messageCallback: (msg) => {
        const mm = /Loading (.+)/.exec(msg);
        if (mm) post({ type: 'status', text: 'Loading ' + mm[1].replace(/, /g, ', ').slice(0, 80) + '…', id: m.id });
      },
      errorCallback: () => {}
    });
    const wants = Object.keys(WHEELS).filter((k) => new RegExp('^\\s*(import|from)\\s+' + k + '\\b', 'm').test(m.code));
    if (wants.length) {
      const have = JSON.parse(await pyodide.runPythonAsync(`import importlib.util, json; json.dumps([${wants.map((w) => `importlib.util.find_spec('${w}') is not None`).join(',')}])`));
      const missing = wants.filter((w, i) => !have[i]);
      if (missing.length) {
        post({ type: 'status', text: 'Installing ' + missing.join(', ') + '…', id: m.id });
        await pyodide.loadPackage('micropip');
        const micropip = pyodide.pyimport('micropip');
        await micropip.install(missing.map((k) => WHEELS[k]));
        micropip.destroy();
      }
    }
  } catch (e) {
    /* a missing package is reported by Python itself when the import runs */
  }
  const runner = pyodide.globals.get('_nb_run');
  let ok = false;
  try {
    ok = await runner(m.code);
  } finally {
    runner.destroy();
    flushStream();
  }
  post({ type: 'done', id: m.id, ok: !!ok, secs: (performance.now() - t0) / 1000 });
  runId = null;
}

async function evalExpr(m) {
  const f = pyodide.globals.get('_nb_eval');
  let v = 'null';
  try {
    v = f(m.expr);
  } finally {
    f.destroy();
  }
  post({ type: 'evalResult', id: m.id, value: JSON.parse(v) });
}

async function vars(m) {
  const f = pyodide.globals.get('_nb_vars');
  let v = '[]';
  try {
    v = f();
  } finally {
    f.destroy();
  }
  post({ type: 'vars', id: m.id, value: JSON.parse(v) });
}

async function handle(m) {
  try {
    if (m.type === 'init') await init(m);
    else if (m.type === 'run') await run(m);
    else if (m.type === 'eval') await evalExpr(m);
    else if (m.type === 'vars') await vars(m);
  } catch (e) {
    post({ type: 'fatal', id: m.id, stage: m.type, message: String((e && e.message) || e) });
  }
}

self.onmessage = (ev) => {
  const m = ev.data;
  queue = queue.then(() => handle(m));
};
