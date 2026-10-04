import argparse, glob, os, sys
from datetime import date as _date, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts import common, gh  # noqa: E402

def classify(repo: dict, reg_entry: dict | None) -> str:
    if reg_entry is None:
        return "new"
    if (repo.get("pushed_at") or "") != (reg_entry.get("last_commit") or ""):
        return "updated"
    return "seen"

def _recent_daily(date: str, window_days: int) -> list[str]:
    files = sorted(glob.glob(os.path.join(common.ROOT, "data", "daily", "*.repos.json")))
    cutoff = _date.fromisoformat(date) - timedelta(days=window_days)
    keep = []
    for f in files:
        d = os.path.basename(f)[:10]
        try:
            if _date.fromisoformat(d) >= cutoff:
                keep.append(f)
        except ValueError:
            pass
    return keep

def run(cfg: dict, date: str) -> dict:
    pool: dict[str, dict] = {}
    for f in _recent_daily(date, cfg.get("window_days", 7)):
        for r in common.load_json(f):
            pool.setdefault(r["full_name"], dict(r))
    search_path = common.data_dir("search", f"{date}.json")
    if os.path.exists(search_path):
        for r in common.load_json(search_path):
            cur = pool.setdefault(r["full_name"], dict(r))
            # 盲搜带 pushed_at,优先补全
            for k in ("pushed_at", "stars", "language", "description", "url"):
                cur[k] = r.get(k) or cur.get(k, "")
    reg = common.read_registry()
    candidates, seen = [], []
    for full_name, r in pool.items():
        if not r.get("pushed_at"):
            meta = gh.repo_meta(full_name)
            r.update({k: meta[k] for k in ("pushed_at", "stars", "language", "description", "url")})
        status = classify(r, reg["repos"].get(full_name))
        r["status"] = status
        (seen if status == "seen" else candidates).append(r if status != "seen" else full_name)
    candidates.sort(key=lambda r: r.get("stars", 0), reverse=True)
    common.dump_json(common.data_dir("candidates", f"{date}.json"), candidates)
    return {"candidates": candidates, "seen": seen}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(common.ROOT, "config.yaml"))
    a = ap.parse_args()
    cfg = common.load_config(a.config)
    out = run(cfg, common.today())
    print(f"candidates={len(out['candidates'])} seen={len(out['seen'])}")

if __name__ == "__main__":
    main()
