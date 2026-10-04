# Daily-Code-Agent-Template v2 归档阶段 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 v1 每周流水线的 score 与 issue 之间插入归档阶段:对 `score >= min_score` 的仓库用 degit 浅克隆 + repowiki-cli 导出三种 wiki,落在 gitignored 的 `code/` 下,并产出 `data/archive/<date>.json` 元数据。

**Architecture:** 新增单文件 `scripts/archive.py`(纯函数 + 可注入的外部命令调用),复用 v1 的 `common.py`(config/路径/日期/JSON)。外部命令(degit / repowiki-cli)通过 `subprocess.run` 封装并逐项 try/except 隔离失败。`run(cfg, date, clone=None, wiki=None)` 采用与 `score.py` 相同的注入式签名,便于离线测试。归档目录 `code/` 已 gitignore,不提交。

**Tech Stack:** Python 3.11;`degit`(node CLI)浅克隆;`repowiki-cli`(PyPI `pyrepowiki-cli`)导出 DeepWiki/Google Code Wiki/zread;pytest + PyYAML。

**Spec:** `docs/superpowers/specs/2026-10-05-daily-code-agent-template-v2-design.md`

## Global Constraints

- 复用 `common.py` 的 `load_config` / `data_dir` / `load_json` / `dump_json` / `today` / `ROOT`,不重复实现。
- 测试**不联网**:所有外部命令(degit / repowiki-cli)调用经 `subprocess.run` 或注入的 `clone`/`wiki` 函数,测试里 monkeypatch。
- 单仓库、单 wiki 失败均**隔离**(记 `false`),绝不拖垮整阶段(对齐 v1「单条失败不拖垮整周」)。
- `code/` 保持 gitignored(已在 `.gitignore`);归档阶段只提交 `data/archive/<date>.json`。
- **提交约定**:使用仓库已配置身份 `Joe Hoye Dow <luxunisgod123@gmail.com>`,**绝不追加任何 `Co-Authored-By:` 行**。

## Review Focus

以下五类输入/失败模式是 spec 隐含但默认任务测试未必覆盖的,最可能咬人(最可能先):

1. `config.yaml` 缺失 `llm.min_score`(旧配置)→ `run` 应回退默认 5,而不是 KeyError。→ Task 1 加 `test_run_defaults_min_score_when_absent`。
2. `data/scored/<date>.json` 不存在或全被门槛过滤(空)→ 写空 `[]` 不崩溃、不调用任何外部命令。→ Task 1 加 `test_run_missing_scored_yields_empty`。
3. CI 里 `degit` / `repowiki-cli` 未安装 → 归档阶段在 `set -euo pipefail` 下直接中断整周。→ Task 3 在 weekly.yml 安装两者,并做 sanity 校验。
4. 某 wiki 来源对某仓库无条目(repowiki-cli 非零退出)→ 记 `false`,其余来源与其它仓库继续。→ Task 1 的 `test_run_isolates_wiki_failure` 已覆盖。
5. 克隆目标仓库已存在旧档(updated 复现)→ 归档前清空,覆盖旧文件,不残留陈旧文件。→ Task 1 的 `test_run_overwrites_existing_dir` 已覆盖。

---

### Task 1: `scripts/archive.py` 归档阶段 + 测试

**Files:**
- Create: `scripts/archive.py`
- Test: `tests/test_archive.py`

**Interfaces:**
- Consumes: `common.load_config`, `common.data_dir`, `common.load_json`, `common.dump_json`, `common.today`, `common.ROOT`(均来自 v1 `scripts/common.py`)
- Produces(供 Task 2 的 `run_weekly.sh` 与后续 v3 依赖):
  - `archive.threshold(scored: list[dict], min_score: int) -> list[dict]`
  - `archive.repo_dir(full_name: str) -> str`
  - `archive.clone_repo(full_name: str, dest: str) -> bool`
  - `archive.export_wiki(source: str, full_name: str, dest: str) -> bool`
  - `archive.archive_one(row: dict, clone, wiki) -> dict`
  - `archive.run(cfg: dict, date: str, clone=None, wiki=None) -> list[dict]`
  - `archive.main()` — argparse `--config`(默认 `config.yaml`)、`--date`(默认 `common.today()`)

