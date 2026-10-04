import argparse, os, subprocess, sys
from datetime import date as _date, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts import common, logs, gh  # noqa: E402

def collect(date: str, cfg: dict) -> list[dict]:
    root = common.ROOT
    wl = cfg["daily"]["watchlists"]
    y, m = date[:4], date[5:7]
    since = (_date.fromisoformat(date) - timedelta(days=1)).isoformat()  # ghresearcher 需 YYYY-MM-DD
    table: dict = {}
    for key, is_org, received in (("users", False, False), ("orgs", True, False),
                                  ("users_core", False, True)):
        list_path = os.path.join(root, wl[key])
        if not os.path.exists(list_path):
            continue
        subdir = {"users": "users", "orgs": "orgs", "users_core": "received"}[key]
        out_dir = os.path.join(root, "monitor", subdir, y, m)
        os.makedirs(out_dir, exist_ok=True)
        cmd = ["ghresearcher", "monitor", "-f", list_path, "--since", since,
               "--expand-commits"]
        if is_org:
            cmd.append("--org")
        if received:
            cmd += ["-r", "-l", "30"]
        try:
            text = gh.run(cmd)
        except subprocess.CalledProcessError as e:
            print(f"[daily] watchlist {key} skipped: {e}", file=sys.stderr)
            continue
        with open(os.path.join(out_dir, f"{date[8:10]}.txt"), "w", encoding="utf-8") as f:
            f.write(text)
        for full_name, info in logs.repos_from_events(logs.extract_events(text)).items():
            e = table.setdefault(full_name, {"full_name": full_name, "who": [], "event": ""})
            e["who"] = sorted(set(e["who"]) | set(info["who"]))
            e["event"] = info["kinds"][0] if len(info["kinds"]) == 1 else "mixed"
    rows = []
    for full_name, e in table.items():
        meta = gh.safe_repo_meta(full_name)
        rows.append({**e, "stars": meta["stars"], "language": meta["language"],
                     "description": meta["description"], "url": meta["url"]})
    rows.sort(key=lambda r: r["stars"], reverse=True)
    return rows

def build_daily_issue(repo_table: list[dict], raw_lines: int, cfg: dict, date: str) -> tuple[str, str]:
    title = f"\U0001F4E1 每日动态 {date} · {cfg.get('title', '')}".strip()
    body = [f"# {title}", "",
            f"- 原始动态行数:{raw_lines}",
            f"- 候选仓库:{len(repo_table)}", ""]
    if cfg.get("daily", {}).get("enable_repo_table", True) and repo_table:
        body += ["## 今日候选仓库(免费元数据,未做 LLM)", "",
                 "| repo | 谁 | 事件 | stars | language | description |",
                 "|---|---|---|---|---|---|"]
        for r in repo_table:
            body.append("| [{0}]({1}) | {2} | {3} | {4} | {5} | {6} |".format(
                r["full_name"], r["url"], ", ".join(r["who"]), r["event"],
                r["stars"], r["language"], (r["description"] or "").replace("|", "\\|")))
    return title, "\n".join(body) + "\n"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(common.ROOT, "config.yaml"))
    ap.add_argument("--out-dir", default=common.ROOT)
    ap.add_argument("--issue-body", required=True)
    ap.add_argument("--issue-title", required=True)
    a = ap.parse_args()
    cfg = common.load_config(a.config)
    date = common.today()
    table = collect(date, cfg)
    y, m, dd = date[:4], date[5:7], date[8:10]
    raw_lines = 0
    for sub in ("users", "orgs", "received"):
        p = os.path.join(common.ROOT, "monitor", sub, y, m, f"{dd}.txt")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                raw_lines += sum(1 for ln in fh if ln.strip())
    common.dump_json(common.data_dir("daily", f"{date}.repos.json"), table)
    title, body = build_daily_issue(table, raw_lines=raw_lines, cfg=cfg, date=date)
    open(a.issue_body, "w", encoding="utf-8").write(body)
    open(a.issue_title, "w", encoding="utf-8").write(title)

if __name__ == "__main__":
    main()
