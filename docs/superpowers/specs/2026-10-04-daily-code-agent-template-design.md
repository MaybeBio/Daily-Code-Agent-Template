# Daily-Code-Agent-Template — 设计文档

日期:2026-10-04
状态:已与用户逐节确认(第 1–4 节)

## 1. 目标与范围

一个**科研领域的 GitHub 仓库自动追踪模板**(单 topic / 仓库,形态对齐 `Daily-Paper-Agent-Template`)。周期性:按关键词盲搜 + 抽取关注圈子动态里的仓库 → 并集去重 → 抓 README 做 LLM 打分 → 推送 Issue + 落盘 CSV;后续版本对高分仓库浅克隆并归档 AI wiki、生成静态 Pages 站点 + 每仓库 code card。

**核心驱动工具(复用,不重写)**:
- `ghresearcher`(PyPI 同名单包)——`monitor`(关注人/组织动态)、`search`(关键词搜仓库)、`parse`(README+tree → LLM 友好 md)
- `repowiki-cli`(PyPI `pyrepowiki-cli`)——`deepwiki`/`codewiki`/`zread` 的 `cp` 导出 wiki(v2)
- `degit` —— 浅克隆(v2)

### v1 范围(本次实现)
心跳闭环:**每日**(日志 + 免费元数据表 + Issue,不花 LLM)+ **每周**(盲搜 ∪ 日抽仓库 → registry 去重 → README 精读打分 → 周报 Issue + CSV)。

### 非目标(显式推迟)
- v2:高分仓库浅克隆(`code/`)+ 抓 wiki(`deepwiki/`、`zread/`、`google_code_wiki/`);含"高分门槛(min_score)"的最终语义。
- v3:静态 Pages 站点 + 每仓库 code card(`build_site.py` + `templates/` + `deploy_pages` 工作流)。
- Hugging Face(`hf` CLI)集成。

## 2. 总体架构与仓库布局

模板落在仓库根目录。运行时靠 PyPI 安装 ghresearcher / repowiki-cli,不依赖 vendor 副本,因此当前开发期参考目录 `GhResearcher/`、`Repowiki-cli/`、`Daily-GitHub-AI4Bio/` **不属于模板**——`git init` 时须排除(写入 `.gitignore`),否则成为嵌套仓库。

采用**方案 B:分阶段脚本 + JSON 中间产物**,每阶段可单独跑/测/重跑。

```
├── config.yaml                       # 课题与开关(见 §7)
├── prompts.yaml                      # LLM 提示词(见 §7)
├── README.md                         # “Use this template” 三步上手
├── .gitignore                        # code/、site/、__pycache__、参考目录
├── scripts/
│   ├── common.py                     # config/路径/日期/registry 读写
│   ├── daily.py                      # 日志 + 免费元数据表 + daily Issue
│   ├── search.py                     # ghresearcher search 盲搜
│   ├── merge.py                      # 并集 + registry 去重 → new/updated/seen
│   ├── score.py                      # 抓 README + LLM 打分
│   ├── issue.py                      # 周报 Issue + CSV
│   ├── run_weekly.sh                 # 串联 weekly 各阶段
│   ├── (v2) clone.py  wiki.py
│   └── (v3) build_site.py
├── queries/search_repos.yaml         # ghresearcher search 检索式
├── templates/                        # (v3) 站点 Jinja 模板
├── data/
│   ├── registry.json                 # 持久索引(唯一状态)
│   ├── daily/<date>.repos.json
│   ├── search/<date>.json
│   ├── candidates/<date>.json
│   ├── scored/<date>.json
│   └── weekly/<date>.csv
├── monitor/                          # 每日原始日志(沿用 AI4Bio 布局)
│   ├── lists/{users,users_core,orgs}.txt
│   └── {users,orgs,received}/YYYY/MM/DD.txt
├── tests/
└── .github/workflows/{daily.yml, weekly.yml}
```

## 3. 数据模型 `data/registry.json`

全流程唯一状态。每仓库一条:

```jsonc
{
  "topic": "idr-repos",
  "repos": {
    "owner/repo": {
      "first_seen":         "2026-09-28",
      "last_seen":          "2026-10-05",
      "last_commit":        "2026-10-03T12:00:00Z", // 最近观察到的 head(pushedAt,免费元数据)
      "last_scored_commit": "2026-10-03T12:00:00Z", // 上次跑 LLM 时的 head
      "score": 8,
      "one_liner": "一句话总结"
    }
  }
}
```

**去重三态**(`merge.py` 判定,持久索引 + new/updated 标注):
- 不在 registry → **new** → 进打分;
- 在 registry 且 `last_commit != last_scored_commit` → **updated** → **直接重跑分析,原地覆盖** score/one_liner;
- 在 registry 且 commit 未变 → **seen** → 跳过 LLM,沿用旧值。

**明确决策(用户拍板)**:任何变动就重新分析,不做 README 差异比对、不分类、不记录 `source` 来源、不做来源加权。理由:分析对象统一是 README,时间成本比 token 贵。`who`(谁 star 的)只出现在每日免费表里,不进 registry。

## 4. 每日流水线 `daily.py`(不花 LLM)

