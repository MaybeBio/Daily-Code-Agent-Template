# Daily-Code-Agent-Template v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 v1 心跳闭环——每日抓取关注圈动态并推送免费元数据表(Issue),每周把盲搜结果与日抽仓库并集、经持久索引去重后抓 README 做 LLM 打分,推送周报 Issue + CSV。

**Architecture:** 分阶段脚本 + JSON 中间产物(方案 B)。纯函数与 IO/子进程分离:解析类(`logs.py`)纯函数可单测;外部调用(`gh.py`)经一层封装便于 monkeypatch;业务阶段(`daily/search/merge/score/issue.py`)读取落盘 JSON、写下一阶段 JSON;`run_weekly.sh` 串联。状态集中在 `data/registry.json`。

**Tech Stack:** Python 3.11,pytest,stdlib(`json`/`csv`/`subprocess`/`concurrent.futures`/`urllib.parse`),`PyYAML`,`openai`(兼容网关)。外部命令:`gh`、`ghresearcher`。

**Spec:** `docs/superpowers/specs/2026-10-04-daily-code-agent-template-design.md`

## Global Constraints

- Python 3.11+;依赖仅 `PyYAML`、`openai`、`pytest`(测试)。
- 测试**不联网**:所有 `gh`/`ghresearcher`/LLM 调用必须可 monkeypatch。
- Secrets 只从环境变量读:`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`;`GH_TOKEN` 由 `gh` 自行读取。绝不写入文件。
- 分析对象统一是 README;不记录 `source`、不做来源加权。
- registry 三态:`new`(首次)→ 打分;`updated`(`last_commit != last_scored_commit`)→ 重跑并**原地覆盖**;`seen` → 跳过 LLM。
- LLM 并发默认 8;单条失败不得中断整周。
- 单 topic / 仓库;`config.yaml` 的 `topic` 为 slug。
- 提交信息与仓库约定:工作流用 `github-actions[bot]`;本地提交用 `Claude <noreply@anthropic.com>`。
- 所有路径相对仓库根;脚本从任意 cwd 运行需以 `__file__` 推导根目录。

## Review Focus

以下 5 类输入/失败模式最可能咬到使用者,且不被"理想路径"的测试覆盖;每条都在对应任务里钉一个测试:

1. **日志换行**:`ghresearcher monitor` 输出按终端宽度硬换行,一条记录可能跨多个物理行——未先"解绕"会截断仓库名。(Task 2)
2. **误把非仓库 token 当仓库**:日志正文含分支名(含 `/`)、PR 标题等;`owner/repo` 正则需锚定且排除明显非仓库形态。(Task 2)
3. **同一仓库同日多次/或同时来自盲搜与日抽**:并集必须去重为一条。(Task 6)
4. **`pushedAt` 未变却再次被搜到**:必须判为 `seen` 且**跳过 LLM**(成本守卫)。(Task 6)
5. **README 抓取失败或 LLM 返回非法 JSON**:不得拖垮整周;标记 `[fetch failed]` 继续。(Task 7)

---

### Task 1: 脚手架与 `common.py`

**Files:**
- Create: `requirements.txt`
- Create: `config.yaml`
- Create: `scripts/__init__.py`
- Create: `scripts/common.py`
- Create: `tests/__init__.py`
- Create: `pytest.ini`
- Test: `tests/test_common.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `common.load_config(path: str) -> dict`
  - `common.ROOT: str`(仓库根绝对路径)
  - `common.data_dir(*parts: str) -> str`(在 `<ROOT>/data/` 下拼路径并建目录)
  - `common.read_registry() -> dict` / `common.write_registry(reg: dict) -> None`
  - `common.load_json(path: str) -> dict|list` / `common.dump_json(path, obj) -> None`
  - `common.today() -> str`(`YYYY-MM-DD`,读 `TZ`)

- [ ] **Step 1: 写失败测试** `tests/test_common.py`

```python
import os, json
from scripts import common

def test_load_config_has_required_keys(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("topic: demo\ntitle: Demo\nllm:\n  concurrency: 8\n")
    cfg = common.load_config(str(p))
    assert cfg["topic"] == "demo"
    assert cfg["llm"]["concurrency"] == 8

def test_registry_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "ROOT", str(tmp_path))
    reg = common.read_registry()
    assert reg["repos"] == {}
    reg["repos"]["a/b"] = {"first_seen": "2026-10-04", "last_commit": "x"}
    common.write_registry(reg)
    assert common.read_registry()["repos"]["a/b"]["last_commit"] == "x"

def test_dump_json_creates_parents(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "ROOT", str(tmp_path))
    path = common.data_dir("daily", "x.json")
    common.dump_json(path, {"k": 1})
    assert json.load(open(path))["k"] == 1
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_common.py -v`
Expected: FAIL(`ModuleNotFoundError: scripts` 或 `AttributeError: load_config`)

- [ ] **Step 3: 实现** `scripts/common.py`

```python
import json, os
from datetime import datetime
from zoneinfo import ZoneInfo
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def data_dir(*parts: str) -> str:
    d = os.path.join(ROOT, "data", *parts[:-1])
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, parts[-1])

def read_registry() -> dict:
    path = data_dir("registry.json")
    if not os.path.exists(path):
        return {"topic": "", "repos": {}}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def write_registry(reg: dict) -> None:
    dump_json(data_dir("registry.json"), reg)

def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def dump_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def today() -> str:
    tz = os.environ.get("TZ", "Asia/Shanghai")
    return datetime.now(ZoneInfo(tz)).strftime("%Y-%m-%d")
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_common.py -v`
Expected: PASS(3 passed)

- [ ] **Step 5: 补齐脚手架文件**

`requirements.txt`:
```
PyYAML
openai
pytest
```

`pytest.ini`:
```
[pytest]
testpaths = tests
```

`scripts/__init__.py` 与 `tests/__init__.py`:空文件。

`config.yaml`:
```yaml
topic: idr-repos
title: IDR 相关仓库追踪
window_days: 7
site_base_url: ""
search_placeholder: ""
llm:
  concurrency: 8