- [ ] **Step 1: 写失败测试** `tests/test_archive.py`

```python
import os
from scripts import archive

def test_threshold_filters_and_sorts():
    scored = [
        {"full_name": "a/b", "score": 3},
        {"full_name": "c/d", "score": 9},
        {"full_name": "e/f", "score": None},
        {"full_name": "g/h", "score": 5},
    ]
    out = archive.threshold(scored, 5)
    assert [r["full_name"] for r in out] == ["c/d", "g/h"]

def test_repo_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(archive.common, "ROOT", str(tmp_path))
    assert archive.repo_dir("MaybeBio/GhResearcher") == str(tmp_path / "code" / "MaybeBio__GhResearcher")

def test_run_archives_only_threshold(monkeypatch, tmp_path):
    monkeypatch.setattr(archive.common, "ROOT", str(tmp_path))
    scored = [
        {"full_name": "hi/a", "score": 9, "one_liner": "x", "pushed_at": "t"},
        {"full_name": "lo/b", "score": 2, "one_liner": "y", "pushed_at": "t"},
    ]
    archive.common.dump_json(str(tmp_path / "data" / "scored" / "2026-10-05.json"), scored)
    clone_calls, wiki_calls = [], []
    out = archive.run({"llm": {"min_score": 5}}, "2026-10-05",
                      clone=lambda fn, d: clone_calls.append(fn) or True,
                      wiki=lambda s, fn, d: wiki_calls.append((s, fn)) or True)
    assert [r["full_name"] for r in out] == ["hi/a"]
    assert clone_calls == ["hi/a"]
    assert sorted(s for s, _ in wiki_calls) == ["codewiki", "deepwiki", "zread"]
    saved = archive.common.load_json(str(tmp_path / "data" / "archive" / "2026-10-05.json"))
    assert [r["full_name"] for r in saved] == ["hi/a"]
    assert saved[0]["clone_ok"] is True

def test_run_isolates_clone_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(archive.common, "ROOT", str(tmp_path))
    archive.common.dump_json(str(tmp_path / "data" / "scored" / "2026-10-05.json"),
                             [{"full_name": "a/b", "score": 8, "one_liner": "x"}])
    out = archive.run({"llm": {"min_score": 5}}, "2026-10-05",
                      clone=lambda fn, d: False, wiki=lambda s, fn, d: True)
    assert out[0]["clone_ok"] is False
    assert out[0]["wikis"]["deepwiki"] is True   # wiki 仍继续

def test_run_isolates_wiki_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(archive.common, "ROOT", str(tmp_path))
    archive.common.dump_json(str(tmp_path / "data" / "scored" / "2026-10-05.json"),
                             [{"full_name": "a/b", "score": 8, "one_liner": "x"}])
    out = archive.run({"llm": {"min_score": 5}}, "2026-10-05",
                      clone=lambda fn, d: True, wiki=lambda s, fn, d: s != "zread")
    assert out[0]["wikis"] == {"deepwiki": True, "codewiki": True, "zread": False}

def test_run_overwrites_existing_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(archive.common, "ROOT", str(tmp_path))
    archive.common.dump_json(str(tmp_path / "data" / "scored" / "2026-10-05.json"),
                             [{"full_name": "a/b", "score": 8, "one_liner": "x"}])
    base = str(tmp_path / "code" / "a__b")
    os.makedirs(os.path.join(base, "code"), exist_ok=True)
    open(os.path.join(base, "code", "stale.txt"), "w").write("old")
    def fake_clone(fn, dest):
        os.makedirs(dest, exist_ok=True)
        open(os.path.join(dest, "fresh.txt"), "w").write("new")
        return True
    def fake_wiki(src, fn, dest):
        os.makedirs(dest, exist_ok=True)
        return True
    archive.run({"llm": {"min_score": 5}}, "2026-10-05", clone=fake_clone, wiki=fake_wiki)
    assert not os.path.exists(os.path.join(base, "code", "stale.txt"))
    assert os.path.exists(os.path.join(base, "code", "fresh.txt"))

def test_run_defaults_min_score_when_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(archive.common, "ROOT", str(tmp_path))
    archive.common.dump_json(str(tmp_path / "data" / "scored" / "2026-10-05.json"),
                             [{"full_name": "a/b", "score": 4, "one_liner": "x"},
                              {"full_name": "c/d", "score": 6, "one_liner": "y"}])
    out = archive.run({}, "2026-10-05", clone=lambda fn, d: True, wiki=lambda s, fn, d: True)
    assert [r["full_name"] for r in out] == ["c/d"]

def test_run_missing_scored_yields_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(archive.common, "ROOT", str(tmp_path))
    calls = []
    out = archive.run({"llm": {"min_score": 5}}, "2026-10-05",
                      clone=lambda fn, d: calls.append(fn) or True,
                      wiki=lambda s, fn, d: calls.append(s) or True)
    assert out == [] and calls == []

def test_clone_repo_command(monkeypatch):
    captured = {}
    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
    monkeypatch.setattr(archive.subprocess, "run", fake_run)
    assert archive.clone_repo("a/b", "/dest") is True
    assert captured["cmd"] == ["degit", "a/b", "/dest", "--force"]

def test_export_wiki_command(monkeypatch):
    captured = []
    monkeypatch.setattr(archive.subprocess, "run",
                        lambda cmd, **kw: captured.append(cmd) or None)
    archive.export_wiki("codewiki", "a/b", "/dest")
    assert captured == [["repowiki-cli", "codewiki", "cp", "a/b", "/dest"]]
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_archive.py -v`
Expected: FAIL(`ModuleNotFoundError: scripts.archive`)

