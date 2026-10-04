import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts import common, gh  # noqa: E402

FIELDS = ["fullName", "url", "language", "stargazersCount", "description", "pushedAt"]

def _norm(d: dict) -> dict:
    return {"full_name": d.get("fullName", ""), "url": d.get("url", ""),
            "language": d.get("language") or "", "stars": d.get("stargazersCount", 0),
            "description": d.get("description") or "", "pushed_at": d.get("pushedAt", "")}

def run(cfg: dict, date: str, since: str) -> list[dict]:
    qcfg = os.path.join(common.ROOT, cfg["search"]["config"])
    rows = [_norm(d) for d in gh.search_repos(qcfg, since, FIELDS)]
    rows = [r for r in rows if r["full_name"]]
    common.dump_json(common.data_dir("search", f"{date}.json"), rows)
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(common.ROOT, "config.yaml"))
    ap.add_argument("--since", required=True)   # e.g. ">=2026-09-27"
    a = ap.parse_args()
    cfg = common.load_config(a.config)
    print(len(run(cfg, common.today(), a.since)))

if __name__ == "__main__":
    main()