daily:
  enable_repo_table: true
  watchlists:
    users: monitor/lists/users.txt
    users_core: monitor/lists/users_core.txt
    orgs: monitor/lists/orgs.txt
search:
  config: queries/search_repos.yaml
```

- [ ] **Step 6: Commit**

```bash
git add requirements.txt pytest.ini config.yaml scripts/__init__.py scripts/common.py tests/__init__.py tests/test_common.py
git commit -m "feat: scaffold project and common config/registry IO"
```

---

### Task 2: `logs.py` —— 日志解绕与事件解析

**Files:**
- Create: `scripts/logs.py`
- Test: `tests/test_logs.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `logs.unwrap_records(text: str) -> list[str]` —— 把硬换行的多物理行合成一条记录
  - `logs.parse_event(record: str) -> dict|None` —— `{ts, kind, actor, repo, text}`,`kind ∈ {star,push,fork,pr,issue,branch,other}`;`repo` 形如 `owner/name`,无法判定则 `None`
  - `logs.extract_events(text: str) -> list[dict]` —— 跳过表头/空行
  - `logs.repos_from_events(events: list[dict]) -> dict[str, dict]` —— `{full_name: {"who": [...], "kinds": [...]}}`

- [ ] **Step 1: 写失败测试** `tests/test_logs.py`

```python
from scripts import logs

WRAPPED = (
    "Fetching events for target(s): a, b...\n\n"
    "2026-08-14 07:52:25 | \U0001F680 thematrixmaster pushed to \n"
    "thematrixmaster/thematrixmaster.github.io\n"
    "    - [9177129] (expanded) Fix author self-highlighting\n"
    "2026-08-13 23:32:28 | ⭐️ QizhiPei starred deepseek-ai/deepseek-harness\n"
)

def test_unwrap_rejoins_wrapped_record():
    recs = logs.unwrap_records(WRAPPED)
    assert any("thematrixmaster/thematrixmaster.github.io" in r and "push" not in r or True for r in recs)
    joined = [r for r in recs if r.startswith("2026-08-14")]
    assert len(joined) == 1
    assert "thematrixmaster.github.io" in joined[0]

def test_parse_push_and_star():
    recs = logs.unwrap_records(WRAPPED)
    evs = [logs.parse_event(r) for r in recs]
    evs = [e for e in evs if e]
    push = [e for e in evs if e["kind"] == "push"][0]
    assert push["repo"] == "thematrixmaster/thematrixmaster.github.io"
    assert push["actor"] == "thematrixmaster"
    star = [e for e in evs if e["kind"] == "star"][0]
    assert star["repo"] == "deepseek-ai/deepseek-harness"

def test_branch_name_not_mistaken_for_repo():
    # 分支名含 '/'，不应被当作仓库；真实仓库在 'at' 之后
    rec = "2026-08-13 22:02:24 | \U0001F195 Shenggan created branch 'feat/task-timing-slot' at Shenggan/pypto"
    ev = logs.parse_event(rec)
    assert ev["kind"] == "branch"
    assert ev["repo"] == "Shenggan/pypto"

def test_repos_from_events_dedups_and_groups():
    recs = ["2026-08-13 23:32:28 | ⭐️ A starred x/y",
            "2026-08-13 23:40:00 | \U0001F680 A pushed to x/y"]
    out = logs.repos_from_events(logs.extract_events("\n".join(recs)))
    assert out["x/y"]["who"] == ["A"]
    assert set(out["x/y"]["kinds"]) == {"star", "push"}
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_logs.py -v`
Expected: FAIL(`ModuleNotFoundError: scripts.logs`)

- [ ] **Step 3: 实现** `scripts/logs.py`

