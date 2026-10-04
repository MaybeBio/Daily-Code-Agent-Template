# Daily-Code-Agent-Template — v3 设计文档(静态 Pages 站点 + 富 code card)

日期:2026-10-05
状态:已与用户确认(3 项决策:富卡片 / 归档提交 + 外链 / 仅高分仓库)

## 1. 目标与范围

在 v1(搜索→打分→Issue)与 v2(高分仓库浅克隆 + wiki 归档)基础上,新增 **v3 静态 Pages 站点**:为每周 `score >= llm.min_score` 的「保留」仓库生成一份 LLM 富卡片(Code Card),渲染成静态站点并部署到 GitHub Pages,页面内附当周 Issue 链接。

**已确认的三项决策:**
- **富卡片(新增 LLM 步骤)**:每仓库用 LLM 把 README 总结成结构化 Code Card(是什么/亮点/为何对本课题有用/怎么用),新增 `code_card` prompt 与生成阶段,而非只渲染 v1 的 score + one_liner。
- **归档提交 + 外链**:`code/`(浅克隆 + 三份 wiki)从 gitignored **改为提交进 git**(对 v2「code/ 保持 gitignored」的逆转);但站点卡片**不渲染本地归档**,只外链 GitHub 仓库与三处公网 wiki URL(deepwiki / codewiki / zread)。
- **仅高分保留仓库**:只为 `score >= llm.min_score`(默认 5)的仓库生成富卡片并展示;低分仓库只进 Issue/CSV,不进站点。

**非目标(继续推迟):** 站点内渲染本地 wiki/code(只外链);Hugging Face 集成。

## 2. 站点布局与页面

静态站点由 `scripts/build_site.py`(Jinja2)渲染 `templates/` 输出到 gitignored 的 `site/`,数据全部来自提交进 git 的 `data/`。

```
site/                        # gitignored,deploy 时重建
├── index.html               # 本周保留仓库(按 score 降序,高/中分层)+ 当周 Issue 链接
├── archive.html             # 按周归档全部保留仓库
├── repos/<owner>__<repo>/index.html   # 单仓库详情(富卡片 + 四个外链)
└── assets/style.css
```

- 详情页目录名沿用 v2 的 `full_name.replace("/", "__")` 约定。
- 页面导航:本周(`/`)、归档(`/archive.html`),与 paper 模板一致。
- `site/` 保持 gitignored,deploy 时从 `data/` 重建。

## 3. 数据模型变化

### 3.1 `requirements.txt`
新增 Jinja2 与 markdown 渲染依赖(供 `build_site.py`):

```
PyYAML
openai
pytest
jinja2
markdown
```

### 3.2 `prompts.yaml` 新增 `code_card`
对齐 score 的 JSON 风格,输出 `{"card": "<markdown>"}`。markdown 固定四节(`## 是什么` / `## 亮点` / `## 为何对本课题有用` / `## 怎么用`),中文为主、技术术语保留英文,只基于 README 不编造。

### 3.3 新增输出 `data/cards/<date>.json`(提交)
每周保留仓库的**自包含**站点输入,按 score 降序:

```jsonc
[
  {
    "full_name": "MaybeBio/GhResearcher",
    "url": "https://github.com/MaybeBio/GhResearcher",
    "language": "Python",
    "stars": 123,
    "pushed_at": "2026-10-01T00:00:00Z",
    "status": "new",
    "score": 8,
    "one_liner": "……",
    "card": "## 是什么\n……\n## 亮点\n……\n## 为何对本课题有用\n……\n## 怎么用\n……"
  }
]
```

- 每条含站点渲染所需的全部字段 + 富卡片 `card`(轻微重复 scored 的 score/one_liner 等字段,换取站点无需跨文件 join)。
- 来源:`scripts/cards.py` 读 `data/scored/<date>.json`(v1 已产出,含 url/language/stars/pushed_at/status/full_name/score/one_liner)→ 过滤 `score >= min_score` → 拉 README → LLM 生成 `card` → 写自包含记录。

### 3.4 新增 `data/latest_issue.txt`(提交)
当周 Issue URL。由 `weekly.yml` 在 `gh issue create` 成功时捕获其 stdout URL 写入此文件;站点首页据此渲染「当周 Issue」链接。每次运行先清空该文件,仅当 issue 创建成功才写入新 URL —— 失败则文件为空,首页不显示链接(优雅降级,且不残留上周的陈旧链接)。

### 3.5 `.gitignore` 变化
- **移除 `code/`** —— 归档的浅克隆 + 三份 wiki 改为提交进 git。
- `site/` 仍忽略(部署时重建)。

## 4. 卡片生成阶段 `scripts/cards.py`

