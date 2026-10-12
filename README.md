# Daily-Code-Agent-Template (v1 + v2 + v3)

定时追踪 GitHub 仓库的自动化模板:每天抓取"免费元数据"动态流,每周对候选仓库的 README 做 LLM 打分,并把结果推送到 GitHub Issue + CSV。
Scheduled GitHub-repo tracking template: a daily free-metadata feed plus a weekly README-LLM scoring pass, pushed to a GitHub Issue + CSV.

> v1+v2+v3 覆盖「发现 + 打分 + 归档 + 站点」:每日免费元数据流、每周 README 打分、高分仓库的浅克隆(degit)+ wiki 归档,以及把这些高分仓库渲染成静态 Pages 站点(每仓库一张富 code card,附当周 Issue 链接)。
> v1+v2+v3 cover **discovery + scoring + archive + site**: the daily feed, weekly scoring, shallow-clone (degit) + wiki archive, and a static Pages site with one rich code card per high-score repo plus the weekly Issue link.

依赖 / Depends on:`ghresearcher` CLI(PyPI `ghresearcher`)、`pyrepowiki-cli`(PyPI `pyrepowiki-cli`,v2 归档)、Node.js + `degit`(npm,v2 浅克隆)与 `gh` CLI(`gh auth login`)。本地需 Python 3.11+。
Requires the `ghresearcher` CLI (PyPI `ghresearcher`), `pyrepowiki-cli` (PyPI `pyrepowiki-cli`, v2 archive), Node.js + `degit` (npm, v2 clone), and the authenticated `gh` CLI.

## 快速开始 / Quickstart

1. **配置 / Configure** — 编辑 `config.yaml`(`topic` slug / `title` 显示名 / `topic_desc` 喂给 LLM 的课题说明 / `window_days` / `search.queries` 搜索查询列表)并按主题填写 `monitor/lists/{users,users_core,orgs}.txt`(每行一个真实 GitHub 用户或 org;`users_core.txt` 必须是 `users.txt` 的子集,它只收窄更嘈杂的 received 流)。
   Edit `config.yaml` (`topic` slug / `title` / `topic_desc` — the human-readable brief fed to the LLM / `window_days` / `search.queries` — the list of search queries) and fill `monitor/lists/{users,users_core,orgs}.txt` with real GitHub users/orgs — one per line.
2. **密钥 / Secrets** — 在仓库设置里添加 Secrets `LLM_BASE_URL`、`LLM_API_KEY`,以及变量 Variable `LLM_MODEL`(OpenAI 兼容接口)。
   Add repo Secrets `LLM_BASE_URL` / `LLM_API_KEY` and Variable `LLM_MODEL` (OpenAI-compatible endpoint).
3. **调度 / Schedule** — 用外部 cron(如 Cron-job.org)按需触发两个 `workflow_dispatch` 工作流 `daily-feed` 与 `weekly-discovery`。GitHub 原生 `schedule` 在此不可靠,故不使用;cron 用 UTC。
   Drive the two `workflow_dispatch` workflows (`daily-feed`, `weekly-discovery`) from an external cron (e.g. Cron-job.org). GitHub's native `schedule` is unreliable here and is intentionally not used.

## 本地运行 / Run locally

```bash
pip install -r requirements.txt
pip install ghresearcher              # 需要 / required for search + monitor
pip install pyrepowiki-cli           # 需要 / required for wiki archive (v2)
npm install -g degit                 # 需要 / required for shallow clone (v2)
pip install jinja2 markdown            # 需要 / required for site build (v3)
gh auth login                         # 供 gh api 使用 / for gh api

# 每日 / daily
python scripts/daily.py --config config.yaml \
    --issue-body /tmp/issue.md --issue-title /tmp/issue.title

# 每周 / weekly (search → merge → score → archive → cards → issue)
bash scripts/run_weekly.sh

# 站点 / site (v3)
python scripts/build_site.py --out-dir . --config config.yaml
```

## 搜索时间窗:`pushed_at` 而非 `updated_at` / Search window: pushed_at, not updated_at

「本周推荐」以 `pushed_at`(最后一次真·代码 push)为准,而非 `updated_at` —— 后者会被 star / watch / fork 等非代码事件顶掉:一个代码一年没动的仓库,被人 star 一下,`updated_at` 就变成今天,而 `pushed_at` 仍停在去年。

两个约束:
- `gh search repos` **没有 `--pushed` flag**,只能按 `--updated` 过滤/排序;
- `pushed:` 查询限定符虽存在于 GitHub 搜索语法,但与 `in:name,description,readme,topics` 组合时会被**静默忽略**(本项目每条查询都带 `in:`),所以不能把过滤直接换成 `pushed:`。

