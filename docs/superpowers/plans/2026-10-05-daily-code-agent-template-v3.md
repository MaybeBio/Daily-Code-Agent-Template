# Daily-Code-Agent-Template v3 静态站点 + 富 code card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 v2 归档阶段之上,为每周 `score >= min_score` 的保留仓库生成 LLM 富卡片(Code Card),渲染成静态站点并部署到 GitHub Pages,页面内附当周 Issue 链接。

**Architecture:** 新增两层 —— `scripts/cards.py`(LLM 卡片生成,读 scored → 过滤保留仓库 → 拉 README → 生成 markdown 卡片 → 写自包含 `data/cards/<date>.json`);`scripts/build_site.py`(Jinja2 静态站点,遍历 `data/cards/*.json` + `data/latest_issue.txt` → 渲染 `site/`)。站点镜像 paper 模板的 `build_site.py` + `templates/` + `deploy_pages.yml`。`code/`(归档)从 gitignored 改为提交进 git,但站点卡片只外链 GitHub + 三处公网 wiki URL,不渲染本地归档。

**Tech Stack:** Python 3.11;Jinja2 + markdown(站点渲染);openai(LLM);pytest + PyYAML。

**Spec:** `docs/superpowers/specs/2026-10-05-daily-code-agent-template-v3-design.md`

## Global Constraints

- 复用 `common.py` 的 `load_config` / `data_dir` / `load_json` / `dump_json` / `today` / `ROOT`,以及 v2 的 `archive.threshold(scored, min_score)`,不重复实现。
- 测试**不联网**:所有 LLM 调用经注入的 `client` / `card_fn`,README 拉取经注入的 `fetch`,测试里 monkeypatch;`build_site` 只读本地 `data/`,不联网。
- 单仓库 README 拉取或 LLM 卡片生成失败**隔离**(`card` 记空串 `""`),绝不拖垮整阶段(对齐 v1「单条失败不拖垮整周」)。
- 仅 `score >= llm.min_score`(默认 5)的仓库生成卡片;低分仓库不生成、不进站点。
- `code/` **提交进 git**(从 `.gitignore` 移除);`site/` 保持 gitignored(部署时重建)。
- **提交约定**:使用仓库已配置身份 `Joe Hoye Dow <luxunisgod123@gmail.com>`,**绝不追加任何 `Co-Authored-By:` 行**。

## Review Focus

以下五类输入/失败模式是 spec 隐含但默认任务测试未必覆盖的,最可能咬人(最可能先):

1. `data/cards/` 目录不存在(站点从未跑过)→ `build_site` 渲染空 index/archive,不崩溃。→ Task 2 加 `test_build_site_empty_no_crash`。
2. `data/latest_issue.txt` 缺失或为空 → 首页不渲染 Issue 链接,不崩溃。→ Task 2 加 `test_build_site_no_issue_link`。
3. 某仓库 `card` 为空串(拉取/LLM 失败)→ 详情页不渲染卡片段(`if card_html` 守卫),不崩溃。→ Task 2 加 `test_build_site_empty_card`。
4. `config.yaml` 缺失 `llm.min_score`(旧配置)→ `cards.run` 回退默认 5,仍正确过滤。→ Task 1 加 `test_run_defaults_min_score_when_absent`。
5. `config.yaml` 设了 `site_base_url`(子路径部署)→ 所有链接加 `BASE` 前缀。→ Task 2 加 `test_site_base_path_and_base_prefix`。

---

### Task 1: 卡片生成阶段 `scripts/cards.py` + `agent.build_code_card` + `code_card` prompt

**Files:**
- Create: `scripts/cards.py`
- Modify: `scripts/agent.py`(加 `build_code_card`)
- Modify: `prompts.yaml`(加 `code_card`)
- Test: `tests/test_cards.py`

**Interfaces:**
- Consumes: `common.load_config`/`data_dir`/`load_json`/`dump_json`/`today`(v1);`archive.threshold(scored, min_score) -> list[dict]`(v2);`gh.fetch_readme(full_name)`(v1);`agent.make_client`/`model_name`(v1)。
- Produces(供 Task 2 的 `build_site.py` 依赖):
  - `cards.card_record(row: dict, card: str) -> dict`
  - `cards.run(cfg: dict, date: str, client=None, fetch=None, card_fn=None) -> list[dict]`
  - `agent.build_code_card(client, model, prompts, topic, readme) -> dict`(返回 `{"card": str}`)
  - 文件:`data/cards/<date>.json`(自包含记录:`full_name/url/language/stars/pushed_at/status/score/one_liner/card`)