新增单文件,读 `data/scored/<date>.json` 与 `config.yaml`,产出 `data/cards/<date>.json`。

**接口(供测试与 build_site 依赖):**
- `card_record(row: dict, card: str) -> dict` — 从 scored 行 + 富卡片 markdown 组装自包含记录(§3.3 的字段全集)。
- `run(cfg: dict, date: str, client=None, fetch=None, card_fn=None) -> list[dict]` — 编排:读 scored → 复用 `archive.threshold(scored, min_score)` 过滤保留仓库 → 对每行 `fetch(full_name)` 拉 README、`card_fn(...)` 生成卡片 → 写 `data/cards/<date>.json` → 返回记录。`client`/`fetch`/`card_fn` 可注入(默认 `agent.make_client` / `gh.fetch_readme` / `agent.build_code_card`),供离线测试 monkeypatch。
- `main()` — argparse `--config`(默认 `config.yaml`)、`--date`(默认 `common.today()`)。

**复用:** `common.load_config` / `common.data_dir` / `common.load_json` / `common.dump_json` / `common.today`;`archive.threshold`(v2 已测,不重写)。

**错误处理(对齐 v1「单条失败不拖垮整周」):**
- 单仓库 README 拉取失败或 LLM 调用失败:该仓库 `card` 记为空串 `""`,继续下一仓库,不中断(与 score.py 的 `[fetch failed]` 同哲学)。

### 4.1 `scripts/agent.py` 新增 `build_code_card`

```python
def build_code_card(client, model, prompts, topic, readme) -> dict:
    # 调 prompts["code_card"],response_format json_object,返回 {"card": str}
```
与 `score_repo` 同风格(4 次重试 + 指数退避),返回 `{"card": "<markdown>"}`。

## 5. 站点生成 `scripts/build_site.py`

新增单文件,镜像 paper 模板的 `build_site.py`。

**接口:**
- `score_tier(score) -> str` — `>=8` high / `5-7` mid / 其余 low(与 paper 模板一致)。
- `wiki_url(source: str, full_name: str) -> str` — 公网 wiki URL:
  - `deepwiki` → `https://deepwiki.com/<full_name>`
  - `codewiki` → `https://codewiki.google/github.com/<full_name>`
  - `zread` → `https://zread.ai/<full_name>`
- `load_cards(out_dir) -> list[dict]` — 遍历 `data/cards/*.json`,给每条补 `date` 字段,按 date 降序返回;缺 `data/cards/` 目录返回 `[]`。
- `load_issue_url(out_dir) -> str` — 读 `data/latest_issue.txt`(存在则返回内容,否则 `""`)。
- `build_site(out_dir, config=None)` — 渲染 `site/`:
  - `index.html`:最新一周记录 + issue 链接 + 分数图例
  - `archive.html`:按周分组全部记录
  - `repos/<owner>__<repo>/index.html`:单仓库详情(富卡片 markdown→HTML + 四个外链)
- `main()` — argparse `--out-dir`(默认 `.`)、`--config`(默认 None)。

**渲染依赖:** Jinja2(`Environment` + `FileSystemLoader` + `select_autoescape(["html"])`)、`markdown`(转 `card` markdown → HTML,extensions 同 paper:`tables`/`fenced_code`/`sane_lists`)。

**模板全局变量:** `BASE`(`site_base_url` 的路径前缀,空串=根)、`SITE_TITLE`(`config.title`)、`score_tier`、`wiki_url`。

## 6. 模板 `templates/`

| 文件 | 职责 |
|---|---|
| `base.html` | `<head>` + 页头导航(本周 `/`、归档 `/archive.html`)+ `assets/style.css` 链接 + `{% block content %}` |
| `index.html` | 本周推荐:图例侧栏(分数分层)+ 本周保留仓库列表(`_code_card.html`)+ 当周 Issue 链接 |
| `archive.html` | 按周降序分组的全部保留仓库 |
| `_code_card.html` | 紧凑列表卡片:score 徽标(分层色)+ 仓库名 + one_liner + stars/language + 外链 |
| `code.html` | 单仓库详情:`card` markdown 渲染 + 四个外链(GitHub / DeepWiki / CodeWiki / zread) |
| `assets/style.css` | 站点样式 |

## 7. 每周流水线更新 `scripts/run_weekly.sh`

在 `archive` 与 `issue` 之间插入 cards 阶段:

```bash
echo "[weekly] cards";      "$PY" scripts/cards.py --config config.yaml
```

完整顺序变为:search → merge → score → archive → **cards** → issue。

## 8. CI 工作流

### 8.1 `.github/workflows/weekly.yml`(调整)
为把当周 Issue URL 提交进 `data/latest_issue.txt`,将「open issue」步骤**提前到 commit 之前**,并让 open issue 捕获 URL:

