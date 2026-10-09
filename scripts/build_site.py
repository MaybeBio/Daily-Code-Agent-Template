import argparse, json, os, shutil
import datetime as dt
from urllib.parse import urlparse
import markdown as md
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATES = os.path.join(os.path.dirname(HERE), "templates")
WIKI_SOURCES = ["deepwiki", "codewiki", "zread"]

def load_config(path):
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if not isinstance(cfg, dict):
        raise ValueError("config must be a YAML mapping")
    return cfg

def window_range(end_date, window_days):
    """由本周运行日期与 window_days 反推搜索窗口 [start, end]。"""
    try:
        d = dt.date.fromisoformat((end_date or "")[:10])
    except ValueError:
        return "", ""
    return (d - dt.timedelta(days=window_days - 1)).isoformat(), d.isoformat()

def site_base_path(site_base_url):
    url = (site_base_url or "").strip()
    if not url:
        return ""
    return urlparse(url).path.rstrip("/")

def score_tier(score):
    try:
        s = int(score)
    except (TypeError, ValueError):
        return "none"
    if s >= 8:
        return "high"
    if s >= 5:
        return "mid"
    return "low"

def wiki_url(source, full_name):
    if source == "deepwiki":
        return f"https://deepwiki.com/{full_name}"
    if source == "codewiki":
        return f"https://codewiki.google/github.com/{full_name}"
    if source == "zread":
        return f"https://zread.ai/{full_name}"
    return ""

def repo_dir_name(full_name):
    return full_name.replace("/", "__")

def load_cards(out_dir):
    cards_root = os.path.join(out_dir, "data", "cards")
    if not os.path.isdir(cards_root):
        return []
    records = []
    for fname in sorted(os.listdir(cards_root)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(cards_root, fname), encoding="utf-8") as f:
            rows = json.load(f)
        for r in rows:
            records.append({**r, "date": fname[:-5]})
    records.sort(key=lambda r: r.get("date") or "", reverse=True)
    return records

def load_issue_url(out_dir):
    path = os.path.join(out_dir, "data", "latest_issue.txt")
    if not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read().strip()

def _md_to_html(text):
    return md.markdown(text or "", extensions=["tables", "fenced_code", "sane_lists"])

def build_site(out_dir, config=None):
    cfg = config or {}
    base_path = site_base_path(cfg.get("site_base_url") or "")
    site_title = (cfg.get("title") or cfg.get("topic") or "").strip()
    records = load_cards(out_dir)
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))
    env.globals["BASE"] = base_path
    env.globals["SITE_TITLE"] = site_title
    env.globals["score_tier"] = score_tier
    env.globals["wiki_url"] = wiki_url
    env.globals["repo_dir_name"] = repo_dir_name
    env.globals["WIKI_SOURCES"] = WIKI_SOURCES

    site_dir = os.path.join(out_dir, "site")
    assets_dir = os.path.join(site_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    latest_date = records[0]["date"] if records else ""
    this_week = [r for r in records if r["date"] == latest_date] if records else []
    issue_url = load_issue_url(out_dir)
    window_start, window_end = window_range(latest_date, int(cfg.get("window_days", 7)))

    latest_by_repo = {}
    for r in records:
        latest_by_repo.setdefault(r["full_name"], r)
    for r in latest_by_repo.values():
        page = env.get_template("code.html").render(repo=r, card_html=_md_to_html(r.get("card", "")))
        page_dir = os.path.join(site_dir, "repos", repo_dir_name(r["full_name"]))
        os.makedirs(page_dir, exist_ok=True)
        with open(os.path.join(page_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(page)

    with open(os.path.join(site_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(env.get_template("index.html").render(
            window_start=window_start, window_end=window_end,
            repos=this_week, issue_url=issue_url, total=len(records)))

    by_date = {}
    for r in records:
        by_date.setdefault(r["date"], []).append(r)
    weeks = [{"date": d, "repos": by_date[d]} for d in sorted(by_date, reverse=True)]
    with open(os.path.join(site_dir, "archive.html"), "w", encoding="utf-8") as f:
        f.write(env.get_template("archive.html").render(weeks=weeks, total=len(records)))

    shutil.copy(os.path.join(TEMPLATES, "assets", "style.css"),
                os.path.join(assets_dir, "style.css"))

def main():
    parser = argparse.ArgumentParser(description="Build the static site from data/.")
    parser.add_argument("--out-dir", default=".", help="Repo root")
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    args = parser.parse_args()
    cfg = load_config(args.config) if args.config else None
    build_site(args.out_dir, cfg)

if __name__ == "__main__":
    main()
