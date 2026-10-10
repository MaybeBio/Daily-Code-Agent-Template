import argparse, os, sys
import yaml
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts import common, gh  # noqa: E402

FIELDS = ["fullName", "url", "language", "stargazersCount", "description", "pushedAt"]

def _norm(d: dict) -> dict:
    return {"full_name": d.get("fullName", ""), "url": d.get("url", ""),
            "language": d.get("language") or "", "stars": d.get("stargazersCount", 0),
            "description": d.get("description") or "", "pushed_at": d.get("pushedAt", "")}

def _queries(search_cfg: dict, qcfg_path: str) -> list[str]:
    if search_cfg.get("queries"):
        return list(search_cfg["queries"])
    with open(qcfg_path, encoding="utf-8") as f:      # 兼容旧式单查询
        q = yaml.safe_load(f) or {}
    if q.get("query"):
        return [q["query"]]
    raise ValueError(f"no queries in config search.queries or {qcfg_path}")

def run(cfg: dict, date: str, since: str) -> list[dict]:
    qcfg = os.path.join(common.ROOT, cfg["search"]["config"])
    merged: dict[str, dict] = {}
    for query in _queries(cfg["search"], qcfg):
        try:
            results = gh.search_repos(qcfg, since, FIELDS, query=query)
        except Exception as e:
            print(f"[search failed] {query}: {e}", file=sys.stderr)
            continue
        for d in results:
            n = _norm(d)
            if n["full_name"]:
                merged[n["full_name"]] = n
    rows = list(merged.values())
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