```yaml
      - name: weekly
        run: bash scripts/run_weekly.sh
        env: {LLM_BASE_URL: ..., LLM_API_KEY: ..., LLM_MODEL: ...}
      - name: open issue
        run: |
          : > data/latest_issue.txt
          if [ -s /tmp/issue.md ]; then
            url=$(gh issue create --title "$(cat /tmp/issue.title)" --body-file /tmp/issue.md) && echo "$url" > data/latest_issue.txt || true
          fi
      - name: commit
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add -A
          git diff --cached --quiet && echo "no changes" && exit 0
          git commit -m "weekly: $(date +%F)"
          for i in 1 2 3; do git pull --rebase && git push && break || sleep $((i*5)); done
```

`git add -A` 现在会提交 `code/`(归档)、`data/cards/<date>.json`、`data/latest_issue.txt` 等。

### 8.2 新增 `.github/workflows/deploy_pages.yml`
镜像 paper 模板的 Pages 部署:

```yaml
name: deploy-pages
on:
  workflow_run:
    workflows: ["weekly-discovery"]
    types: [completed]
  workflow_dispatch: {}
permissions: {contents: read, pages: write, id-token: write}
concurrency: {group: pages, cancel-in-progress: true}
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
        with: {python-version: '3.11'}
      - run: pip install -r requirements.txt
      - run: python scripts/build_site.py --out-dir . --config config.yaml
      - uses: actions/configure-pages@v6
      - uses: actions/upload-pages-artifact@v4
        with: {path: site}
      - id: deployment
        uses: actions/deploy-pages@v5
```

`site/` 不被提交,部署时从 `data/` 重建。

## 9. 提交策略

- 提交:`data/cards/<date>.json`、`data/latest_issue.txt`、`code/`(浅克隆 + wiki)、`data/scored`、`data/archive`、`registry.json` 等(weekly 工作流 `git add -A`)。
- 不提交:`site/`(gitignored,deploy 时重建)。

## 10. 测试(pytest,不联网)

- `cards.py`:(a) 仅 `score >= min_score` 仓库生成卡片并写入 `data/cards/<date>.json`;(b) 自包含记录字段全集正确(含 `card`);(c) 单仓库 `fetch`/`card_fn` 失败记空 `card` 不中断;(d) `data/scored/<date>.json` 缺失时写空 `[]` 不崩溃、不调 LLM。
- `agent.build_code_card`:mock client,断言返回 `{"card": ...}` 且调用 `prompts["code_card"]`。
- `build_site.py`:(a) `wiki_url` 三种 source 的 URL 正确;(b) `score_tier` 分层正确;(c) `load_cards` 空目录返回 `[]`;(d) `load_issue_url` 文件缺失返回 `""`;(e) `build_site` 渲染出 index/archive/detail 三个 HTML 且含期望内容(如 Issue 链接、外链 URL);(f) 空数据不崩溃。
- 命令/流水线 sanity 校验:bash 语法、yaml 可解析、`cards.py` 接入 run_weekly.sh。

## 11. 风险

- **LLM 调用量**:每周多一轮「保留仓库数 × 1」的卡片生成,受 min_score 门槛收敛,通常有限;沿用 score 的并发与重试。
- **仓库体积**:`code/` 提交后,浅克隆 + 三份 wiki 随每周复现增长;用户已确认接受(§1 决策二)。
- **公网 wiki URL 稳定性**:zread 的公网仓库页路径(`zread.ai/<owner>/<repo>`)未经逐仓核验,可能需 `/github/` 前缀;实现时以 `wiki_url` 单点封装,便于后续修正。
- **Pages 部署时机**:`workflow_run` 在 weekly 成功后触发;若 weekly 被取消/失败,站点不更新(与 paper 模板同,`workflow_dispatch` 可手动补)。

## 12. v3 验收标准

1. 本地在 `data/scored/<date>.json` 存在时跑 `python scripts/cards.py --config config.yaml`,生成 `data/cards/<date>.json`,其中仅含 `score >= llm.min_score` 的仓库,每条含 `card` 富卡片。
2. `python scripts/build_site.py --out-dir . --config config.yaml` 生成 `site/index.html`、`site/archive.html`、`site/repos/<owner>__<repo>/index.html`,详情页含四外链(GitHub/DeepWiki/CodeWiki/zread)。
3. 首页渲染当周 Issue 链接(读 `data/latest_issue.txt`)。
4. `code/` 从 `.gitignore` 移除,归档可被提交。
5. `bash scripts/run_weekly.sh` 在 score → archive 之后、issue 之前执行 cards。
6. `deploy_pages.yml` 在 weekly 成功后重建并部署 `site/`。
7. `pytest` 全绿(不联网)。