- [ ] **Step 3: 实现** `scripts/archive.py`

```python
import argparse, os, shutil, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts import common  # noqa: E402

WIKI_SOURCES = ["deepwiki", "codewiki", "zread"]

def threshold(scored, min_score):
    keep = [r for r in scored if r.get("score") is not None and r["score"] >= min_score]
    keep.sort(key=lambda r: r["score"], reverse=True)
    return keep

def repo_dir(full_name):
    return os.path.join(common.ROOT, "code", full_name.replace("/", "__"))

def _wiki_dir(source):
    return "google_code_wiki" if source == "codewiki" else source

def clone_repo(full_name, dest):
    try:
        subprocess.run(["degit", full_name, dest, "--force"],
                       capture_output=True, text=True, check=True)
        return True
    except Exception:
        return False

def export_wiki(source, full_name, dest):
    try:
        subprocess.run(["repowiki-cli", source, "cp", full_name, dest],
                       capture_output=True, text=True, check=True)
        return True
    except Exception:
        return False

def archive_one(row, clone, wiki):
    full_name = row["full_name"]
    base = repo_dir(full_name)
    shutil.rmtree(base, ignore_errors=True)
    os.makedirs(base, exist_ok=True)
    clone_ok = clone(full_name, os.path.join(base, "code"))
    wikis = {s: wiki(s, full_name, os.path.join(base, _wiki_dir(s))) for s in WIKI_SOURCES}
    return {"full_name": full_name, "score": row.get("score"),
            "one_liner": row.get("one_liner", ""), "clone_ok": clone_ok, "wikis": wikis}

def run(cfg, date, clone=None, wiki=None):
    clone = clone or clone_repo
    wiki = wiki or export_wiki
    min_score = int(cfg.get("llm", {}).get("min_score", 5))
    scored_path = common.data_dir("scored", f"{date}.json")
    scored = common.load_json(scored_path) if os.path.exists(scored_path) else []
    archived = [archive_one(r, clone, wiki) for r in threshold(scored, min_score)]
    common.dump_json(common.data_dir("archive", f"{date}.json"), archived)
    return archived

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

Run: `python -m pytest tests/test_archive.py -v`
Expected: PASS(10 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/archive.py tests/test_archive.py
git commit -m "feat: archive stage - degit shallow clone + repowiki-cli wiki export"
```

