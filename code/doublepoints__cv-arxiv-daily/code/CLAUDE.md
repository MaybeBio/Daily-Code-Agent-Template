# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Automated system that fetches Computer Vision papers from arXiv daily, organized by configurable topic categories. Uses GitHub Actions as a scheduler to update a curated paper catalog with code links from PaperWithCode.

## Commands

```bash
# Daily paper fetch (primary operation)
python daily_arxiv.py --config_path config.yaml

# Weekly update of missing code links for existing papers
python daily_arxiv.py --config_path config.yaml --update_paper_links

# Install dependencies
pip install -r requirements.txt   # arxiv, requests, pyyaml
```

## Architecture

### Data Pipeline

`config.yaml` (keyword definitions) -> `get_daily_papers()` (arXiv API + PaperWithCode API) -> JSON files -> `json_to_md()` -> Markdown outputs

### Key Components in `daily_arxiv.py`

- **`load_config()`** - Parses YAML config into query strings. The `pretty_filters()` inner function converts keyword lists into quoted OR-joined arXiv query strings.
- **`get_daily_papers()`** - Fetches papers via `arxiv.Search()`, then checks PaperWithCode API (`arxiv.paperswithcode.com`) for official code repos. Returns two dicts: one for markdown table format, one for web/list format.
- **`update_json_file()`** - Merges new papers into existing JSON, filtering to only keep categories present in current config keywords.
- **`update_paper_links()`** - Re-checks PaperWithCode for papers that previously had no code link (`|null|`).
- **`json_to_md()`** - Converts JSON to markdown with table of contents, badges, back-to-top links, and LaTeX math prettification. Three output modes controlled by flags: README (default), web (GitHub Pages), WeChat.
- **`demo()`** - Orchestrates the full pipeline: fetch all topics, update 3 JSON stores, generate 3 markdown outputs.

### Output Targets

| Target | JSON Source | Markdown Output | Notes |
|--------|-----------|----------------|-------|
| README | `docs/cv-arxiv-daily.json` | `README.md` | Main catalog, table format |
| GitHub Pages | `docs/cv-arxiv-daily-web.json` | `docs/index.md` | Jekyll layout, no TOC/back-to-top |
| WeChat | `docs/cv-arxiv-daily-wechat.json` | `docs/wechat.md` | List format, no title |

### Configuration (`config.yaml`)

- `keywords` dict defines topic categories, each with a `filters` list of search terms
- `max_results` controls papers per keyword per run (default: 10)
- `publish_readme/publish_gitpage/publish_wechat` toggles each output target
- JSON/markdown paths are configurable

### GitHub Actions

- **`cv-arxiv-daily.yml`** - Runs every 12 hours (0:00/12:00 UTC), executes daily paper fetch, commits updated files
- **`update_paper_links.yml`** - Runs Mondays 08:00 UTC, updates missing code links only

### Paper Data Format

Papers are stored in JSON as `{category: {arxiv_id: markdown_row_string}}`. The markdown row contains pipe-delimited fields: date, title, first author, PDF link, code link (or "null").