1. `ghresearcher monitor -f monitor/lists/users.txt --since 1d --expand-commits` → `monitor/users/YYYY/MM/DD.txt`
2. 同法跑 `orgs`、`received`(core users,`-r`)
3. 从当日日志抽 `owner/repo` 集合 → `data/daily/<date>.repos.json`
4. 每日 Issue:上半原始动态,下半"今日候选仓库"免费元数据表
5. 提交日志 + json

每日表列(全部免费元数据,非 LLM):`repo | 谁(who) | 事件(star/push/fork) | stars | language | description`。
`description` 取自 GitHub 元数据,以此与周档的 LLM 一句话从来源上区分。
旋钮:`config.daily.enable_repo_table`(关掉 = 退回 AI4Bio 纯日志)。

## 5. 每周流水线 `run_weekly.sh`(花 LLM)

| 阶段 | 读 | 做 | 写 |
|---|---|---|---|
| `search.py` | `queries/search_repos.yaml` | `ghresearcher search --updated ">=7d ago"` + jq 抽取字段 | `data/search/<date>.json` |
| `merge.py` | 本周 `data/daily/*.repos.json` + `search/*.json` + `registry.json` | 求并集 → 分 new/updated/seen(seen 丢弃) | `data/candidates/<date>.json` |
| `score.py` | candidates | 逐个抓 README(ghresearcher parse / gh api) → LLM 打分+一句话;更新 registry | `data/scored/<date>.json` |
| `issue.py` | scored | 生成周报 Issue + CSV | `data/weekly/<date>.csv` |

周报列:`repo | url | language | stars | last_commit | status(new/updated) | score | one_liner`。
按 status 分组、score 降序。

`score.py` 要点:并发默认 8(受 LLM 网关 ~10/窗口约束,同 paper 模板);失败重试 + 退避;README 抓取失败标 `[fetch failed]` 仍出表,单条失败不拖垮整周。

## 6. 提示词 `prompts.yaml`

v1 仅一个 `score` 提示词:输入 topic + README,返回 JSON `{score: 0-10, one_liner: "..."}`。
v3 再补 `code_card`。领域相关措辞在此替换。

## 7. 配置

`config.yaml`:
```yaml
topic: idr-repos
title: IDR 相关仓库追踪
window_days: 7
site_base_url: https://...            # v3
search_placeholder: ...               # v3
llm:
  concurrency: 8
  # (v2) min_score: 5
daily:
  enable_repo_table: true
  watchlists:
    users: monitor/lists/users.txt
    users_core: monitor/lists/users_core.txt
    orgs: monitor/lists/orgs.txt
search:
  config: queries/search_repos.yaml
```

`queries/search_repos.yaml`:ghresearcher search 格式(`item_type: repos` + `query` + `limit`/`sort`/`order` + `json` 字段列表),照 `Daily-GitHub-AI4Bio/discovery/queries/search_idr_repos.yaml`。

Secrets/Vars:`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`;`GITHUB_TOKEN` 内置。权限:`contents: write` + `issues: write`。

## 8. 工作流

`daily.yml`、`weekly.yml`:均用 `workflow_dispatch`,配外部 Cron-job.org(GitHub 原生 `schedule` 已验证不可靠,见 AI4Bio `Notes.md`);weekly 可选加原生 cron 兜底。两者流程一致:跑脚本 → `github-actions[bot]` 提交(`git pull --rebase` 后 push)→ `gh issue create`。

## 9. 测试(pytest,不联网)

- `merge.py` 状态机:new/updated/seen 三分支 + 原地覆盖;
- `score.py`:假 LLM fixture 测 JSON 解析、`[fetch failed]` 兜底、并发/重试;
- `issue.py`:表渲染、分组、排序。
- fixtures:样例 registry + candidates + 预存 README。

## 10. 提交策略

提交:`data/registry.json`、`data/weekly/*.csv`、`monitor/` 日志、`data/{daily,search,scored}/*.json`(可回放)。
`.gitignore`: `code/`、`site/`、`__pycache__/`、参考目录(`GhResearcher/`、`Repowiki-cli/`、`Daily-GitHub-AI4Bio/`)。

## 11. 风险与未决

- LLM 网关限流:并发与重试须保守,否则 429。
- 外部 Cron 依赖:需自行配置 Cron-job.org(模板 README 写明)。
- v2 wiki 更新难题:仓库复现时 degit 可覆盖,但 wiki 通常需全量重抓——留待 v2 设计(可在 update 记录留 `wiki_stale` 钩子)。
- 未决:v2 的 min_score 门槛语义(高分才克隆/精读?低分是否进 Pages?)。

## 12. v1 验收标准

1. 本地可跑 `python scripts/daily.py --config config.yaml` 生成日志 + 每日 Issue 正文与 `data/daily/<date>.repos.json`。
2. 本地可跑 `bash scripts/run_weekly.sh` 产出 `data/candidates`、`data/scored`、`data/weekly/<date>.csv`,并更新 `data/registry.json`。
3. 重复运行:第二次运行同一批仓库时,`updated`/`seen` 判定正确(commit 未变则跳过 LLM)。
4. `pytest` 全绿(不联网)。
5. 两个 workflow 结构完整,手动 `workflow_dispatch` 可触发提交 + Issue。