- [ ] **Step 1: 写失败测试** `tests/test_cards.py`

```python
import types
from scripts import cards, agent

PROMPTS = {"code_card": {"system": "s", "user": "{topic}\n{readme}"}}

def _fake_client(content):
    msg = types.SimpleNamespace(content=content)
    resp = types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])
    return types.SimpleNamespace(chat=types.SimpleNamespace(
        completions=types.SimpleNamespace(create=lambda **kw: resp)))

def test_card_record_shape():
    row = {"full_name": "a/b", "url": "https://github.com/a/b", "language": "Python",
           "stars": 5, "pushed_at": "t", "status": "new", "score": 8, "one_liner": "x"}
    out = cards.card_record(row, "## 是什么\n...")
    assert out == {"full_name": "a/b", "url": "https://github.com/a/b", "language": "Python",
                   "stars": 5, "pushed_at": "t", "status": "new", "score": 8,
                   "one_liner": "x", "card": "## 是什么\n..."}

def test_run_cards_only_keepers(monkeypatch, tmp_path):
    monkeypatch.setattr(cards.common, "ROOT", str(tmp_path))
    scored = [
        {"full_name": "hi/a", "url": "u", "language": "Python", "stars": 1, "status": "new",
         "score": 9, "one_liner": "x"},
        {"full_name": "lo/b", "url": "u", "language": "Go", "stars": 1, "status": "new",
         "score": 2, "one_liner": "y"},
    ]
    cards.common.dump_json(str(tmp_path / "data" / "scored" / "2026-10-05.json"), scored)
    monkeypatch.setattr(cards, "load_prompts", lambda p: PROMPTS)
    out = cards.run({"llm": {"min_score": 5}, "topic": "t"}, "2026-10-05",
                    client=object(), fetch=lambda fn: "README",
                    card_fn=lambda c, m, p, topic, readme: {"card": "card:" + fn})
    assert [r["full_name"] for r in out] == ["hi/a"]
    saved = cards.common.load_json(str(tmp_path / "data" / "cards" / "2026-10-05.json"))
    assert saved[0]["card"] == "card:hi/a"
    assert set(saved[0]) == {"full_name", "url", "language", "stars", "pushed_at",
                             "status", "score", "one_liner", "card"}

def test_run_card_failure_is_isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(cards.common, "ROOT", str(tmp_path))
    cards.common.dump_json(str(tmp_path / "data" / "scored" / "2026-10-05.json"),
                           [{"full_name": "a/b", "url": "u", "language": "Py", "stars": 1,
                             "status": "new", "score": 8, "one_liner": "x"}])
    monkeypatch.setattr(cards, "load_prompts", lambda p: PROMPTS)
    def boom(fn):
        raise RuntimeError("fetch failed")
    out = cards.run({"llm": {"min_score": 5}, "topic": "t"}, "2026-10-05",
                    client=object(), fetch=boom,
                    card_fn=lambda c, m, p, t, r: {"card": "x"})
    assert out[0]["card"] == ""

def test_run_defaults_min_score_when_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(cards.common, "ROOT", str(tmp_path))
    cards.common.dump_json(str(tmp_path / "data" / "scored" / "2026-10-05.json"),
                           [{"full_name": "a/b", "url": "u", "language": "Py", "stars": 1,
                             "status": "new", "score": 4, "one_liner": "x"},
                            {"full_name": "c/d", "url": "u", "language": "Py", "stars": 1,
                             "status": "new", "score": 6, "one_liner": "y"}])
    monkeypatch.setattr(cards, "load_prompts", lambda p: PROMPTS)
    out = cards.run({"topic": "t"}, "2026-10-05",
                    client=object(), fetch=lambda fn: "r",
                    card_fn=lambda c, m, p, t, r: {"card": "x"})
    assert [r["full_name"] for r in out] == ["c/d"]

def test_run_missing_scored_yields_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(cards.common, "ROOT", str(tmp_path))
    calls = []
    monkeypatch.setattr(cards, "load_prompts", lambda p: PROMPTS)
    out = cards.run({"llm": {"min_score": 5}, "topic": "t"}, "2026-10-05",
                    client=object(), fetch=lambda fn: calls.append(fn) or "r",
                    card_fn=lambda c, m, p, t, r: {"card": "x"})
    assert out == [] and calls == []

def test_build_code_card_parses_json():
    client = _fake_client('{"card": "## 是什么\\nhello"}')
    out = agent.build_code_card(client, "m", PROMPTS, "topic", "README")
    assert out == {"card": "## 是什么\nhello"}
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_cards.py -v`
Expected: FAIL(`ModuleNotFoundError: scripts.cards`)