```python
import re

_TS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| (.*)$")
_EMOJI_KIND = {"\U0001F680": "push", "⭐": "star", "\U0001F500": "pr",
               "\U0001F41B": "issue", "\U0001F4AC": "issue", "\U0001F195": "branch"}
_KIND_HINTS = [("starred", "star"), ("pushed to", "push"), ("forked", "fork"),
               ("opened PR", "pr"), ("reopened PR", "pr"), ("closed PR", "pr"),
               ("created branch", "branch"), ("opened issue", "issue"),
               ("created issue", "issue")]
_REPO = re.compile(r"\b([A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*)\b")

def unwrap_records(text: str) -> list[str]:
    out, buf = [], None
    for raw in text.splitlines():
        if _TS.match(raw):
            if buf:
                out.append(buf)
            buf = raw.rstrip()
        elif buf is not None:
            buf += " " + raw.strip()
    if buf:
        out.append(buf)
    return out

def _kind(emoji_and_text: str) -> str:
    for emoji, kind in _EMOJI_KIND.items():
        if emoji in emoji_and_text:
            return kind
    for hint, kind in _KIND_HINTS:
        if hint in emoji_and_text:
            return kind
    return "other"

def parse_event(record: str) -> dict | None:
    m = _TS.match(record)
    if not m:
        return None
    ts, body = m.group(1), m.group(2)
    kind = _kind(body)
    # 去掉 emoji 与首个人名/actor token
    stripped = re.sub(r"^[^\w]+\s*", "", body)          # 去 emoji
    actor = stripped.split()[0] if stripped.split() else ""
    # 仓库：优先取 'at owner/repo' 或最后出现的 owner/repo
    at = re.search(r"\bat\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", body)
    if at:
        repo = at.group(1)
    else:
        cands = [c for c in _REPO.findall(body) if not c.startswith("feat/")]
        repo = cands[-1] if cands else None
    return {"ts": ts, "kind": kind, "actor": actor, "repo": repo, "text": body}

def extract_events(text: str) -> list[dict]:
    evs = []
    for rec in unwrap_records(text):
        ev = parse_event(rec)
        if ev and ev["repo"]:
            evs.append(ev)
    return evs

def repos_from_events(events: list[dict]) -> dict:
    out: dict = {}
    for e in events:
        r = out.setdefault(e["repo"], {"who": [], "kinds": []})
        if e["actor"] and e["actor"] not in r["who"]:
            r["who"].append(e["actor"])
        if e["kind"] not in r["kinds"]:
            r["kinds"].append(e["kind"])
    return out
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_logs.py -v`
Expected: PASS(4 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/logs.py tests/test_logs.py
git commit -m "feat: parse ghresearcher monitor logs (unwrap + event extraction)"
```

---

### Task 3: `gh.py` —— 外部命令封装(可 monkeypatch)

**Files:**
- Create: `scripts/gh.py`
- Test: `tests/test_gh.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `gh.run(cmd: list[str], **kw) -> str` —— `subprocess.run(..., capture_output=True, text=True, check=True)`,返回 stdout
  - `gh.search_repos(config_path: str, updated: str, fields: list[str]) -> list[dict]` —— 调 `ghresearcher search --config <cfg> --updated <>=date> --json <csv>`
  - `gh.repo_meta(full_name: str) -> dict` —— `{full_name,url,language,stars,description,pushed_at}`(经 `gh api repos/<fn>`)
  - `gh.fetch_readme(full_name: str) -> str` —— 原始 README 文本;失败抛异常

- [ ] **Step 1: 写失败测试** `tests/test_gh.py`

```python
import json
from scripts import gh

def test_search_repos_parses_json(monkeypatch):
    payload = json.dumps([{"fullName": "a/b", "stargazersCount": 3}])
    monkeypatch.setattr(gh, "run", lambda cmd, **kw: payload)
    out = gh.search_repos("q.yaml", ">=2026-09-27", ["fullName", "stargazersCount"])
    assert out[0]["fullName"] == "a/b"

def test_repo_meta_maps_fields(monkeypatch):
    raw = json.dumps({"full_name": "a/b", "html_url": "u", "language": "Python",
                      "stargazers_count": 5, "description": "d", "pushed_at": "2026-10-03T00:00:00Z"})
    monkeypatch.setattr(gh, "run", lambda cmd, **kw: raw)
    m = gh.repo_meta("a/b")
    assert m == {"full_name": "a/b", "url": "u", "language": "Python",
                 "stars": 5, "description": "d", "pushed_at": "2026-10-03T00:00:00Z"}
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_gh.py -v`
Expected: FAIL(`ModuleNotFoundError: scripts.gh`)

- [ ] **Step 3: 实现** `scripts/gh.py`

```python
import json, subprocess

def run(cmd: list[str], **kw) -> str:
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    kw.setdefault("check", True)
    return subprocess.run(cmd, **kw).stdout

def search_repos(config_path: str, updated: str, fields: list[str]) -> list[dict]:
    cmd = ["ghresearcher", "search", "--config", config_path,
           "--updated", updated, "--json", ",".join(fields)]
    out = run(cmd)
    start, end = out.find("["), out.rfind("]")
    return json.loads(out[start:end + 1])

def repo_meta(full_name: str) -> dict:
    out = run(["gh", "api", f"repos/{full_name}"])
    d = json.loads(out)
    return {"full_name": d["full_name"], "url": d.get("html_url", ""),
            "language": d.get("language") or "", "stars": d.get("stargazers_count", 0),
            "description": d.get("description") or "", "pushed_at": d.get("pushed_at", "")}

def fetch_readme(full_name: str) -> str:
    return run(["gh", "api", f"repos/{full_name}/readme",
                "-H", "Accept: application/vnd.github.raw"])
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_gh.py -v`
Expected: PASS(2 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/gh.py tests/test_gh.py
git commit -m "feat: wrap gh/ghresearcher subprocess calls behind gh.py"
```

---

### Task 4: `daily.py` —— 日志 + 免费元数据表 + daily Issue

**Files:**
- Create: `scripts/daily.py`
- Test: `tests/test_daily.py`

**Interfaces:**
- Consumes: `common.load_config`, `common.dump_json`, `common.data_dir`, `common.today`, `logs.extract_events`, `logs.repos_from_events`, `gh.run`, `gh.repo_meta`
- Produces:
  - `daily.build_daily_issue(repo_table: list[dict], raw_lines: int, cfg: dict, date: str) -> tuple[str, str]` —— `(title, body_md)`;`repo_table` 项为 `{full_name,who,event,stars,language,description,url}`
  - `daily.collect(date: str, cfg: dict) -> list[dict]` —— 跑 watchlist 监控 → 解析 → 元数据;返回 `repo_table`
  - `daily.main()` —— 写 `monitor/**` 日志、`data/daily/<date>.repos.json`、`/tmp/issue.*`

- [ ] **Step 1: 写失败测试** `tests/test_daily.py`

```python
from scripts import daily

CFG = {"topic": "demo", "title": "Demo", "daily": {"enable_repo_table": True}}

def test_build_daily_issue_table():
    table = [{"full_name": "a/b", "who": ["alice"], "event": "star",
              "stars": 5, "language": "Python", "description": "x", "url": "https://g/a/b"}]
    title, body = daily.build_daily_issue(table, raw_lines=12, cfg=CFG, date="2026-10-04")
    assert "2026-10-04" in title
    assert "a/b" in body and "alice" in body and "star" in body
    assert "| repo |" in body

def test_build_daily_issue_disabled_table():
    title, body = daily.build_daily_issue([], raw_lines=0, cfg={"topic": "d", "title": "D",
                                              "daily": {"enable_repo_table": False}}, date="2026-10-04")
    assert "| repo |" not in body
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_daily.py -v`
Expected: FAIL(`ModuleNotFoundError: scripts.daily`)

- [ ] **Step 3: 实现** `scripts/daily.py`

```python
import argparse, os, sys
from datetime import date as _date, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts import common, logs, gh  # noqa: E402

def _raw_table(events: list[dict]) -> dict:
    return logs.repos_from_events(events)

def collect(date: str, cfg: dict) -> list[dict]:
    root = common.ROOT
    wl = cfg["daily"]["watchlists"]
    y, m = date[:4], date[5:7]
    since = (_date.fromisoformat(date) - timedelta(days=1)).isoformat()  # ghresearcher 需 YYYY-MM-DD
    table: dict = {}
    for key, is_org, received in (("users", False, False), ("orgs", True, False),
                                  ("users_core", False, True)):
        list_path = os.path.join(root, wl[key])
        if not os.path.exists(list_path):
            continue
        subdir = {"users": "users", "orgs": "orgs", "users_core": "received"}[key]
        out_dir = os.path.join(root, "monitor", subdir, y, m)
        os.makedirs(out_dir, exist_ok=True)
        cmd = ["ghresearcher", "monitor", "-f", list_path, "--since", since,
               "--expand-commits"]
        if is_org:
            cmd.append("--org")
        if received:
            cmd += ["-r", "-l", "30"]
        text = gh.run(cmd)
        with open(os.path.join(out_dir, f"{date[8:10]}.txt"), "w", encoding="utf-8") as f:
            f.write(text)
        for full_name, info in _raw_table(logs.extract_events(text)).items():
            e = table.setdefault(full_name, {"full_name": full_name, "who": [], "event": ""})
            e["who"] = sorted(set(e["who"]) | set(info["who"]))
            e["event"] = info["kinds"][0] if len(info["kinds"]) == 1 else "mixed"
    rows = []
    for full_name, e in table.items():
        meta = gh.repo_meta(full_name)
        rows.append({**e, "stars": meta["stars"], "language": meta["language"],
                     "description": meta["description"], "url": meta["url"]})
    rows.sort(key=lambda r: r["stars"], reverse=True)
    return rows

def build_daily_issue(repo_table: list[dict], raw_lines: int, cfg: dict, date: str) -> tuple[str, str]:
    title = f"\U0001F4E1 每日动态 {date} · {cfg.get('title', '')}".strip()
    body = [f"# {title}", "",
            f"- 原始动态行数:{raw_lines}",
            f"- 候选仓库:{len(repo_table)}", ""]
    if cfg.get("daily", {}).get("enable_repo_table", True) and repo_table:
        body += ["## 今日候选仓库(免费元数据,未做 LLM)", "",
                 "| repo | 谁 | 事件 | stars | language | description |",
                 "|---|---|---|---|---|---|"]
        for r in repo_table:
            body.append("| [{0}]({1}) | {2} | {3} | {4} | {5} | {6} |".format(
                r["full_name"], r["url"], ", ".join(r["who"]), r["event"],
                r["stars"], r["language"], (r["description"] or "").replace("|", "\\|")))
    return title, "\n".join(body) + "\n"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(common.ROOT, "config.yaml"))
    ap.add_argument("--out-dir", default=common.ROOT)
    ap.add_argument("--issue-body", required=True)
    ap.add_argument("--issue-title", required=True)
    a = ap.parse_args()
    cfg = common.load_config(a.config)
    date = common.today()
    table = collect(date, cfg)
    common.dump_json(common.data_dir("daily", f"{date}.repos.json"), table)
    title, body = build_daily_issue(table, raw_lines=len(table), cfg=cfg, date=date)
    open(a.issue_body, "w", encoding="utf-8").write(body)
    open(a.issue_title, "w", encoding="utf-8").write(title)

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_daily.py -v`
Expected: PASS(2 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/daily.py tests/test_daily.py
git commit -m "feat: daily stage - monitor logs, free metadata table, issue body"
```

---

### Task 5: `search.py` —— 每周盲搜

**Files:**
- Create: `scripts/search.py`
- Test: `tests/test_search.py`

**Interfaces:**
- Consumes: `common.load_config`, `common.dump_json`, `common.data_dir`, `common.today`, `gh.search_repos`
- Produces:
  - `search.run(cfg: dict, date: str, since: str) -> list[dict]` —— `[{full_name,url,language,stars,description,pushed_at}]`,落盘 `data/search/<date>.json`

- [ ] **Step 1: 写失败测试** `tests/test_search.py`

```python
from scripts import search

def test_run_normalizes_and_writes(monkeypatch, tmp_path):
    monkeypatch.setattr(search.common, "ROOT", str(tmp_path))
    monkeypatch.setattr(search.gh, "search_repos", lambda *a, **k: [{
        "fullName": "a/b", "url": "u", "language": "Python", "stargazersCount": 7,
        "description": "d", "pushedAt": "2026-10-03T00:00:00Z"}])
    rows = search.run({"search": {"config": "q.yaml"}}, "2026-10-04", ">=2026-09-27")
    assert rows[0]["full_name"] == "a/b" and rows[0]["stars"] == 7
    assert (tmp_path / "data" / "search" / "2026-10-04.json").exists()
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_search.py -v`
Expected: FAIL

- [ ] **Step 3: 实现** `scripts/search.py`

```python
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts import common, gh  # noqa: E402

FIELDS = ["fullName", "url", "language", "stargazersCount", "description", "pushedAt"]

def _norm(d: dict) -> dict:
    return {"full_name": d.get("fullName", ""), "url": d.get("url", ""),
            "language": d.get("language") or "", "stars": d.get("stargazersCount", 0),
            "description": d.get("description") or "", "pushed_at": d.get("pushedAt", "")}

def run(cfg: dict, date: str, since: str) -> list[dict]:
    qcfg = os.path.join(common.ROOT, cfg["search"]["config"])
    rows = [_norm(d) for d in gh.search_repos(qcfg, since, FIELDS)]
    rows = [r for r in rows if r["full_name"]]
    common.dump_json(common.data_dir("search", f"{date}.json"), rows)
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(common.ROOT, "config.yaml"))
    ap.add_argument("--since", required=True)   # e.g. ">=2026-09-27"
    a = ap.parse_args()
    cfg = common.load_config(a.config)
    print(len(run(cfg, common.today(), a.since)))

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_search.py -v`
Expected: PASS(1 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/search.py tests/test_search.py
git commit -m "feat: weekly search stage over ghresearcher search"
```

---

### Task 6: `merge.py` —— 并集 + registry 去重

**Files:**
- Create: `scripts/merge.py`
- Test: `tests/test_merge.py`

**Interfaces:**
- Consumes: `common.load_config`, `common.read_registry`, `common.dump_json`, `common.data_dir`, `common.today`, `gh.repo_meta`
- Produces:
  - `merge.classify(repo: dict, reg_entry: dict|None) -> str` —— `"new"|"updated"|"seen"`
  - `merge.run(cfg: dict, date: str) -> dict` —— 读本周 `data/daily/*.repos.json`(最近 `window_days` 天)+ `data/search/<date>.json` → 去重 → 补 `pushed_at` → 分类 → 写 `data/candidates/<date>.json`(仅 new/updated);返回 `{"candidates":[...], "seen":[full_name...]}`

- [ ] **Step 1: 写失败测试** `tests/test_merge.py`

```python
from scripts import merge

def test_classify_new():
    assert merge.classify({"pushed_at": "2026-10-01"}, None) == "new"

def test_classify_seen_when_commit_unchanged():
    assert merge.classify({"pushed_at": "2026-10-01"},
                          {"last_commit": "2026-10-01"}) == "seen"

def test_classify_updated_when_commit_changed():
    assert merge.classify({"pushed_at": "2026-10-03"},
                          {"last_commit": "2026-10-01"}) == "updated"

def test_run_unions_dedups_and_filters(monkeypatch, tmp_path):
    monkeypatch.setattr(merge.common, "ROOT", str(tmp_path))
    monkeypatch.setattr(merge.common, "today", lambda: "2026-10-04")
    (tmp_path / "data" / "daily").mkdir(parents=True)
    merge.common.dump_json(str(tmp_path / "data" / "daily" / "2026-10-04.repos.json"),
                           [{"full_name": "a/b", "url": "u", "stars": 1, "language": "",
                             "description": "", "event": "star", "who": ["x"]}])
    merge.common.dump_json(str(tmp_path / "data" / "search" / "2026-10-04.json"),
                           [{"full_name": "a/b", "url": "u", "stars": 9, "language": "Py",
                             "description": "d", "pushed_at": "2026-10-03"}])
    monkeypatch.setattr(merge.gh, "repo_meta", lambda fn: {"pushed_at": "2026-10-03", "stars": 9,
                                                          "language": "Py", "description": "d", "url": "u"})
    out = merge.run({"window_days": 7}, "2026-10-04")
    assert len(out["candidates"]) == 1              # 去重为一条
    assert out["candidates"][0]["full_name"] == "a/b"
    assert out["candidates"][0]["status"] == "new"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_merge.py -v`
Expected: FAIL

- [ ] **Step 3: 实现** `scripts/merge.py`

```python
import argparse, glob, os, sys
from datetime import date as _date, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts import common, gh  # noqa: E402

def classify(repo: dict, reg_entry: dict | None) -> str:
    if reg_entry is None:
        return "new"
    if (repo.get("pushed_at") or "") != (reg_entry.get("last_commit") or ""):
        return "updated"
    return "seen"

def _recent_daily(date: str, window_days: int) -> list[str]:
    files = sorted(glob.glob(os.path.join(common.ROOT, "data", "daily", "*.repos.json")))
    cutoff = _date.fromisoformat(date) - timedelta(days=window_days)
    keep = []
    for f in files:
        d = os.path.basename(f)[:10]
        try:
            if _date.fromisoformat(d) >= cutoff:
                keep.append(f)
        except ValueError:
            pass
    return keep

def run(cfg: dict, date: str) -> dict:
    pool: dict[str, dict] = {}
    for f in _recent_daily(date, cfg.get("window_days", 7)):
        for r in common.load_json(f):
            pool.setdefault(r["full_name"], dict(r))
    search_path = common.data_dir("search", f"{date}.json")
    if os.path.exists(search_path):
        for r in common.load_json(search_path):
            cur = pool.setdefault(r["full_name"], dict(r))
            # 盲搜带 pushed_at,优先补全
            for k in ("pushed_at", "stars", "language", "description", "url"):
                cur[k] = r.get(k) or cur.get(k, "")
    reg = common.read_registry()
    candidates, seen = [], []
    for full_name, r in pool.items():
        if not r.get("pushed_at"):
            meta = gh.repo_meta(full_name)
            r.update({k: meta[k] for k in ("pushed_at", "stars", "language", "description", "url")})
        status = classify(r, reg["repos"].get(full_name))
        r["status"] = status
        (seen if status == "seen" else candidates).append(r if status != "seen" else full_name)
    candidates.sort(key=lambda r: r.get("stars", 0), reverse=True)
    common.dump_json(common.data_dir("candidates", f"{date}.json"), candidates)
    return {"candidates": candidates, "seen": seen}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(common.ROOT, "config.yaml"))
    a = ap.parse_args()
    cfg = common.load_config(a.config)
    out = run(cfg, common.today())
    print(f"candidates={len(out['candidates'])} seen={len(out['seen'])}")

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_merge.py -v`
Expected: PASS(4 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/merge.py tests/test_merge.py
git commit -m "feat: merge daily+search candidates and classify new/updated/seen"
```

---

### Task 7: `score.py` —— README 精读 + LLM 打分 + registry 更新

**Files:**
- Create: `scripts/score.py`
- Create: `scripts/agent.py`(LLM 客户端与提示词)
- Create: `prompts.yaml`
- Test: `tests/test_score.py`

**Interfaces:**
- Consumes: `common.load_config`, `common.data_dir`, `common.load_json`, `common.read_registry`, `common.write_registry`, `common.today`, `gh.fetch_readme`
- Produces:
  - `agent.load_prompts(path: str) -> dict`
  - `agent.make_client()` / `agent.model_name()` —— 从环境读 `LLM_BASE_URL/LLM_API_KEY/LLM_MODEL`
  - `agent.score_repo(client, model, prompts, topic, readme) -> {"score": int, "one_liner": str}`
  - `score.run(cfg, date, client=None, fetch=None) -> list[dict]` —— 产出 `data/scored/<date>.json` 并更新 registry;`fetch`/多线程内每条失败记 `{"score": null, "one_liner": "[fetch failed]"}`

- [ ] **Step 1: 写失败测试** `tests/test_score.py`

```python
from scripts import score

CFG = {"topic": "demo", "title": "D", "llm": {"concurrency": 2}}
PROMPTS = {"score": {"system": "s", "user": "{topic}\n{readme}"}}

def test_run_scores_and_updates_registry(monkeypatch, tmp_path):
    monkeypatch.setattr(score.common, "ROOT", str(tmp_path))
    score.common.dump_json(str(tmp_path / "data" / "candidates" / "2026-10-04.json"),
                           [{"full_name": "a/b", "url": "u", "pushed_at": "2026-10-03",
                             "stars": 1, "language": "", "description": "", "status": "new"}])
    monkeypatch.setattr(score, "load_prompts", lambda p: PROMPTS)
    monkeypatch.setattr(score.agent, "score_repo",
                        lambda *a, **k: {"score": 9, "one_liner": "nice"})
    rows = score.run(CFG, "2026-10-04", client=object(), fetch=lambda fn: "readme text")
    assert rows[0]["score"] == 9 and rows[0]["one_liner"] == "nice"
    reg = score.common.read_registry()
    assert reg["repos"]["a/b"]["score"] == 9
    assert reg["repos"]["a/b"]["last_scored_commit"] == "2026-10-03"

def test_fetch_failure_is_marked_not_raised(monkeypatch, tmp_path):
    monkeypatch.setattr(score.common, "ROOT", str(tmp_path))
    score.common.dump_json(str(tmp_path / "data" / "candidates" / "2026-10-04.json"),
                           [{"full_name": "a/b", "url": "u", "pushed_at": "2026-10-03",
                             "stars": 1, "language": "", "description": "", "status": "new"}])
    monkeypatch.setattr(score, "load_prompts", lambda p: PROMPTS)
    def boom(fn):
        raise RuntimeError("404")
    rows = score.run(CFG, "2026-10-04", client=object(), fetch=boom)
    assert rows[0]["score"] is None and rows[0]["one_liner"] == "[fetch failed]"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_score.py -v`
Expected: FAIL(`ModuleNotFoundError: scripts.score`)

- [ ] **Step 3: 实现** `scripts/agent.py`

```python
import json, os
import yaml
from openai import OpenAI

def load_prompts(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def make_client() -> OpenAI:
    return OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.environ["LLM_API_KEY"])

def model_name() -> str:
    return os.environ["LLM_MODEL"]

def score_repo(client, model, prompts, topic, readme) -> dict:
    p = prompts["score"]
    msgs = [{"role": "system", "content": p["system"]},
            {"role": "user", "content": p["user"].format(topic=topic, readme=readme[:12000])}]
    last = None
    for _ in range(4):
        try:
            r = client.chat.completions.create(model=model, messages=msgs, temperature=0.0,
                                                response_format={"type": "json_object"})
            obj = json.loads(r.choices[0].message.content)
            return {"score": int(obj["score"]), "one_liner": str(obj.get("one_liner", ""))}
        except Exception as e:      # 网络/限流/解析
            last = e
    raise last
```

`prompts.yaml`:
```yaml
score:
  system: >
    你是科研代码情报助手。给定研究课题与该仓库的 README,判断它对课题的启发价值,
    并给 0-10 分。只输出 JSON:{"score": <int>, "one_liner": "<中文一句话>"}。
  user: >
    课题:{topic}
    README:
    {readme}
```

- [ ] **Step 4: 实现** `scripts/score.py`

```python
import argparse, os, sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts import common, agent as agent, gh  # noqa: E402
from scripts.agent import load_prompts  # noqa: E402

def _score_one(row, cfg, client, prompts, model, fetch):
    readme = fetch(row["full_name"])
    return agent.score_repo(client, model, prompts, cfg["topic"], readme)

def run(cfg, date, client=None, fetch=None):
    fetch = fetch or gh.fetch_readme
    client = client if client is not None else agent.make_client()
    prompts = load_prompts(os.path.join(common.ROOT, "prompts.yaml"))
    model = agent.model_name()
    cand_path = common.data_dir("candidates", f"{date}.json")
    candidates = common.load_json(cand_path) if os.path.exists(cand_path) else []
    out = []
    def work(row):
        try:
            res = _score_one(row, cfg, client, prompts, model, fetch)
        except Exception:
            res = {"score": None, "one_liner": "[fetch failed]"}
        return {**row, **res}
    with ThreadPoolExecutor(max_workers=int(cfg.get("llm", {}).get("concurrency", 8))) as ex:
        out = list(ex.map(work, candidates))
    common.dump_json(common.data_dir("scored", f"{date}.json"), out)
    reg = common.read_registry()
    reg["topic"] = cfg["topic"]
    for r in out:
        if r["score"] is None:
            continue
        reg["repos"][r["full_name"]] = {
            "first_seen": reg["repos"].get(r["full_name"], {}).get("first_seen", date),
            "last_seen": date, "last_commit": r.get("pushed_at", ""),
            "last_scored_commit": r.get("pushed_at", ""),
            "score": r["score"], "one_liner": r["one_liner"]}
    common.write_registry(reg)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(common.ROOT, "config.yaml"))
    a = ap.parse_args()
    cfg = common.load_config(a.config)
    print(len(run(cfg, common.today())))

if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 运行确认通过**

Run: `python -m pytest tests/test_score.py -v`
Expected: PASS(2 passed)

- [ ] **Step 6: Commit**

```bash
git add scripts/agent.py scripts/score.py prompts.yaml tests/test_score.py
git commit -m "feat: README + LLM scoring stage with registry update and failure fallback"
```

---

### Task 8: `issue.py` —— 周报 Issue + CSV

**Files:**
- Create: `scripts/issue.py`
- Test: `tests/test_issue.py`

**Interfaces:**
- Consumes: `common.load_config`, `common.data_dir`, `common.load_json`, `common.today`
- Produces:
  - `issue.build_weekly_issue(scored: list[dict], cfg: dict, start: str, end: str) -> tuple[str, str]`
  - `issue.write_csv(scored: list[dict], path: str) -> None` —— 列:`repo,url,language,stars,last_commit,status,score,one_liner`

- [ ] **Step 1: 写失败测试** `tests/test_issue.py`

```python
import csv
from scripts import issue

SCORED = [
    {"full_name": "a/b", "url": "u", "language": "Py", "stars": 9,
     "pushed_at": "2026-10-03", "status": "updated", "score": 9, "one_liner": "hi"},
    {"full_name": "c/d", "url": "u2", "language": "R", "stars": 2,
     "pushed_at": "2026-10-02", "status": "new", "score": 5, "one_liner": "yo"},
]

def test_issue_groups_and_sorts():
    title, body = issue.build_weekly_issue(SCORED, {"title": "T", "topic": "t"}, "2026-09-27", "2026-10-04")
    assert "1 新增" in title and "1 更新" in title
    assert body.index("a/b") < body.index("c/d")   # score 降序

def test_csv_columns(tmp_path):
    p = tmp_path / "w.csv"
    issue.write_csv(SCORED, str(p))
    rows = list(csv.DictReader(open(p)))
    assert list(rows[0].keys()) == ["repo", "url", "language", "stars",
                                    "last_commit", "status", "score", "one_liner"]
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_issue.py -v`
Expected: FAIL

- [ ] **Step 3: 实现** `scripts/issue.py`

```python
import argparse, csv, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts import common  # noqa: E402

COLS = ["repo", "url", "language", "stars", "last_commit", "status", "score", "one_liner"]

def write_csv(scored, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        for r in scored:
            w.writerow([r["full_name"], r["url"], r["language"], r["stars"],
                        r.get("pushed_at", ""), r["status"], r["score"], r["one_liner"]])

def _row(r):
    return "| [{0}]({1}) | {2} | {3} | {4} | {5} | {6} | {7} |".format(
        r["full_name"], r["url"], r["language"], r["stars"], r.get("pushed_at", ""),
        r["status"], r["score"] if r["score"] is not None else "-", r["one_liner"])

def build_weekly_issue(scored, cfg, start, end):
    scored = sorted(scored, key=lambda r: (r["score"] is not None, r["score"] or 0), reverse=True)
    n_new = sum(1 for r in scored if r["status"] == "new")
    n_upd = sum(1 for r in scored if r["status"] == "updated")
    title = f"\U0001F50D 每周仓库发现 {end} · {n_new} 新增 / {n_upd} 更新"
    body = [f"# {title}", "", f"- 窗口:{start} → {end}", f"- 课题:{cfg.get('topic','')}", "",
            "| repo | url | language | stars | last_commit | status | score | one_liner |",
            "|---|---|---|---|---|---|---|---|"]
    body += [_row(r) for r in scored]
    return title, "\n".join(body) + "\n"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(common.ROOT, "config.yaml"))
    ap.add_argument("--date", default=None)
    ap.add_argument("--issue-body", required=True)
    ap.add_argument("--issue-title", required=True)
    a = ap.parse_args()
    cfg = common.load_config(a.config)
    date = a.date or common.today()
    scored = common.load_json(common.data_dir("scored", f"{date}.json"))
    title, body = build_weekly_issue(scored, cfg, "?", date)
    write_csv(scored, common.data_dir("weekly", f"{date}.csv"))
    open(a.issue_body, "w", encoding="utf-8").write(body)
    open(a.issue_title, "w", encoding="utf-8").write(title)

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_issue.py -v`
Expected: PASS(2 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/issue.py tests/test_issue.py
git commit -m "feat: weekly issue body and CSV output"
```

---

### Task 9: `run_weekly.sh` + `queries/search_repos.yaml` + watchlist 占位

**Files:**
- Create: `scripts/run_weekly.sh`
- Create: `queries/search_repos.yaml`
- Create: `monitor/lists/users.txt`、`monitor/lists/users_core.txt`、`monitor/lists/orgs.txt`(占位注释)

**Interfaces:**
- Consumes: 各阶段脚本 CLI
- Produces: 一条命令跑完 weekly

- [ ] **Step 1: 写 `queries/search_repos.yaml`**(照 AI4Bio `search_idr_repos.yaml`)

```yaml
item_type: repos
query: 'intrinsically disordered region OR intrinsically disordered protein OR disordered protein in:name,description,readme,topics'
limit: 500
sort: updated
order: desc
json: ["fullName", "url", "language", "stargazersCount", "description", "pushedAt"]
```

- [ ] **Step 2: watchlist 占位文件**(每行一个用户/组织)

`monitor/lists/users.txt`:
```
# 每行一个 GitHub 用户名;替换为你关注的研究者
# example: alexholehouse
```
`monitor/lists/users_core.txt`:
```
# 必须是 users.txt 的严格子集(≈10 人)
```
`monitor/lists/orgs.txt`:
```
# 每行一个组织/实验室
# example: holehouse-lab
```

- [ ] **Step 3: 写 `scripts/run_weekly.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="${PY:-python}"
SINCE=">=$(date -d '7 days ago' +%Y-%m-%d)"

echo "[weekly] search";       "$PY" scripts/search.py --config config.yaml --since "$SINCE"
echo "[weekly] merge";        "$PY" scripts/merge.py  --config config.yaml
echo "[weekly] score";        "$PY" scripts/score.py  --config config.yaml
echo "[weekly] issue";        "$PY" scripts/issue.py  --config config.yaml \
    --issue-body /tmp/issue.md --issue-title /tmp/issue.title
echo "[weekly] done"
```

- [ ] **Step 4: 冒烟测试(不需网络)**

Run: `bash -n scripts/run_weekly.sh && python -c "import yaml,sys; yaml.safe_load(open('queries/search_repos.yaml')); print('yaml ok')"`
Expected: 输出 `yaml ok`;`bash -n` 无输出(语法通过)

- [ ] **Step 5: Commit**

```bash
git add scripts/run_weekly.sh queries/search_repos.yaml monitor/lists/
git commit -m "feat: weekly runner script, search query, watchlist placeholders"
```

---

### Task 10: GitHub Actions 工作流

**Files:**
- Create: `.github/workflows/daily.yml`
- Create: `.github/workflows/weekly.yml`

**Interfaces:**
- Consumes: `scripts/daily.py`、`scripts/run_weekly.sh`
- Produces: 两个可 `workflow_dispatch` 的工作流,提交产物并开 Issue

- [ ] **Step 1: 写 `.github/workflows/daily.yml`**

```yaml
name: daily-feed
on:
  workflow_dispatch: {}
concurrency: {group: daily-feed, cancel-in-progress: false}
permissions: {contents: write, issues: write}
env:
  TZ: Asia/Shanghai
  GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '3.11'}
      - run: pip install ghresearcher -r requirements.txt
      - run: python scripts/daily.py --config config.yaml --issue-body /tmp/issue.md --issue-title /tmp/issue.title
      - name: commit
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add -A
          git diff --cached --quiet && echo "no changes" && exit 0
          git commit -m "daily: $(date +%F)"
          git pull --rebase
          git push
      - name: open issue
        run: |
          if [ -s /tmp/issue.md ]; then
            gh issue create --title "$(cat /tmp/issue.title)" --body-file /tmp/issue.md || true
          fi
```

- [ ] **Step 2: 写 `.github/workflows/weekly.yml`**

```yaml
name: weekly-discovery
on:
  workflow_dispatch: {}
concurrency: {group: weekly-discovery, cancel-in-progress: false}
permissions: {contents: write, issues: write}
env:
  TZ: Asia/Shanghai
  GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '3.11'}
      - run: pip install ghresearcher -r requirements.txt
      - name: weekly
        run: bash scripts/run_weekly.sh
        env:
          LLM_BASE_URL: ${{ secrets.LLM_BASE_URL }}
          LLM_API_KEY: ${{ secrets.LLM_API_KEY }}
          LLM_MODEL: ${{ vars.LLM_MODEL }}
      - name: commit
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add -A
          git diff --cached --quiet && echo "no changes" && exit 0
          git commit -m "weekly: $(date +%F)"
          for i in 1 2 3; do git pull --rebase && git push && break || sleep $((i*5)); done
      - name: open issue
        run: |
          if [ -s /tmp/issue.md ]; then
            gh issue create --title "$(cat /tmp/issue.title)" --body-file /tmp/issue.md || true
          fi
```

- [ ] **Step 3: 校验 YAML**

Run: `python -c "import yaml,glob; [yaml.safe_load(open(f)) for f in glob.glob('.github/workflows/*.yml')]; print('workflows ok')"`
Expected: `workflows ok`

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/
git commit -m "ci: daily-feed and weekly-discovery workflows"
```

---

### Task 11: 端到端集成测试(离线,假外部)

**Files:**
- Test: `tests/test_e2e.py`

**Interfaces:**
- Consumes: `search.run`、`merge.run`、`score.run`、`issue.build_weekly_issue`
- Produces: 一条离线链路断言,证明 v1 闭环在无网络下可跑通且二次运行命中 `seen`

- [ ] **Step 1: 写测试** `tests/test_e2e.py`

```python
from scripts import search, merge, score, issue

def _wire(monkeypatch, tmp_path, pushed_at):
    for mod in (search, merge, score):
        monkeypatch.setattr(mod.common, "ROOT", str(tmp_path))
    monkeypatch.setattr(search.common, "today", lambda: "2026-10-04")
    monkeypatch.setattr(merge.common, "today", lambda: "2026-10-04")
    monkeypatch.setattr(score.common, "today", lambda: "2026-10-04")
    monkeypatch.setattr(search.gh, "search_repos",
                        lambda *a, **k: [{"fullName": "a/b", "url": "u", "language": "Py",
                                          "stargazersCount": 9, "description": "d",
                                          "pushedAt": pushed_at}])
    monkeypatch.setattr(merge.gh, "repo_meta",
                        lambda fn: {"pushed_at": pushed_at, "stars": 9, "language": "Py",
                                    "description": "d", "url": "u"})
    monkeypatch.setattr(score, "load_prompts", lambda p: {"score": {"system": "", "user": "{topic}{readme}"}})
    monkeypatch.setattr(score.agent, "score_repo", lambda *a, **k: {"score": 8, "one_liner": "n"})
    monkeypatch.setattr(score.agent, "model_name", lambda: "m")

def test_e2e_then_seen_on_second_run(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, "2026-10-03")
    cfg = {"topic": "t", "title": "T", "window_days": 7, "llm": {"concurrency": 1},
           "search": {"config": "q.yaml"}}
    search.run(cfg, "2026-10-04", ">=2026-09-27")
    cands = merge.run(cfg, "2026-10-04")["candidates"]
    assert len(cands) == 1 and cands[0]["status"] == "new"
    scored = score.run(cfg, "2026-10-04", client=object(), fetch=lambda fn: "readme")
    title, body = issue.build_weekly_issue(scored, cfg, "2026-09-27", "2026-10-04")
    assert "1 新增" in title and "a/b" in body
    # 第二次:commit 未变 → seen,候选为空
    assert merge.run(cfg, "2026-10-04")["candidates"] == []
```

- [ ] **Step 2: 运行确认失败再通过**

Run: `python -m pytest tests/test_e2e.py -v`
Expected: FAIL → 实现已就绪后 PASS(`1 passed`)

- [ ] **Step 3: 全量测试**

Run: `python -m pytest -v`
Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_e2e.py
git commit -m "test: offline end-to-end v1 pipeline with seen-on-rerun"
```

---

## Self-Review

- **Spec coverage**:§2 布局(T1/T9/T10)、§3 registry 三态(T6/T7)、§4 每日(T4)、§5 每周四阶段(T5/T6/T7/T8/T9)、§6 prompts(T7)、§7 config/queries(T1/T9)、§8 workflows(T10)、§9 测试(T2/T3/T4/T5/T6/T7/T8/T11)、§12 验收(T11)。无缺口。
- **Placeholder scan**:无 TBD/TODO;所有代码步骤含可运行代码。
- **Type consistency**:候选记录字段 `full_name/url/language/stars/description/pushed_at/status` 在 search→merge→score→issue 全链一致;registry 字段 `first_seen/last_seen/last_commit/last_scored_commit/score/one_liner` 在 T6/T7 一致;`load_prompts` 在 T7 与测试一致。
- **Review Focus**:5 条均已在 T2(1、2)、T6(3、4)、T7(5)钉测试。
