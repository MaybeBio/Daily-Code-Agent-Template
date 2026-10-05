# Daily-Code-Agent-Template (v1 + v2 + v3)

定时追踪 GitHub 仓库的自动化模板:每天抓取"免费元数据"动态流,每周对候选仓库的 README 做 LLM 打分,并把结果推送到 GitHub Issue + CSV。
Scheduled GitHub-repo tracking template: a daily free-metadata feed plus a weekly README-LLM scoring pass, pushed to a GitHub Issue + CSV.

> v1+v2+v3 覆盖「发现 + 打分 + 归档 + 站点」:每日免费元数据流、每周 README 打分、高分仓库的浅克隆(degit)+ wiki 归档,以及把这些高分仓库渲染成静态 Pages 站点(每仓库一张富 code card,附当周 Issue 链接)。
> v1+v2+v3 cover **discovery + scoring + archive + site**: the daily feed, weekly scoring, shallow-clone (degit) + wiki archive, and a static Pages site with one rich code card per high-score repo plus the weekly Issue link.

依赖 / Depends on:`ghresearcher` CLI(PyPI `ghresearcher`)、`pyrepowiki-cli`(PyPI `pyrepowiki-cli`,v2 归档)、Node.js + `degit`(npm,v2 浅克隆)与 `gh` CLI(`gh auth login`)。本地需 Python 3.11+。
Requires the `ghresearcher` CLI (PyPI `ghresearcher`), `pyrepowiki-cli` (PyPI `pyrepowiki-cli`, v2 archive), Node.js + `degit` (npm, v2 clone), and the authenticated `gh` CLI.

## 快速开始 / Quickstart

1. **配置 / Configure** — 编辑 `config.yaml`(`topic` / `title` / `window_days`)并按主题填写 `monitor/lists/{users,users_core,orgs}.txt`(每行一个真实 GitHub 用户或 org;`users_core.txt` 必须是 `users.txt` 的子集,它只收窄更嘈杂的 received 流)。
   Edit `config.yaml` (`topic` / `title` / `window_days`) and fill `monitor/lists/{users,users_core,orgs}.txt` with real GitHub users/orgs — one per line.
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

# 每周 / weekly (search → merge → score → archive → issue)
bash scripts/run_weekly.sh

# 站点 / site (v3)
python scripts/build_site.py --out-dir . --config config.yaml
```

## 测试 / Tests

```bash
python -m pytest -q
```