- [ ] **Step 3: 实现**

**(a)** `prompts.yaml` — 在 `score:` 块后追加:

```yaml
code_card:
  system: >
    你是科研代码情报助手。给定研究课题与该仓库的 README,生成一份「Code Card」,中文为主,技术术语保留英文。
    只基于 README,绝不编造。严格输出 JSON:{"card": "<markdown>"},markdown 用 ## 二级标题,固定四节,顺序为:
    ## 是什么、## 亮点、## 为何对本课题有用、## 怎么用。
  user: >
    课题:{topic}
    README:
    {readme}
```

**(b)** `scripts/agent.py` — 在 `score_repo` 之后追加:

```python
def build_code_card(client, model, prompts, topic, readme) -> dict:
    p = prompts["code_card"]
    msgs = [{"role": "system", "content": p["system"]},
            {"role": "user", "content": p["user"].format(topic=topic, readme=readme[:12000])}]
    last = None
    for attempt in range(4):
        try:
            r = client.chat.completions.create(model=model, messages=msgs, temperature=0.0,
                                                response_format={"type": "json_object"})
            obj = json.loads(r.choices[0].message.content)
            return {"card": str(obj.get("card", ""))}
        except Exception as e:      # 网络/限流/解析
            last = e
            if attempt < 3:
                time.sleep(2 ** attempt)
    raise last
```

**(c)** `scripts/cards.py`:

```python
import argparse, os, sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts import common, agent, gh, archive  # noqa: E402
from scripts.agent import load_prompts  # noqa: E402

def card_record(row, card):
    return {"full_name": row["full_name"], "url": row.get("url", ""),
            "language": row.get("language", ""), "stars": row.get("stars", 0),
            "pushed_at": row.get("pushed_at", ""), "status": row.get("status", ""),
            "score": row["score"], "one_liner": row.get("one_liner", ""), "card": card}

def run(cfg, date, client=None, fetch=None, card_fn=None):
    fetch = fetch or gh.fetch_readme
    client = client if client is not None else agent.make_client()
    card_fn = card_fn or agent.build_code_card
    prompts = load_prompts(os.path.join(common.ROOT, "prompts.yaml"))
    model = agent.model_name()
    min_score = int(cfg.get("llm", {}).get("min_score", 5))
    scored_path = common.data_dir("scored", f"{date}.json")
    scored = common.load_json(scored_path) if os.path.exists(scored_path) else []
    keepers = archive.threshold(scored, min_score)
    def work(row):
        try:
            readme = fetch(row["full_name"])
            res = card_fn(client, model, prompts, cfg["topic"], readme)
            card = res.get("card", "")
        except Exception:
            card = ""
        return card_record(row, card)
    with ThreadPoolExecutor(max_workers=int(cfg.get("llm", {}).get("concurrency", 8))) as ex:
        out = list(ex.map(work, keepers))
    common.dump_json(common.data_dir("cards", f"{date}.json"), out)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(common.ROOT, "config.yaml"))
    ap.add_argument("--date", default=None)
    a = ap.parse_args()
    cfg = common.load_config(a.config)
    date = a.date or common.today()
    print(len(run(cfg, date)))

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_cards.py -v`
Expected: PASS(6 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/cards.py scripts/agent.py prompts.yaml tests/test_cards.py
git commit -m "feat: code card generation stage for high-score repos"
```

---

### Task 2: 站点生成 `scripts/build_site.py` + `templates/` + 渲染依赖

**Files:**
- Create: `scripts/build_site.py`
- Create: `templates/base.html`、`templates/index.html`、`templates/archive.html`、`templates/code.html`、`templates/_code_card.html`、`templates/assets/style.css`
- Modify: `requirements.txt`(加 `jinja2`、`markdown`)
- Test: `tests/test_build_site.py`

**Interfaces:**
- Consumes: Task 1 的 `data/cards/<date>.json`(自包含记录)与 `data/latest_issue.txt`(由 Task 3 的 weekly.yml 产出);`config.yaml` 的 `title` / `site_base_url`。
- Produces(供 Task 3 的 `deploy_pages.yml` 依赖):
  - `build_site.score_tier(score) -> str`(`high`/`mid`/`low`/`none`)
  - `build_site.wiki_url(source, full_name) -> str`
  - `build_site.load_cards(out_dir) -> list[dict]`
  - `build_site.load_issue_url(out_dir) -> str`
  - `build_site.build_site(out_dir, config=None)` → 渲染 `site/`
  - `build_site.main()` — argparse `--out-dir`(默认 `.`)、`--config`

- [ ] **Step 1: 写失败测试** `tests/test_build_site.py`

```python
import json, os
from scripts import build_site

def test_score_tier():
    assert build_site.score_tier(8) == "high"
    assert build_site.score_tier(5) == "mid"
    assert build_site.score_tier(3) == "low"
    assert build_site.score_tier(None) == "none"

def test_wiki_url():
    assert build_site.wiki_url("deepwiki", "a/b") == "https://deepwiki.com/a/b"
    assert build_site.wiki_url("codewiki", "a/b") == "https://codewiki.google/github.com/a/b"
    assert build_site.wiki_url("zread", "a/b") == "https://zread.ai/a/b"
    assert build_site.wiki_url("nope", "a/b") == ""

def test_load_cards_empty(tmp_path):
    assert build_site.load_cards(str(tmp_path)) == []

def test_load_issue_url_missing(tmp_path):
    assert build_site.load_issue_url(str(tmp_path)) == ""

def test_site_base_path_and_base_prefix():
    assert build_site.site_base_path("") == ""
    assert build_site.site_base_path("https://example.com/repos/foo") == "/repos/foo"

def _write_cards(tmp_path, rows):
    d = str(tmp_path / "data" / "cards")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "2026-10-05.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)

def test_build_site_renders(tmp_path):
    _write_cards(tmp_path, [{"full_name": "a/b", "url": "https://github.com/a/b",
                             "language": "Python", "stars": 5,
                             "pushed_at": "2026-10-01T00:00:00Z", "status": "new",
                             "score": 8, "one_liner": "one",
                             "card": "## 是什么\nhello"}])
    open(str(tmp_path / "data" / "latest_issue.txt"), "w").write("https://github.com/x/y/issues/1")
    build_site.build_site(str(tmp_path), {"title": "T", "site_base_url": ""})
    idx = open(str(tmp_path / "site" / "index.html"), encoding="utf-8").read()
    assert "当周 Issue" in idx and "https://github.com/x/y/issues/1" in idx
    arch = open(str(tmp_path / "site" / "archive.html"), encoding="utf-8").read()
    assert "a/b" in arch
    detail = open(str(tmp_path / "site" / "repos" / "a__b" / "index.html"), encoding="utf-8").read()
    assert "https://deepwiki.com/a/b" in detail and "hello" in detail

def test_build_site_empty_no_crash(tmp_path):
    build_site.build_site(str(tmp_path), {"title": "T", "site_base_url": ""})
    idx = open(str(tmp_path / "site" / "index.html"), encoding="utf-8").read()
    assert "本周推荐" in idx

def test_build_site_no_issue_link(tmp_path):
    _write_cards(tmp_path, [{"full_name": "a/b", "url": "u", "language": "Py", "stars": 1,
                             "pushed_at": "t", "status": "new", "score": 8,
                             "one_liner": "x", "card": "## 是什么\nhi"}])
    build_site.build_site(str(tmp_path), {"title": "T", "site_base_url": ""})
    idx = open(str(tmp_path / "site" / "index.html"), encoding="utf-8").read()
    assert "当周 Issue" not in idx

def test_build_site_empty_card(tmp_path):
    _write_cards(tmp_path, [{"full_name": "a/b", "url": "u", "language": "Py", "stars": 1,
                             "pushed_at": "t", "status": "new", "score": 8,
                             "one_liner": "x", "card": ""}])
    build_site.build_site(str(tmp_path), {"title": "T", "site_base_url": ""})
    detail = open(str(tmp_path / "site" / "repos" / "a__b" / "index.html"), encoding="utf-8").read()
    assert "Code Card" not in detail
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_build_site.py -v`
Expected: FAIL(`ModuleNotFoundError: scripts.build_site`)

- [ ] **Step 3: 实现**

**(a)** `requirements.txt`:

```
PyYAML
openai
pytest
jinja2
markdown
```

**(b)** `scripts/build_site.py`:

```python
import argparse, json, os, shutil
from urllib.parse import urlparse
import markdown as md
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(os.path.dirname(HERE), "templates")
WIKI_SOURCES = ["deepwiki", "codewiki", "zread"]

def load_config(path):
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if not isinstance(cfg, dict):
        raise ValueError("config must be a YAML mapping")
    return cfg

def site_base_path(site_base_url):
    url = (site_base_url or "").strip()
    if not url:
        return ""
    return urlparse(url).path.rstrip("/")

def score_tier(score):
    try:
        s = int(score)
    except (TypeError, ValueError):
        return "none"
    if s >= 8:
        return "high"
    if s >= 5:
        return "mid"
    return "low"

def wiki_url(source, full_name):
    if source == "deepwiki":
        return f"https://deepwiki.com/{full_name}"
    if source == "codewiki":
        return f"https://codewiki.google/github.com/{full_name}"
    if source == "zread":
        return f"https://zread.ai/{full_name}"
    return ""

def repo_dir_name(full_name):
    return full_name.replace("/", "__")

def load_cards(out_dir):
    cards_root = os.path.join(out_dir, "data", "cards")
    if not os.path.isdir(cards_root):
        return []
    records = []
    for fname in sorted(os.listdir(cards_root)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(cards_root, fname), encoding="utf-8") as f:
            rows = json.load(f)
        for r in rows:
            records.append({**r, "date": fname[:-5]})
    records.sort(key=lambda r: r.get("date") or "", reverse=True)
    return records

def load_issue_url(out_dir):
    path = os.path.join(out_dir, "data", "latest_issue.txt")
    if not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read().strip()

def _md_to_html(text):
    return md.markdown(text or "", extensions=["tables", "fenced_code", "sane_lists"])

def build_site(out_dir, config=None):
    cfg = config or {}
    base_path = site_base_path(cfg.get("site_base_url") or "")
    site_title = (cfg.get("title") or cfg.get("topic") or "").strip()
    records = load_cards(out_dir)
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))
    env.globals["BASE"] = base_path
    env.globals["SITE_TITLE"] = site_title
    env.globals["score_tier"] = score_tier
    env.globals["wiki_url"] = wiki_url
    env.globals["repo_dir_name"] = repo_dir_name
    env.globals["WIKI_SOURCES"] = WIKI_SOURCES

    site_dir = os.path.join(out_dir, "site")
    assets_dir = os.path.join(site_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    latest_date = records[0]["date"] if records else ""
    this_week = [r for r in records if r["date"] == latest_date] if records else []
    issue_url = load_issue_url(out_dir)

    for r in records:
        page = env.get_template("code.html").render(repo=r, card_html=_md_to_html(r.get("card", "")))
        page_dir = os.path.join(site_dir, "repos", repo_dir_name(r["full_name"]))
        os.makedirs(page_dir, exist_ok=True)
        with open(os.path.join(page_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(page)

    with open(os.path.join(site_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(env.get_template("index.html").render(
            window=latest_date, repos=this_week, issue_url=issue_url, total=len(records)))

    by_date = {}
    for r in records:
        by_date.setdefault(r["date"], []).append(r)
    weeks = [{"date": d, "repos": by_date[d]} for d in sorted(by_date, reverse=True)]
    with open(os.path.join(site_dir, "archive.html"), "w", encoding="utf-8") as f:
        f.write(env.get_template("archive.html").render(weeks=weeks, total=len(records)))

    shutil.copy(os.path.join(TEMPLATES, "assets", "style.css"),
                os.path.join(assets_dir, "style.css"))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the static site from data/.")
    parser.add_argument("--out-dir", default=".", help="Repo root")
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    args = parser.parse_args()
    cfg = load_config(args.config) if args.config else None
    build_site(args.out_dir, cfg)
```

**(c)** `templates/base.html`:

```html
<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}{{ SITE_TITLE }}{% endblock %}</title>
  <link rel="stylesheet" href="{{ BASE }}/assets/style.css">
</head>
<body>
  <header class="site-header">
    <a class="brand" href="{{ BASE }}/">{{ SITE_TITLE }}</a>
    <nav>
      <a href="{{ BASE }}/">本周</a>
      <a href="{{ BASE }}/archive.html">归档</a>
    </nav>
  </header>
  <main>{% block content %}{% endblock %}</main>
</body>
</html>
```

**(d)** `templates/index.html`:

```html
{% extends "base.html" %}
{% block title %}本周推荐 · {{ SITE_TITLE }}{% endblock %}
{% block content %}
<h1>本周推荐 <span class="window-tag">{{ window }}</span></h1>
<p class="muted">累计 {{ total }} 个仓库 · 按相关度评分排序</p>
{% if issue_url %}<p class="issue-link"><a href="{{ issue_url }}">当周 Issue →</a></p>{% endif %}
<div class="layout">
  <aside class="sidebar">
    <div class="legend">
      <h3>相关度评分</h3>
      <div class="row"><span class="dot high"></span>高<span class="range">8–10</span></div>
      <div class="row"><span class="dot mid"></span>中<span class="range">5–7</span></div>
    </div>
  </aside>
  <div class="content">
    <div class="repo-list">
      {% for r in repos %}{% set card_index = loop.index %}{% include "_code_card.html" %}{% endfor %}
    </div>
  </div>
</div>
{% endblock %}
```

**(e)** `templates/archive.html`:

```html
{% extends "base.html" %}
{% block title %}归档 · {{ SITE_TITLE }}{% endblock %}
{% block content %}
<h1>历史归档</h1>
<p class="muted">累计 {{ total }} 个仓库 · 按周归档</p>
{% for w in weeks %}
<details class="archive-week-block"{% if loop.first %} open{% endif %}>
  <summary>{{ w.date }}（{{ w.repos|length }} 个）</summary>
  <div class="repo-list">
    {% for r in w.repos %}{% set card_index = loop.index %}{% include "_code_card.html" %}{% endfor %}
  </div>
</details>
{% endfor %}
{% endblock %}
```

**(f)** `templates/_code_card.html`:

```html
<a class="repo-card" href="{{ BASE }}/repos/{{ repo_dir_name(r.full_name) }}/">
  <div class="repo-number">{{ card_index }}</div>
  <div class="repo-card-main">
    <div class="repo-meta">
      <span class="score score-{{ score_tier(r.score) }}">{{ r.score if r.score is not none else "-" }}</span>
      {% if r.language %}<span class="lang">{{ r.language }}</span>{% endif %}
      {% if r.stars %}<span class="stars">★ {{ r.stars }}</span>{% endif %}
      {% if r.status %}<span class="status">{{ r.status }}</span>{% endif %}
      <span>{{ r.pushed_at[:10] }}</span>
    </div>
    <h2>{{ r.full_name }}</h2>
    <p class="card-summary">{{ r.one_liner }}</p>
  </div>
</a>
```

**(g)** `templates/code.html`:

```html
{% extends "base.html" %}
{% block title %}{{ repo.full_name }} · {{ SITE_TITLE }}{% endblock %}
{% block content %}
<article class="repo">
  <div class="repo-head">
    <span class="score score-{{ score_tier(repo.score) }}">{{ repo.score if repo.score is not none else "-" }}</span>
    <div>
      <h1>{{ repo.full_name }}</h1>
      <div class="meta">
        {% if repo.language %}<span class="lang">{{ repo.language }}</span>{% endif %}
        {% if repo.stars %}<span class="stars">★ {{ repo.stars }}</span>{% endif %}
        {% if repo.status %}<span class="status">{{ repo.status }}</span>{% endif %}
        · {{ repo.pushed_at[:10] }}
      </div>
      {% if repo.one_liner %}<p class="one-liner">{{ repo.one_liner }}</p>{% endif %}
      <div class="repo-links">
        <a href="{{ repo.url }}">GitHub</a>
        {% for s in WIKI_SOURCES %}<a href="{{ wiki_url(s, repo.full_name) }}">{{ s }}</a>{% endfor %}
      </div>
    </div>
  </div>
  {% if card_html %}
  <section>
    <h2>Code Card</h2>
    <div class="md">{{ card_html | safe }}</div>
  </section>
  {% endif %}
</article>
{% endblock %}
```

**(h)** `templates/assets/style.css`:

```css
:root { --bg:#fafaf8; --fg:#182932; --muted:#61717a; --card:#ffffff; --accent:#176c65; --border:#dfe5e5; --high:#16a34a; --mid:#eab308; --low:#dc2626; --none:#6b7280; --serif:Georgia,'Times New Roman',serif; }
* { box-sizing: border-box; }
body { margin:0; font-family:-apple-system,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif; background:var(--bg); color:var(--fg); line-height:1.6; }
.site-header { display:flex; align-items:center; gap:24px; padding:14px 24px; background:var(--card); border-bottom:1px solid var(--border); position:sticky; top:0; }
.brand { font-family:var(--serif); font-weight:700; text-decoration:none; color:var(--accent); font-size:18px; }
.site-header nav a { margin-right:16px; color:var(--muted); text-decoration:none; font-size:14px; }
.site-header nav a:hover { color:var(--accent); }
main { max-width:1080px; margin:0 auto; padding:24px; }
h1 { font-size:24px; margin:0 0 4px; }
.muted { color:var(--muted); font-size:14px; }
.window-tag { color:var(--accent); font-size:16px; }
.issue-link a { color:var(--accent); font-weight:600; text-decoration:none; }

.layout { display:flex; gap:24px; margin-top:16px; }
.sidebar { flex:0 0 180px; }
.content { flex:1; min-width:0; }
.legend { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:14px; }
.legend h3 { font-size:11px; letter-spacing:1px; color:var(--accent); margin:0 0 10px; text-transform:uppercase; }
.legend .row { display:flex; align-items:center; gap:8px; font-size:13px; margin-bottom:8px; }
.legend .dot { width:10px; height:10px; border-radius:3px; flex:0 0 10px; }
.legend .range { color:var(--muted); font-size:12px; margin-left:auto; }
.dot.high { background:var(--high); }
.dot.mid { background:var(--mid); }
.dot.low { background:var(--low); }

.repo-list { margin:0; }
.repo-card { display:flex; gap:14px; background:var(--card); border:1px solid var(--border); border-radius:10px; padding:14px 16px; margin-bottom:12px; text-decoration:none; color:var(--fg); transition:box-shadow .15s, transform .15s; }
.repo-card:hover { box-shadow:0 4px 16px rgba(0,0,0,.06); transform:translateY(-1px); }
.repo-number { font-family:var(--serif); color:var(--accent); font-size:20px; font-weight:700; flex:0 0 32px; text-align:right; opacity:.55; }
.repo-card-main { flex:1; min-width:0; }
.repo-meta { display:flex; align-items:center; gap:10px; font-size:12px; color:var(--muted); flex-wrap:wrap; }
.lang { color:var(--accent); font-weight:650; }
.stars { color:#8a661e; }
.status { background:#eef2f2; color:var(--muted); border-radius:4px; padding:1px 6px; font-size:11px; }
.repo-card h2 { font-size:16px; margin:4px 0; line-height:1.4; }
.card-summary { color:#3b505b; font-size:13px; margin:0; }

.score { display:inline-block; color:#fff; font-weight:700; border-radius:6px; padding:2px 9px; font-size:13px; }
.score-high { background:var(--high); }
.score-mid { background:var(--mid); }
.score-low { background:var(--low); }
.score-none { background:var(--none); }

.archive-week-block { margin-bottom:8px; }
.archive-week-block > summary { cursor:pointer; font-size:16px; font-weight:700; padding:10px 0; border-bottom:1px solid var(--border); }

.repo { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:24px; }
.repo-head { display:flex; gap:16px; margin-bottom:24px; }
.repo-head h1 { font-size:22px; }
.meta { color:var(--muted); font-size:13px; margin:2px 0; }
.one-liner { color:#3b505b; font-size:14px; margin:8px 0 0; }
.repo-links { margin-top:10px; }
.repo-links a { display:inline-block; margin-right:10px; color:var(--accent); text-decoration:none; font-size:14px; font-weight:600; }
.md table { border-collapse:collapse; width:100%; margin:12px 0; font-size:14px; }
.md th, .md td { border:1px solid var(--border); padding:8px; text-align:left; vertical-align:top; }
.md th { background:#f3f4f6; }
.md h2 { margin-top:28px; font-size:18px; }
.md h3 { font-size:16px; }
.md p { margin:8px 0; }
.md a { color:var(--accent); }

@media (max-width: 760px) {
  .layout { flex-direction: column; }
  .sidebar { flex: none; }
}
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_build_site.py -v`
Expected: PASS(9 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/build_site.py templates/ requirements.txt tests/test_build_site.py
git commit -m "feat: static site generator with repo code cards"
```

---

### Task 3: 流水线接线 + CI 工作流 + `.gitignore` + README

**Files:**
- Modify: `.gitignore`(移除 `code/`)
- Modify: `scripts/run_weekly.sh`(插入 cards 阶段)
- Modify: `.github/workflows/weekly.yml`(open issue 提前 + 捕获 URL)
- Create: `.github/workflows/deploy_pages.yml`
- Modify: `README.md`(v3 状态)

**Interfaces:**
- Consumes: Task 1 的 `scripts/cards.py main()`;Task 2 的 `scripts/build_site.py main()`。
- Produces: weekly 流水线顺序 search → merge → score → archive → **cards** → issue;`weekly.yml` 产出 `data/latest_issue.txt`;`deploy_pages.yml` 部署 `site/`。

- [ ] **Step 1: 编辑 `.gitignore`**

把:

```
# ── 运行产物 ──
# degit 浅克隆 (v2)
code/
# 静态站点,部署时重建 (v3)
site/
```

改为(移除 `code/`,保留 `site/` 忽略):

```
# ── 运行产物 ──
# 静态站点,部署时重建 (v3)
site/
```

(其余行 `__pycache__/`、`*.pyc`、`.pytest_cache/`、`.env`、三个参考目录保持不动。)

- [ ] **Step 2: 编辑 `scripts/run_weekly.sh`**

在 `archive` 行之后、`issue` 行之前插入一行(最终顺序 search → merge → score → archive → **cards** → issue):

```bash
echo "[weekly] cards";        "$PY" scripts/cards.py   --config config.yaml
```

- [ ] **Step 3: 编辑 `.github/workflows/weekly.yml`**

把当前顺序 `weekly → commit → open issue` 改为 `weekly → open issue(捕获 URL) → commit`。具体:将现有 `open issue` 步骤整体移到 `commit` 步骤之前,并把其 `run` 改为捕获 URL:

```yaml
      - name: open issue
        run: |
          : > data/latest_issue.txt
          if [ -s /tmp/issue.md ]; then
            url=$(gh issue create --title "$(cat /tmp/issue.title)" --body-file /tmp/issue.md) && echo "$url" > data/latest_issue.txt || true
          fi
```

(`commit` 步骤保持原样,现位于 open issue 之后,`git add -A` 会一并提交 `code/`、`data/cards/`、`data/latest_issue.txt`。)

- [ ] **Step 4: 新建 `.github/workflows/deploy_pages.yml`**

```yaml
name: deploy-pages
on:
  workflow_run:
    workflows: ["weekly-discovery"]
    types:
      - completed
  workflow_dispatch: {}
permissions:
  contents: read
  pages: write
  id-token: write
concurrency:
  group: "pages"
  cancel-in-progress: true
jobs:
  deploy:
    if: ${{ github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion == 'success' }}
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: python scripts/build_site.py --out-dir . --config config.yaml
      - uses: actions/configure-pages@v6
      - uses: actions/upload-pages-artifact@v4
        with:
          path: "site"
      - id: deployment
        uses: actions/deploy-pages@v5
```

- [ ] **Step 5: 编辑 `README.md`**

(a) 标题:`# Daily-Code-Agent-Template (v1 + v2)` → `# Daily-Code-Agent-Template (v1 + v2 + v3)`。

(b) 第 6-7 行的 deferred 说明,把「静态 Pages 站点仍属 v3,尚未实现」改为已实现:

```
> v1+v2+v3 覆盖「发现 + 打分 + 归档 + 站点」:每日免费元数据流、每周 README 打分、高分仓库的浅克隆(degit)+ wiki 归档,以及把这些高分仓库渲染成静态 Pages 站点(每仓库一张富 code card,附当周 Issue 链接)。
> v1+v2+v3 cover **discovery + scoring + archive + site**: the daily feed, weekly scoring, shallow-clone (degit) + wiki archive, and a static Pages site with one rich code card per high-score repo plus the weekly Issue link.
```

(c) 在「本地运行 / Run locally」的 `npm install -g degit` 一行之后加:

```
pip install jinja2 markdown            # 需要 / required for site build (v3)
```

(d) 在「本地运行」代码块末尾(issue 运行之后)加一行站点构建:

```
# 站点 / site (v3)
python scripts/build_site.py --out-dir . --config config.yaml
```

- [ ] **Step 6: 校验**

Run:
```bash
bash -n scripts/run_weekly.sh && echo "bash syntax ok"
python -c "import yaml,glob; [yaml.safe_load(open(f)) for f in glob.glob('.github/workflows/*.yml')]; print('workflows ok')"
grep -n "cards\|deploy-pages\|latest_issue" scripts/run_weekly.sh .github/workflows/weekly.yml .github/workflows/deploy_pages.yml
grep -n "^code/\|^site/" .gitignore
```
Expected:`bash syntax ok`、`workflows ok`,且 grep 命中 cards / deploy-pages / latest_issue;`.gitignore` 中只有 `site/` 命中、`code/` 不命中。

- [ ] **Step 7: 运行全量测试**

Run: `python -m pytest -q`
Expected: 全绿(现有 37 + 新增 15 = 52 passed)

- [ ] **Step 8: Commit**

```bash
git add .gitignore scripts/run_weekly.sh .github/workflows/weekly.yml .github/workflows/deploy_pages.yml README.md
git commit -m "feat: wire v3 site into pipeline and deploy to GitHub Pages"
```

---
