import argparse, os, sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts import common, agent, gh  # noqa: E402
from scripts.agent import load_prompts  # noqa: E402

def _score_one(row, cfg, client, prompts, model, fetch):
    readme = fetch(row["full_name"])
    return agent.score_repo(client, model, prompts, common.topic_brief(cfg), readme)

def run(cfg, date, client=None, fetch=None):
    fetch = fetch or gh.fetch_readme
    client = client if client is not None else agent.make_client()
    prompts = load_prompts(os.path.join(common.ROOT, "prompts.yaml"))
    model = agent.model_name()
    cand_path = common.data_dir("candidates", f"{date}.json")
    candidates = common.load_json(cand_path) if os.path.exists(cand_path) else []
    out = []
    def work(row):
        try:
            res = _score_one(row, cfg, client, prompts, model, fetch)
        except Exception:
            res = {"score": None, "one_liner": "[fetch failed]"}
        return {**row, **res}
    with ThreadPoolExecutor(max_workers=int(cfg.get("llm", {}).get("concurrency", 8))) as ex:
        out = list(ex.map(work, candidates))
    common.dump_json(common.data_dir("scored", f"{date}.json"), out)
    reg = common.read_registry()
    reg["topic"] = cfg["topic"]
    for r in out:
        if r["score"] is None:
            continue
        reg["repos"][r["full_name"]] = {
            "first_seen": reg["repos"].get(r["full_name"], {}).get("first_seen", date),
            "last_seen": date, "last_commit": r.get("pushed_at", ""),
            "last_scored_commit": r.get("pushed_at", ""),
            "score": r["score"], "one_liner": r["one_liner"]}
    common.write_registry(reg)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(common.ROOT, "config.yaml"))
    a = ap.parse_args()
    cfg = common.load_config(a.config)
    print(len(run(cfg, common.today())))

if __name__ == "__main__":
    main()
