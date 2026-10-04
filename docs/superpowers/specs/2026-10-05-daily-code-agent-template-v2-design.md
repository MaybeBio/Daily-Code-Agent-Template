# Daily-Code-Agent-Template — v2 设计文档(归档阶段)

日期:2026-10-05
状态:已与用户确认(3 项门槛/来源/更新决策)

## 1. 目标与范围

在 v1 每周流水线(搜索 → 合并 → 打分 → 周报 Issue)基础上,新增**归档阶段**:对达到分数门槛的仓库,用 `degit` 浅克隆代码、用 `repowiki-cli` 导出三种 AI wiki,落在 gitignored 的 `code/` 下,供本地浏览与后续 v3 站点消费。

**已确认的三项决策:**
- **min_score 门槛**:`score >= llm.min_score`(默认 5)才做浅克隆 + wiki 归档;低于阈值的仓库只保留 score/one_liner,不归档。对齐 paper 模板语义(高分段才生成卡片,低分段只保留)。
- **wiki 来源**:三个全抓 —— DeepWiki(`deepwiki`)、Google Code Wiki(`codewiki`)、zread(`zread`)。
- **更新策略**:仓库每周复现(updated)也**全量重克隆 + 重抓 wiki 覆盖旧档**(不对齐「已有就跳过」,因为 wiki 无法增量更新,spec v1 §11 已提示「通常需全量重抓」)。

**非目标(继续推迟):** v3 静态 Pages 站点 + code card、Hugging Face 集成。

## 2. 归档布局

```
code/                       # 已 .gitignore,归档不提交
└── <owner>__<repo>/        # full_name 的 '/' 替换为 '__'
    ├── code/               # degit 浅克隆(默认分支 HEAD,无 .git 历史)
    ├── deepwiki/           # repowiki-cli deepwiki cp
    ├── google_code_wiki/   # repowiki-cli codewiki cp(codewiki == Google Code Wiki)
    └── zread/              # repowiki-cli zread cp
```

- full_name → 目录名:`full_name.replace("/", "__")`(如 `MaybeBio/GhResearcher` → `MaybeBio__GhResearcher`)。
- 每次归档前先清空该仓库目录,保证「全量覆盖」语义(degit 用 `--force`;wiki 导出前 `shutil.rmtree` 清目标目录)。
- `code/` 已在 `.gitignore`(v1 §10),归档产物**不提交**;仅提交 `data/archive/<date>.json` 元数据。

## 3. 数据模型变化

### 3.1 `config.yaml`
新增一行(放在 `llm:` 块下,对齐 paper 模板):

```yaml
llm:
  concurrency: 8
  min_score: 5          # (v2) score >= 该值才克隆+抓 wiki
```

### 3.2 新增输出 `data/archive/<date>.json`
归档阶段的结果清单(按 score 降序):

```jsonc
[
  {
    "full_name": "MaybeBio/GhResearcher",
    "score": 8,
    "one_liner": "……",
    "clone_ok": true,
    "wikis": {"deepwiki": true, "codewiki": true, "zread": false}
  }
]
```

- 每仓库一条;`clone_ok` 与 `wikis.{source}` 记录该项成功/失败(逐项隔离,失败记 `false` 不中断)。
- `registry.json` 结构**不变**(score/one_liner 已由 `score.py` 写入;归档不新增持久字段)。

## 4. 归档阶段 `scripts/archive.py`

新增单文件,消费 `data/scored/<date>.json` 与 `config.yaml`,产出 `data/archive/<date>.json` 及 `code/` 目录。

**接口(供测试与后续 v3 依赖):**

