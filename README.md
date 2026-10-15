<p align="center">
  <img src="assets/banner.svg" width="100%" alt="BioCode Agent —— 科研代码仓库自动追踪 · 打分 · Code Card · 静态站点模板">
</p>

<h1 align="center">BioCode Agent</h1>

<p align="center">
  <strong>科研代码仓库（GitHub repo）自动追踪 + AI 精读模板</strong><br/>
  用 GitHub Actions 每周自动「替你搜一遍研究领域」：每日免费元数据流 + 每周关键词盲搜 → 合并去重 → LLM 按 README 打分 → 高分仓库 <b>degit 浅克隆</b> + AI wiki（DeepWiki · Code Wiki · zread）快照归档 → LLM 生成一张「Code Card」→ 开一条 GitHub Issue 周报 → 部署一个可全文检索的 Pages 站点。
</p>

<p align="center">
  <img src="https://img.shields.io/badge/ghresearcher-powered-7C3AED?style=for-the-badge" alt="ghresearcher powered">
  <img src="https://img.shields.io/badge/repowiki--cli-wiki%20archive-0EA5E9?style=for-the-badge" alt="repowiki-cli wiki archive">
  <img src="https://img.shields.io/badge/schedule-daily%20%C2%B7%20weekly-0D9488?style=for-the-badge" alt="daily · weekly">
  <img src="https://img.shields.io/badge/AI-LLM%20code%20card-F59E0B?style=for-the-badge" alt="LLM code card">
  <img src="https://img.shields.io/badge/output-data%20%2B%20site-4F46E5?style=for-the-badge" alt="data + site">
  <img src="https://img.shields.io/badge/python-3.11-3776AB?style=for-the-badge" alt="python 3.11">
</p>

<p align="center">
  <a href="#-三步上手">三步上手</a> ·
  <a href="#-设计思路">设计思路</a> ·
  <a href="#-流水线各阶段">流水线</a> ·
  <a href="#-code-card-与站点">Code Card 与站点</a> ·
  <a href="#-搜索要点">搜索要点</a> ·
  <a href="#-密钥与仓库配置">密钥与配置</a> ·
  <a href="#-本地运行与调试">本地运行</a> ·
  <a href="#-部署清单">部署清单</a> ·
  <a href="#-faq">FAQ</a>
</p>

