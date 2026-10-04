# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this place is

`/data2/Daily-Code-Agent-Template` is a **template/scratch directory**, not a working application. It is **not** a git repository itself. It holds the README (the design brief) plus three vendored reference projects, each cloned from GitHub with its own `.git` (they are plain sibling clones, not git submodules):

| Dir | Upstream | Role |
|---|---|---|
| `GhResearcher/` | MaybeBio/GhResearcher | CLI `ghresearcher` — GitHub monitor / parse / search |
| `Repowiki-cli/` | MaybeBio/Repowiki-cli | CLI `repowiki-cli` (PyPI dist `pyrepowiki-cli`) — DeepWiki / Google Code Wiki / zread fetching |
| `Daily-GitHub-AI4Bio/` | MaybeBio/Daily-GitHub-AI4Bio | A working example of the search + CSV + issue workflow to imitate |

The **goal** (from `README.md`) is to build a new automated pipeline in this directory that, on a schedule, discovers GitHub repos for a research topic, scores/filters them, pushes an Issue + static Pages site, shallow-clones the high scorers, and archives AI wiki docs for each. **This pipeline does not exist yet** — treat the subprojects as reference tools to call, and the README as the spec. To understand where output should land, mirror the sibling `/data2/Daily-Paper-Agent-Template` (see below).

## The target pipeline (from README.md)

