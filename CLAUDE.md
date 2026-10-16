# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this place is

`/data2/Daily-Code-Agent-Template` is **BioCode Agent** — a *working* GitHub-repo-tracking pipeline, packaged as a reusable template (it IS a git repository). On a schedule it discovers GitHub repos for a research topic, LLM-scores them by README, shallow-clones the high scorers plus AI-wiki snapshots, generates one "Code Card" per repo, opens a GitHub Issue, and deploys a static Pages site.

The default/example topic baked into `config.yaml` / `prompts.yaml` is **IDR/IDP × phase separation (biomolecular condensates)**. "One topic = one repo": to reuse, copy the repo and edit `config.yaml` + `prompts.yaml` + `monitor/lists/` + `queries/`.

Sibling blueprint: `/data2/Daily-Paper-Agent-Template` ("BioLit Agent") — the paper-analog of this same discover → score → Issue → Pages shape. Mirror its conventions.

Gitignored, not part of the template (local dev references only): `GhResearcher/`, `Repowiki-cli/`, `Daily-GitHub-AI4Bio/`, `docs/`, `.claude/`, `.superpowers/`, `.env`, `site/`.

## Pipeline (one topic)

Two discovery channels merge into one candidate pool, then LLM/archive/site stages run off it:

1. **Daily feed** — `scripts/daily.py` runs `ghresearcher monitor` over `monitor/lists/{users,users_core,orgs}.txt` → `monitor/{users,orgs,received}/YYYY/MM/DD.txt`, writes `data/daily/{date}.repos.json`, opens a daily Issue.
2. **Weekly search** — `scripts/search.py` runs each query in `config.yaml:search.queries` via `gh search repos --updated …`, then **client-side filters by `pushed_at`** (see caveats).
3. **Merge** — `scripts/merge.py`: recent daily feeds (window = `window_days`) ∪ this week's search → `data/candidates/{date}.json` (dedup by `full_name`).
4. **Score** — `scripts/score.py` → LLM 0–10 + one-liner per repo → `data/scored/{date}.json`.
5. **Archive** — `scripts/archive.py` (gated by `llm.min_score`): `degit` shallow clone → `code/{repo}/code/`; three wiki snapshots → `code/{repo}/wikis/{date}/{deepwiki,google_code_wiki,zread}/llms.txt`. Writes `data/archive/{date}.json`.
6. **Cards** — `scripts/cards.py` feeds README (cap 40k) + directory tree + dependency files to the LLM → `data/cards/{date}.json`.
7. **Issue + CSV** — `scripts/issue.py` → `data/weekly/{date}.csv` + weekly Issue.
8. **Site** — `scripts/build_site.py` walks `data/` + `code/` → renders `templates/*.html` into `site/` (gitignored, rebuilt at deploy).

`bash scripts/run_weekly.sh` orchestrates steps 2–7. Workflows: `.github/workflows/{daily,weekly,deploy_pages}.yml`; `deploy_pages.yml` triggers on `weekly-discovery`'s `workflow_run` (and `workflow_dispatch`).

## Data layout

- `data/` — tracked runtime output (daily feed, search, candidates, scored, archive, cards, weekly CSV). Auto-created by `common.data_dir()` / `dump_json()`; safe to delete and regenerate.
- `code/` — shallow clones + wiki snapshots, keyed `full_name.replace("/", "__")`.
- `site/` — gitignored, rebuilt.

## LLM layer

`scripts/agent.py` — OpenAI-compatible client, creds from env **only** (`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`, default `deepseek-chat`). Two functions: `score_repo` (README[:10000]), `build_code_card` (full context text). Both use `_retry_json` (5 attempts, exponential backoff + jitter, `response_format=json_object`; 4xx except 408/429 is permanent → fail fast). Prompts live in `prompts.yaml` (`score`, `code_card`).

## Secrets / config

- Secrets: `LLM_BASE_URL`, `LLM_API_KEY`, optional `ZREAD_TOKEN` (zread wiki submit). Variable: `LLM_MODEL`.
- `config.yaml`: `topic`/`title`/`topic_desc`, `window_days`, `site_base_url`, `github_repo`/`github_branch` (for wiki-snapshot GitHub blob links), `llm.{concurrency,min_score}`, `archive.concurrency`, `search.queries`.
- **`site_base_url` must be set** for project Pages — empty → root-absolute links that 404 on `user.github.io/REPO/`.

## Caveats

- **Filter by `pushed_at`, not `updated_at`.** star/watch/fork bumps `updated_at`; `gh search repos` lacks `--pushed` and the `pushed:` qualifier is silently ignored when combined with `in:`. So search uses `--updated` (a superset) and `search.py` filters client-side by `pushedAt` into the window `[run-window_days, run-1]` — both bounds, since `gh` has no upper-bound flag.
- **The fetch window is one shared definition** — `search.py`/`merge.py`/`cards.py`/`issue.py` all use `[run-window_days, run-1]` (excludes the run day; `window_days` from `config.yaml`). `cards.py` stamps it onto every record and `build_site.py`'s `_window_of` groups by it, so one run's repos land in a single site bucket.
- **Wiki snapshots are append-only.** deepwiki/codewiki/zread have no upstream version history, so each run writes `wikis/{date}/{source}/` and never overwrites past weeks. Re-snapshot only if the wiki's own marker (deepwiki `last_modified`, zread `updated_at`, codewiki `commit_sha` → `gh api`) is in the current week; otherwise reuse (`reused`).
- **Scheduling is native `on.schedule`** — `daily.yml` runs 06:00 daily, `weekly.yml` runs **Sunday** 08:00, both `timezone: "Asia/Shanghai"` (GitHub converts the cron; the `TZ` env still only affects in-job `date`). Because the site groups by the recorded fetch window (above), the run day no longer strands repos in a sparse bucket — Sunday is kept only so the 7-day window (`[prev Sun, Sat]`) lines up with the natural week. Scheduled runs fire only on the default branch and may land late under load (observed up to hours); both workflows keep `workflow_dispatch` for manual reruns; their commit steps share a 3× `git pull --rebase --autostash` → `git push` retry.
- **Manual push doesn't fire the Pages deploy** (gitignored `site/` is never in a commit) — rerun via `gh workflow run deploy_pages.yml`.
- Keep `llm.concurrency` low (default 8); `archive.concurrency` low too (repowiki rate-limits). `users_core.txt` must be a strict subset of `users.txt`.
- Wiki dir `google_code_wiki` is the on-disk name for the `codewiki` source.

## Tool commands

```bash
# local run
pip install -r requirements.txt && pip install ghresearcher pyrepowiki-cli
npm install -g degit && gh auth login
bash scripts/run_weekly.sh
python scripts/build_site.py --out-dir . --config config.yaml

python -m pytest -q                       # tests/ (not part of deploy)
```

`ghresearcher monitor -f <list> [--org] [--since <date>] [--expand-commits] [-r -l 30]`; `repowiki-cli {deepwiki,codewiki,zread} cp <owner/repo> [OUT_DIR]`.