- `threshold(scored: list[dict], min_score: int) -> list[dict]` — 过滤 `score` 非 None 且 `>= min_score` 的仓库,按 score 降序返回。
- `repo_dir(full_name: str) -> str` — `full_name` → `code/<owner>__<repo>` 绝对路径。
- `clone_repo(full_name: str, dest: str) -> bool` — 跑 `degit <full_name> <dest> --force`,成功返回 True。
- `export_wiki(source: str, full_name: str, dest: str) -> bool` — `source ∈ {deepwiki, codewiki, zread}`,跑 `repowiki-cli <source> cp <full_name> <dest>`,成功返回 True。
- `archive_one(row: dict, clone, wiki) -> dict` — 单仓库:清目录 → 克隆 → 三 wiki,逐项 try/except,返回带 `clone_ok`/`wikis` 的记录。`clone: (full_name, dest) -> bool`,`wiki: (source, full_name, dest) -> bool`。
- `run(cfg: dict, date: str, clone=None, wiki=None) -> list[dict]` — 编排:读 scored → threshold → 对每行 `archive_one(row, clone, wiki)` → 写 `data/archive/<date>.json` → 返回记录。`clone`/`wiki` 可注入(默认 `clone_repo`/`export_wiki`),供离线测试 monkeypatch。
- `main()` — argparse `--config`(默认 `config.yaml`)与 `--date`(默认 `common.today()`),调 `run`。

**复用:** `common.load_config` / `common.data_dir` / `common.load_json` / `common.dump_json` / `common.today` / `common.ROOT`。

**命令拼装(唯一外部依赖):**
- 克隆:`degit {full_name} {dest} --force`
- wiki:`repowiki-cli {source} cp {full_name} {dest}`(source 取值 `deepwiki` / `codewiki` / `zread`)

**错误处理(沿用 v1「单条失败不拖垮整周」):**
- 仓库级:任一仓库克隆失败或全部 wiki 失败,记 `false`,继续下一仓库。
- wiki 级:三个 wiki 相互独立,一个失败不影响其余两个与其它仓库。
- 外部命令调用沿用 gh.py 的 `subprocess.run(check=…)` 风格;`clone_repo`/`export_wiki` 内部捕获 `Exception` 返回 `False`(不向上抛)。

## 5. 每周流水线更新 `scripts/run_weekly.sh`

在 `score` 与 `issue` 之间插入一行:

```bash
echo "[weekly] archive";      "$PY" scripts/archive.py --config config.yaml
```

完整顺序变为:search → merge → score → **archive** → issue。

## 6. 提交策略

- 提交:`data/archive/<date>.json`。
- 不提交:`code/`(gitignored)、`site/`。

## 7. 测试(pytest,不联网)

- `threshold`:score 为 None、< min_score、>= min_score 三分支过滤 + 降序。
- `repo_dir`:`a/b` → `…/code/a__b`。
- `run`(注入假 `clone`/`wiki`):(a) 仅达标仓库被归档;(b) 克隆失败记 `clone_ok=false` 且不中断;(c) 单 wiki 失败记 `false` 且不中断其余 wiki/仓库;(d) 输出 `data/archive/<date>.json` 内容正确;(e) updated(已存在目录)仓库同样重跑覆盖。
- 命令拼装:验证 `degit` argv(含 `--force`)与 `repowiki-cli {source} cp` argv(含 dest 路径),monkeypatch `subprocess.run`。

## 8. 风险

- **服务可用性**:DeepWiki/codewiki/zread 对部分仓库无条目会失败 → 记 `false`,不视为错误(与 `[fetch failed]` 同哲学)。
- **限流**:归档阶段**顺序执行**(每仓库 1 克隆 + 3 wiki),默认不并发;候选经 min_score 门槛收敛,通常有限。后续需要再引入并发旋钮。
- **磁盘**:浅克隆 + 三份 wiki 体积不可控,但 `code/` gitignored,不污染仓库体积;超时可手动清 `code/`。

## 9. v2 验收标准

1. 本地在 `data/scored/<date>.json` 存在时跑 `python scripts/archive.py --config config.yaml`,生成 `data/archive/<date>.json`,并在 `code/<owner>__<repo>/` 下产出 `code/` + 三个 wiki 目录。
2. 仅 `score >= llm.min_score` 的仓库被归档。
3. updated 仓库同样重新克隆 + 重抓 wiki(覆盖旧档)。
4. 任一 wiki/克隆失败不拖垮整阶段,`data/archive/<date>.json` 如实记录。
5. `bash scripts/run_weekly.sh` 在 score 之后、issue 之前执行 archive。
6. `pytest` 全绿(不联网)。