1. **Search** — periodic (daily/weekly) GitHub repo search for topic keywords. Use `ghresearcher search` (preferred) or `gh`. See `Daily-GitHub-AI4Bio/discovery/queries/*.yaml` for query-config style.
2. **Table + Issue** — each run writes a CSV (repo/url/last-commit/score/one-line summary) and **must** open a GitHub Issue (issue push is explicitly required via the workflow).
3. **Score/filter** — LLM scores each repo's README against the topic (inspiration/usefulness), à la the paper template's scoring.
4. **Clone + wiki archive** — for high-score repos: `degit` shallow clone into `code/`, plus save AI-generated wiki docs into sibling dirs. Layout per repo: `<repo>/{code/, deepwiki/, zread/, google_code_wiki/}`. Use `repowiki-cli deepwiki cp` / `codewiki cp` / `zread cp` to export wikis.
5. **Static Pages** — weekly deploy of a site with one **code card** per repo (mirror the paper template's site), plus an Issue link into the rendered page.
6. (Optional) Hugging Face integration via `hf` CLI.

The README's section 6 lists four **open design questions** (scoring gating, de-duplicating repos seen across weeks, end-to-end workflow integration, per-step implementation). Keep these in mind — they are unresolved, not settled.

## Reference implementation to model on: `/data2/Daily-Paper-Agent-Template`

"BioLit Agent" is the working paper-analog of exactly this pipeline (discover → score → Issue → Pages). Its architecture is the blueprint:

- `config.yaml` — per-topic settings: `topic` (slug), `title`, `window_days`, `site_base_url`, `search_placeholder`, `platforms.*.query`, and an `llm:` block (`enable_card`, `enable_reviewer`, `concurrency`, `min_score`). **Adding a new topic = editing `config.yaml` + `prompts.yaml` only.**
- `prompts.yaml` — four prompts: `score`, `translate`, `paper_card`, `review`.
- `scripts/monitor.py` — fetch + normalize + write `Archive/` + `Discovery/`, build the Issue body, orchestrate the agent pipeline.
- `scripts/agent.py` — OpenAI-compatible LLM layer (`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` from env only, never in files); `score_paper`, `translate_abstract`, `build_paper_card`, `build_review`.
- `scripts/build_site.py` — Jinja2 static-site generator: walks `Archive/`, renders `templates/*.html` into `site/` (which is gitignored and rebuilt at deploy time).
- `templates/` — `base/index/week/paper/archive/search.html`, `_paper_card.html`, `assets/{style.css,search.js}`.
- `.github/workflows/monitor.yml` — cron + `workflow_dispatch`; runs monitor+agent, commits as `github-actions[bot]`, opens the Issue via `gh issue create`.
- `.github/workflows/deploy_pages.yml` — triggers on `workflow_run` completion of the monitor workflow; rebuilds `site/` and deploys via `actions/deploy-pages`.

### Automation conventions shared across these repos

- Workflows commit with `github-actions[bot]` / `41898282+github-actions[bot]@users.noreply.github.com`, then `git pull --rebase` before `git push`.
- Pages deploy uses the `workflow_run` + `workflow_dispatch` dual trigger (a manual push to a gitignored `site/` never fires `workflow_run`).
- **GitHub's native `schedule` is best-effort and unreliable here** (documented in `Daily-GitHub-AI4Bio/Notes.md`). The AI4Bio repo therefore relies on an external timer (Cron-job.org) hitting `workflow_dispatch`, and its workflows only declare `workflow_dispatch`. Cron is UTC; `TZ` only affects in-job `date`.
- Secrets/vars used by the paper template: `ENTREZ_EMAIL`, `NCBI_API_KEY`, `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` (the last as a repo *variable*).

## Tool commands

### GhResearcher (`ghresearcher`, Python 3.8+)
Requires an authenticated `gh` CLI (`gh auth login`). Install `pip install ghresearcher`, or from source `cd GhResearcher && pip install -e .`.

```bash
ghresearcher monitor -f <list.txt> --since $(date -d '1 day ago' +%Y-%m-%d) --expand-commits   # users
ghresearcher monitor -f <orgs.txt> --org --expand-commits                                      # orgs
ghresearcher monitor -f <core.txt> --since <date> -r --expand-commits -l 30                    # a user's feed
ghresearcher parse <owner/repo>            # README + tree -> LLM-friendly .md
ghresearcher search --config <search.yaml> --updated ">=$(date -d '7 days ago' +%Y-%m-%d)" --jq '<filter>'
```
Key facts: `--limit` is **per target** (default 30); GitHub Events API caps at **300 events/target**; `--expand-commits` costs one extra API call per push. Search configs are YAML (`item_type`, `query`, `limit`, `sort`, `order`, `json` field list) — see `GhResearcher/examples/`.

### Repowiki-cli (`repowiki-cli`, Python 3.10+)
Install `uv tool install pyrepowiki-cli` / `pipx install pyrepowiki-cli` / `pip install pyrepowiki-cli`; from source `uv sync && uv run repowiki-cli --help`. Three namespaces: `deepwiki`, `codewiki`, `zread`.

```bash
repowiki-cli deepwiki structure <owner/repo>       # table of contents
repowiki-cli deepwiki contents  <owner/repo>
repowiki-cli deepwiki cp <owner/repo> [OUT_DIR]    # export full wiki -> one .md per page + llms.txt/llms-full.txt (OUT_DIR defaults to owner_repo)
repowiki-cli codewiki cp <owner/repo> [OUT_DIR]
repowiki-cli zread   cp <owner/repo> [OUT_DIR]
```
`--save PATH` on any command writes Markdown (bare `--save` auto-names `repowiki-<owner>-<repo>_<timestamp>.md`). Tests are real pytest: `uv run pytest` in `Repowiki-cli/`.

### Daily-GitHub-AI4Bio (archive repo, no install)
```bash
python3 scripts/weekly_report.py <topic> <search_config.yaml> <out.csv> --updated ">=YYYY-MM-DD"
python3 scripts/analyze_logs.py monitor/users/*/*/*/*.txt
```
`weekly_report.py` extracts ghresearcher's result array structurally (between first `[` and last `]`) and appends a Chinese-translation column via vendored `scripts/trans` (needs `gawk`). CSV columns mirror the search config's `json` list. `discovery/queries/search_<topic>_repos.yaml` is the repo-search query template; `discovery/weekly/YYYY/MM/` holds the snapshots.

## Caveats worth remembering

- `users_core.txt` must be a **strict subset** of `users.txt` (it only narrows the noisier `received` feed).
- Wiki content (DeepWiki/zread/CodeWiki) is **not re-fetchable incrementally** — the README flags "how to update a repo's wiki when it reappears next week" as an open problem. Clones can be overwritten by re-running `degit`, but wikis typically need a full re-pull.
- Keep LLM `concurrency` low (paper template uses 8) — the SJTU gateway rate-limits a single API key to ~10 requests/window.
- `site/` is gitignored and rebuilt from committed data (`Archive/`) at deploy time; don't expect it to persist in git.