> **模板即实例。** 仓库内的 `config.yaml`、`prompts.yaml`、`queries/` 与 `monitor/lists/` 已内置一套完整可跑的示例——以 **「固有无序区 / 无序蛋白（IDR/IDP）× 相分离 / 生物分子凝聚体」** 为默认课题。拿到后你只需改**几个文件**：`config.yaml`（换课题与检索式）、`prompts.yaml`（换领域措辞）、`monitor/lists/*.txt`（换你要盯的人 / 组织）、`queries/search_repos.yaml`（可选，换盲搜式）。核心驱动为自研工具 [ghresearcher](https://github.com/MaybeBio/GhResearcher) 与 [repowiki-cli](https://github.com/MaybeBio/Repowiki-cli)。

> 顶部名称 `BioCode Agent` 只是占位品牌，随你改成任意课题名。

---

## 🚀 三步上手

| 步骤 | 你要做的 | 具体内容 |
|---|---|---|
| **1 · 换课题** | 编辑 [`config.yaml`](./config.yaml) 与 [`prompts.yaml`](./prompts.yaml) | 改 `topic` / `title` / `topic_desc` / `search.queries`，换 `prompts.yaml` 里 2 个 prompt 的领域措辞；填 `monitor/lists/*.txt` |
| **2 · 设密钥与 Pages** | 配置 Secrets / Variables 与 Pages | **Settings → Secrets and variables → Actions** 添加 `LLM_BASE_URL` / `LLM_API_KEY`（secrets）、`LLM_MODEL`（variable）；要 zread 归档再加 `ZREAD_TOKEN`（secret）。**Settings → Pages** 来源选 **GitHub Actions**。改 `config.yaml` 的 `site_base_url` |
| **3 · 每周收报** | 用外部 cron 触发（或手动 `workflow_dispatch`） | 有新仓库时自动开一条 **Issue 周报**，提交 `data/` 与 `code/`，并重建 **Pages 站点**：按分数排序，逐仓库一张 Code Card，支持全文检索 |

### 🔄 换课题（最终操作）

1. GitHub 上 **Use this template** 建新仓库
2. 改 [`config.yaml`](./config.yaml)：`topic`（slug）、`title`、`topic_desc`（喂给 LLM 的课题说明）、`window_days`、`search.queries`（盲搜式）、`github_repo` / `github_branch`（本仓库的 owner/name + 默认分支，用于构造 wiki 快照链接）、**`site_base_url`**（见「部署清单」）
3. 改 [`prompts.yaml`](./prompts.yaml)：`score` 与 `code_card` 两段 prompt 里与领域相关的措辞
4. 填 [`monitor/lists/`](./monitor/lists) 三个清单：`users.txt` / `orgs.txt` / `users_core.txt`（每行一个真实 GitHub 用户或 org；`users_core.txt` 必须是 `users.txt` 的**子集**，它只收窄更嘈杂的 received 流）
5. 配 Secrets / Variables（见「密钥与仓库配置」）
6. **先启用 Pages**：Settings → Pages，来源设为 **GitHub Actions**（不启用则站点不会部署）
7. 手动 `workflow_dispatch` 跑一次 `weekly-discovery` 验证

> 推送到 `main` 后可在仓库 **Actions** 页手动触发试跑；想先本地验证见「本地运行与调试」。

---

## 💡 设计思路

一句话：

> **每天白捡一份「谁在这个领域动了代码」的免费动态流，每周再主动盲搜一遍 → 合并去重成候选池 → LLM 按 README 打分 → 高分仓库连同代码、AI wiki、一张 Code Card 一起永久沉淀下来 → 开一条 Issue 提醒、部署一个站点，供你博采众长、移植灵感。**

设计取舍：

- **双通道发现，宽召回 + 打分过滤** —— 每日通道只吃 GitHub 免费事件流（零成本、按你盯的人/组织），每周通道用关键词盲搜（`in:name,description,readme,topics`，覆盖更宽）。两条并成候选池后，**统统交给 LLM 打分**决定取舍，而不是写死正则启发式。
- **列表用 `pushed_at` 而非 `updated_at`** —— star/watch/fork 会顶掉 `updated_at`，只有真·代码 push 才动 `pushed_at`。搜索只能按 `--updated` 粗筛（超集），再由客户端按 `pushed_at` 精确过滤，保证「本周推荐」都是真推过代码的仓库。
- **代码 + wiki 一起归档，wiki 只增不删** —— 高分仓库 `degit` 浅克隆到 `code/{repo}/code/`；三个第三方 AI wiki 上游没有版本历史，故每周按日期落一份**快照**，过去周次永不被覆盖。
- **AI 写卡片，你来做判断** —— 每个高分仓库自动产出一张 Code Card（是什么 / 亮点 / 为何对本课题有用 / 怎么用 / 核心 idea / 可搬移点），把「值不值得上手 / 能不能移植」的决策成本压到最低，但最终判断仍在你。
- **Issue 即提醒，站点即沉淀** —— 不额外接推送，有命中才开、零命中不打扰；静态 Pages 把每周产出永久沉淀、可全文检索。
- **密钥不入库** —— LLM 凭据与 zread token 一律走环境变量 / Actions Secret。
- **一个课题一个仓** —— 同一骨架可复制成多个独立仓库，并行追踪多个方向。

---

## 🔀 流水线各阶段

| 阶段 | 脚本 | 触发 | 输入 → 输出 |
|---|---|---|---|
| **每日动态** | `scripts/daily.py` | `daily-feed` workflow | 你盯的 users/orgs → `monitor/{users,orgs,received}/…txt` + `data/daily/{date}.repos.json` + 每日 Issue |
| **每周盲搜** | `scripts/search.py` | `weekly-discovery` | `search.queries` 逐条 `gh search repos` → `data/search/{date}.json`（按 `pushed_at` 客户端过滤） |
| **合并去重** | `scripts/merge.py` | 同上 | 近 `window_days` 天的每日 feed ∪ 本周盲搜 → `data/candidates/{date}.json`（按 `full_name` 去重） |
| **LLM 打分** | `scripts/score.py` | 同上 | 候选池 → LLM 按 README 打 0–10 分 + 一句话 → `data/scored/{date}.json` |
| **归档** | `scripts/archive.py` | 同上 | 高分仓库 → `degit` 浅克隆 + 三 wiki 快照 → `code/{repo}/` + `data/archive/{date}.json` |
| **Code Card** | `scripts/cards.py` | 同上 | 高分仓库 README + 目录树 + 依赖 → LLM 生成一张卡片 → `data/cards/{date}.json` |
| **Issue + CSV** | `scripts/issue.py` | 同上 | 打分结果 → `data/weekly/{date}.csv` + 每周 Issue（并记 `data/latest_issue.txt`） |
| **静态站点** | `scripts/build_site.py` | `deploy-pages` workflow | 遍历 `data/` + `code/` → 渲染 `site/` → 部署到 Pages |

一次完整的每周流水线 = `bash scripts/run_weekly.sh`（`search → merge → score → archive → cards → issue`，见脚本）。

<details>
<summary><b>🗂 仓库结构</b></summary>

```
.
├── scripts/
│   ├── daily.py          # 每日：ghresearcher monitor → 免费元数据流 + Issue
│   ├── search.py         # 每周：逐条 gh search repos（pushed_at 客户端过滤）
│   ├── merge.py          # 每日 feed ∪ 本周盲搜 → 候选池
│   ├── score.py          # LLM 按 README 打分（min_score 门控）
│   ├── archive.py        # degit 浅克隆 + 三 wiki 快照（只增不删）
│   ├── cards.py          # LLM 生成 Code Card（README + 目录树 + 依赖）
│   ├── issue.py          # 生成 CSV + 每周 Issue
│   ├── agent.py          # LLM 层：OpenAI 兼容客户端 + score / code_card 两个生成函数
│   ├── build_site.py     # 静态站点生成：遍历 data/ + code/ 渲染 Jinja2 模板
│   ├── gh.py / logs.py   # gh CLI 封装 / 事件日志解析
│   └── run_weekly.sh     # 每周流水线一键编排
├── templates/            # 站点模板（首页 / 周 / 归档 / 搜索 / 卡片详情）+ 样式与搜索脚本
├── queries/search_repos.yaml   # 盲搜配置（每条查询的召回/噪声实测写在注释里）
├── monitor/lists/        # 你要盯的用户 / 组织清单（users / users_core / orgs）
├── config.yaml           # 课题与检索配置（topic / topic_desc / window_days / llm / search）
├── prompts.yaml          # 两个系统 prompt（score / code_card）集中于此
├── assets/banner.svg     # README 头图
├── requirements.txt      # 依赖：openai + jinja2 + markdown 等
├── tests/                # pytest 自检用例（不参与部署，可删除）
└── .github/workflows/
    ├── daily.yml         # 每日动态 + Issue（workflow_dispatch）
    ├── weekly.yml        # 每周发现 + 归档 + 卡片 + Issue（workflow_dispatch）
    └── deploy_pages.yml  # weekly 成功后自动构建并部署 site/
```

</details>

---

## 🃏 Code Card 与站点

站点由 `build_site.py` 遍历 `data/` 与 `code/` 生成，无后端，纯静态，由 `deploy_pages.yml` 部署到 GitHub Pages。页面包括：**本周推荐**、**按周归档**、**全文搜索**、**每仓库一张 Code Card 详情页**。

**Code Card 六节**（`prompts.yaml` 的 `code_card` 定义，输出单字段 `{"card": "<markdown>"}`）：

```
## 是什么 · ## 亮点 · ## 为何对本课题有用 · ## 怎么用 · ## 核心 idea · ## 可搬移点
```

其中「怎么用」由 README + **目录树 + 依赖/构建文件**共同支撑（`cards.py` 三者一起喂给 LLM），「核心 idea / 可搬移点」瞄准的正是**移植**——这个仓库凭什么值得借鉴、哪个模块值得搬进你的 pipeline。

**两套链接口径：**

| 路径 | 含义 | 何时用 |
|---|---|---|
| `site/repos/{repo}/` | **最新**（latest-wins） | 首页 / 站内搜索，永远指向最近一次卡片 |
| `site/weeks/{week}/repos/{repo}/` | **当周冻结快照** | 周归档页，链到**当周那一刻**的卡片与 wiki 快照 |

**wiki 快照链接**：卡片详情页给出三个 wiki 的 live 链接（deepwiki / codewiki / zread），并在有快照时附一个「快照」链接，指向本仓库里的
`code/{repo}/wikis/{date}/{source}/llms.txt`（`github_repo` / `github_branch` 决定它的 GitHub blob 地址）。

**站内搜索（两段式索引）**：索引在导出阶段预生成，浏览器端完成检索——

| 索引 | 文件 | 字段 | 加载时机 |
|---|---|---|---|
| 头索引 | `site/data/search.json` | 仓库名、一句话、语言、stars、日期 | 页面加载即取 |
| 深索引 | `site/data/search-deep.json` | Code Card + README 全文的纯文本 | 勾选「深度搜索」时惰性拉取 |

---

## 🧩 搜索要点

**时间窗以 `pushed_at` 为准，而非 `updated_at`。** 一个代码一年没动的仓库，被人 star 一下，`updated_at` 就变成今天，而 `pushed_at` 仍停在去年。两个约束：

- `gh search repos` **没有 `--pushed` flag**，只能按 `--updated` 过滤 / 排序；
- `pushed:` 限定符虽存在于 GitHub 搜索语法，但与 `in:name,description,readme,topics` 组合时会被**静默忽略**（本项目每条查询都带 `in:`）。

因此采用「`--updated` 粗筛 + 客户端精确过滤」：搜索用 `--updated ">=$(date -d '7 days ago' +%Y-%m-%d)"` 圈定候选集（`updated_at` 窗口是 `pushed_at` 窗口的**超集**，不漏真 push），再由 `scripts/search.py` 读结果里自带的 `pushedAt` 字段，丢掉早于窗口的仓库。

> **盲搜式为什么拆成多条？** GitHub 硬限制「每条查询最多 5 个 AND/OR/NOT 运算符」，备选短语一多单条 `OR` 会被拒。故 `search.queries` 拆成多条（每条 ≤6 项）各自查询、按 `full_name` 取并集。每条查询的召回/噪声实测都写在各 query 正上方的注释里，改写时请务必保留。

---

## 🔑 密钥与仓库配置

LLM 与 zread 凭据一律走环境变量，**不写入仓库**：

| 用途 | 名称 | 类型 | 必填 |
|---|---|---|---|
| LLM 网关地址 | `LLM_BASE_URL` | Secret | AI 必填 |
| LLM API key | `LLM_API_KEY` | Secret | AI 必填 |
| LLM 模型 | `LLM_MODEL` | **Variable** | 可选（默认 `deepseek-chat`） |
| zread 归档 token | `ZREAD_TOKEN` | Secret | 可选（缺则 zread 只复用旧快照） |
| 每日动态 / Issue | `GITHUB_TOKEN` | 内置 | 自动（workflow 已声明 `contents/issues: write`） |

- 本地：`export LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=...`。
- GitHub Actions：**Settings → Secrets and variables → Actions**，分别建 Repository **secrets** 与 **variables**，workflow 以 `${{ secrets.* }}` / `${{ vars.* }}` 注入。

**调度**：两个 workflow 都只声明 `workflow_dispatch`——**GitHub 原生 `schedule` 在此不可靠**，请用**外部 cron**（如 [Cron-job.org](https://cron-job.org)）按需触发 `daily-feed` 与 `weekly-discovery`。cron 用 **UTC**（`TZ` 只影响 job 内的 `date`）。

**模型选型提示**：打分走 `response_format={"type":"json_object"}`，所选模型必须支持 JSON mode（DeepSeek 的 `deepseek-reasoner` 通常不支持，不能直接替换）；评分要忠实、不宜用思考/推理模式。

---

## 💻 本地运行与调试

```bash
pip install -r requirements.txt
pip install ghresearcher pyrepowiki-cli   # 搜索/监控 + wiki 归档（PyPI）
npm install -g degit                      # 浅克隆（Node.js）
gh auth login                             # 供 gh api / gh search 使用

export LLM_BASE_URL=... LLM_API_KEY=...   # 可选 LLM_MODEL=...

# 每日：免费元数据流 + Issue 正文
python scripts/daily.py --config config.yaml \
    --issue-body /tmp/issue.md --issue-title /tmp/issue.title

# 每周：search → merge → score → archive → cards → issue
bash scripts/run_weekly.sh

# 站点：从 data/ + code/ 重建 site/
python scripts/build_site.py --out-dir . --config config.yaml
```

**测试：** `tests/` 是 pytest 自检用例（不参与部署，可安全删除）。

```bash
python -m pytest -q
```

---

## ✅ 部署清单

从「Use this template」到站点跑通，逐项打勾：

- [ ] **`site_base_url` 必填** —— 在 `config.yaml` 填成你的站点地址，例如 `https://<user>.github.io/<repo>`。**留空会导致站内链接变成根绝对路径（`/assets/…`），在项目型 Pages（`user.github.io/REPO/`）上全部 404。** 这是最容易踩的一条。
- [ ] **启用 Pages** —— Settings → Pages，**Source = GitHub Actions**（不启用则 `deploy_pages.yml` 直接失败）。
- [ ] **Secrets / Variables** —— `LLM_BASE_URL` / `LLM_API_KEY`（secret）、`LLM_MODEL`（variable）、`ZREAD_TOKEN`（可选 secret）。
- [ ] **`github_repo` / `github_branch`** —— 改成新仓的 `owner/name` 与默认分支，wiki 快照链接才会指对。
- [ ] **监听清单** —— 填 `monitor/lists/{users,users_core,orgs}.txt`（`users_core` ⊂ `users`）。
- [ ] **外部 cron** —— 用 Cron-job.org 等按 UTC 触发 `daily-feed` 与 `weekly-discovery`（原生 `schedule` 不可靠，故不使用）。
- [ ] **首次试跑** —— Actions 里手动 `workflow_dispatch` 跑一次 `weekly-discovery`，确认 Issue 与 Pages 都出得来。

> **为什么「手动 push 触发不了部署」？** `deploy_pages.yml` 平时由 `weekly-discovery` 的 `workflow_run` 触发；而**手动 push 不含 `site/` 变化**（`site/` 已 gitignore，部署时才重建），没有触发源。所以本地跑完后需手动触发一次：`gh workflow run deploy_pages.yml --repo <owner>/<repo> --ref main`。

---

## ❓ FAQ

<details>
<summary><b>能不能不要 AI？</b></summary>

可以。不配 LLM 密钥、或令打分全部失败时，`data/scored/*.json` 里 `score` 为 `null`，`archive` / `cards` 的高分门控（`llm.min_score`，默认 5）自然不产出任何卡片——检索、落盘、Issue、站点仍照常运行，只是少了打分与卡片。
</details>

<details>
<summary><b>README 在不同环节截断不同，为什么？</b></summary>

同一个仓库的 README，喂给 LLM 的截断（超长 README 既撑爆上下文又稀释注意力），给人搜/给人看的保留全文（便于溯源命中词上下文）：

| 环节 | 喂什么 | 截断点 |
|---|---|---|
| 打分 score | README 前 **10,000** 字符 | `scripts/agent.py` `score_repo` 的 `readme[:10000]` |
| card 生成 | README 前 **40,000** 字符 + 目录树 + 依赖清单 | `scripts/cards.py` `_README_CAP = 40000` |
| 存盘 | **全文** | `card_record` 的 `readme` 字段 |
| 搜索 deep 索引 | **全文** | `scripts/build_site.py` `_build_search_documents` |
| 详情页 | **全文**（折叠「README 原文」） | `templates/code.html` |

前两档是「喂给 LLM」的，后三档是「展示/搜索/溯源」的，两套截断互不影响。
</details>

<details>
<summary><b>wiki 为什么要按周打快照？</b></summary>

deepwiki / codewiki / zread 是第三方 AI **现算**的产物，上游**没有版本历史**——对方一重新生成，旧版本就永久消失，且每次因随机性与侧重不同会有差异。故把它们当**积累材料**而非缓存：**只增不删**，每周按抓取日期落一份到 `code/{repo}/wikis/{date}/{deepwiki,google_code_wiki,zread}/`。

是否新打一份，看该 wiki **自身**的更新日期是否落在本周（deepwiki 用 `last_modified`、zread 用 `updated_at`、codewiki 用 `commit_sha` 反查提交日期）；没更新且已有旧快照则记 `reused` 不再新打。浅克隆（`code/{repo}/code/`）不受此规则影响，每周照常覆盖重拉——代码本身在 GitHub 上有 git 历史，无需本地攒快照。
</details>

<details>
<summary><b>并发设多大？</b></summary>

`llm.concurrency`（默认 8）是「同时跑的仓库数」，每个仓库会**串行**调用 LLM 1~2 次（打分，高分再加卡片），失败还会重试。若你的网关对单 key 有速率限制（例如 SJTU 网关约 10 次/窗口），并发要**明显低于**该限制——出现大量 `429` 时反而应继续调低。`archive.concurrency`（默认 4）是 degit + repowiki 的网络并发，太高会触发 repowiki 限流。
</details>

---

> 这是一个刻意保持通用的**模板仓库**：属于你的只有 `config.yaml`、`prompts.yaml`、`queries/search_repos.yaml` 与 `monitor/lists/`，脚本、模板、工作流、测试基本不必动。把它复制成「一个课题 = 一个独立仓库」，即可同时追踪多个研究方向。