---

### Task 2: 接入 weekly runner 与 config

**Files:**
- Modify: `config.yaml`(加 `llm.min_score: 5`)
- Modify: `scripts/run_weekly.sh`(score 与 issue 之间插 archive)

**Interfaces:**
- Consumes: `scripts/archive.py` 的 `main()`(Task 1)
- Produces: weekly 流水线顺序变为 search → merge → score → **archive** → issue

- [ ] **Step 1: 编辑 `config.yaml`**

在 `llm:` 块下加一行:

```yaml
llm:
  concurrency: 8
  min_score: 5
```

(把 `llm:` 下现只有 `concurrency: 8` 改成上面两行。)

- [ ] **Step 2: 编辑 `scripts/run_weekly.sh`**

在 score 行之后、issue 行之前插入一行:

```bash
echo "[weekly] archive";      "$PY" scripts/archive.py --config config.yaml
```

(最终该文件 stage 顺序为:`search` → `merge` → `score` → `archive` → `issue`。)

- [ ] **Step 3: 校验**

Run:
```bash
python -c "import yaml; print('min_score =', yaml.safe_load(open('config.yaml'))['llm']['min_score'])"
bash -n scripts/run_weekly.sh && echo "bash syntax ok"
grep -n "archive" scripts/run_weekly.sh
```
Expected:`min_score = 5`、`bash syntax ok`,且 grep 命中 `archive.py`。

- [ ] **Step 4: Commit**

```bash
git add config.yaml scripts/run_weekly.sh
git commit -m "feat: wire archive stage into weekly runner and config"
```

---

### Task 3: CI 依赖(degit + repowiki-cli)与 README

**Files:**
- Modify: `.github/workflows/weekly.yml`(安装 degit + repowiki-cli)
- Modify: `README.md`(本地依赖说明 + v2 状态)

**Interfaces:**
- Consumes: `scripts/run_weekly.sh`(Task 2)在 weekly 工作流中运行
- Produces: weekly 工作流具备归档阶段所需的 CLI 依赖;README 反映 v2 已实现

- [ ] **Step 1: 编辑 `.github/workflows/weekly.yml`**

把安装步骤:

```yaml
      - run: pip install ghresearcher -r requirements.txt
```

改为(repowiki-cli 的 pip 包名是 `pyrepowiki-cli`),并在其后加一行安装 degit:

```yaml
      - run: pip install ghresearcher pyrepowiki-cli -r requirements.txt
      - run: npm install -g degit
```

- [ ] **Step 2: 编辑 `README.md`**

a) 标题版本号:把第一行 `# Daily-Code-Agent-Template (v1)` 改为 `# Daily-Code-Agent-Template (v1 + v2)`。

b) 把「v1 仅覆盖…」两行说明改为:

```
> v1+v2 覆盖「发现 + 打分 + 归档」:每日免费元数据流、每周 README 打分,以及高分仓库的浅克隆(degit)+ wiki 归档(deepwiki/zread/codewiki)。静态 Pages 站点仍属 v3,尚未实现。
> v1+v2 cover **discovery + scoring + archive**: the daily feed, weekly scoring, and shallow-clone (degit) + wiki archive (deepwiki/zread/codewiki) for high-score repos. The static Pages site remains v3.
```

c) 在「本地运行 / Run locally」的 `pip install ghresearcher` 一行之后加两行:

```
pip install pyrepowiki-cli           # 需要 / required for wiki archive (v2)
npm install -g degit                 # 需要 / required for shallow clone (v2)
```

- [ ] **Step 3: 校验**

Run:
```bash
python -c "import yaml,glob; [yaml.safe_load(open(f)) for f in glob.glob('.github/workflows/*.yml')]; print('workflows ok')"
grep -n "pyrepowiki-cli\|degit" .github/workflows/weekly.yml README.md
```
Expected:`workflows ok`,且 grep 在 weekly.yml 与 README.md 均命中。

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/weekly.yml README.md
git commit -m "ci: install degit + repowiki-cli for weekly archive; update README"
```

---