因此采用「`--updated` 粗筛 + 客户端精确过滤」:
1. 搜索用 `--updated ">=N天前"` 圈定候选集 —— push 必然更新 `updated_at`,故 `updated_at` 窗口是 `pushed_at` 窗口的**超集**,不会漏掉真 push 的仓库;
2. `scripts/search.py` 逐条读取结果里自带的 `pushedAt` 字段,丢弃 `pushed_at` 早于窗口的仓库。

这样进入打分/归档的仓库 `pushed_at` 都在窗口内,`build_site.py` 按 `pushed_at` 归自然周不会再出现跨年归档。

The weekly list keys off `pushed_at` (last real code push), not `updated_at`, which GitHub bumps on star/watch/fork even when no code changed. Since `gh search repos` has no `--pushed` flag and the `pushed:` qualifier is silently ignored when combined with `in:`, the search keeps `--updated` as a coarse superset filter while `scripts/search.py` drops repos whose `pushed_at` predates the window client-side.

## README 在各环节的截断 / Where the README gets truncated

同一个仓库的 README 在流水线不同环节喂的是不同长度:喂给 LLM 的截断(超长 README 既撑爆上下文又稀释注意力),给人搜/给人看的保留全文(便于溯源命中词的上下文)。

| 环节 | 喂什么 | 截断点 |
|---|---|---|
| 打分 score | README 前 **10,000** 字符 | `scripts/agent.py` `score_repo` 的 `readme[:10000]` |
| card 解析 | README 前 **40,000** 字符 + 目录树 + 依赖清单 | `scripts/cards.py` `_README_CAP = 40000` |
| 存盘 | **全文** | `card_record` 的 `readme` 字段 |
| 搜索 deep 索引 | **全文** | `scripts/build_site.py` `_build_search_documents` |
| 详情页 | **全文**(折叠「README 原文」) | `templates/code.html` |

前两档是「喂给 LLM」的,后三档是「展示/搜索/溯源」的,两套截断互不影响。

The README is truncated differently per stage: scoring feeds only the first 10,000 chars (`scripts/agent.py`), card generation the first 40,000 (`scripts/cards.py`), while storage, the deep search index, and the detail page all keep the full text — truncated only for the LLM, full for display and search.

## 归档的 wiki 复用与周快照 / Wiki reuse & weekly snapshots in the archive

三个 wiki(deepwiki / codewiki / zread)是第三方 AI 现算的产物,上游**没有版本历史**——一旦对方重新生成,旧版本就永久消失,且每次生成因随机性与侧重不同会有差异。因此把它们当「积累材料」而非「缓存」:**只增不删**,每周按抓取日期落一份快照到 `code/{repo}/wikis/{date}/{deepwiki,codewiki,zread}/`,过去周次的快照永不被覆盖。

是否新打一份快照,仍看该 wiki **自身**的更新日期是否落在本次运行的自然周内(先 `repowiki-cli <源> stat --json` 取「内容截止标记」):

| 源 | 截止标记 | 取值 |
|---|---|---|
| deepwiki | `last_modified` | `stat` 的 `data.last_modified`(ISO 日期) |
| zread | `updated_at` | `stat` 的 `data.updated_at`(epoch 秒,转日期) |
| codewiki | `commit_sha` | 只有 sha,经 `gh api .../commits/{sha}` 反查提交日期 |

判定(`scripts/archive.py` 的 `_stat_date` + `_in_week`):标记落在本周 → `cp` 到本周快照;否则(或 `stat` 失败)且已有旧快照 → 不再新打,状态记 `reused`;从未留过快照则仍 `cp`。浅克隆(`code/`)不受此规则影响,每周照常覆盖重拉——代码本身在 GitHub 上有 git 历史,无需本地攒快照。边界:周窗口有「周日深夜更新、周一凌晨抓取」的缝隙,可能把晚几天的更新误判为「上周」而不新打快照,对本仓库的归档用途影响可忽略。

The three wikis (deepwiki / codewiki / zread) are AI-generated by third parties with **no upstream version history** — once regenerated, the old version is gone forever, and each generation differs (randomness + emphasis). They are therefore treated as accumulated material rather than a cache: **append-only**, with one snapshot per run date under `code/{repo}/wikis/{date}/{deepwiki,codewiki,zread}/`; past weeks are never overwritten.

Whether to add a new snapshot still hinges on whether the wiki's **own** update marker falls in the run's natural week (from `repowiki-cli <source> stat --json`): deepwiki `last_modified` (ISO), zread `updated_at` (epoch), codewiki `commit_sha` (resolved via `gh api`). A marker in-week triggers `cp` into this week's snapshot; otherwise — or when `stat` fails — an existing snapshot means no new one is written (`reused`); with no prior snapshot, `cp` still runs. The shallow clone (`code/`) is unaffected and re-cloned weekly — the code already has git history on GitHub, so no local snapshot is needed. One boundary gap: a late-Sunday update fetched early Monday reads as "last week" and skips a snapshot — negligible for this archive's purpose.

## 测试 / Tests

```bash
python -m pytest -q
```
