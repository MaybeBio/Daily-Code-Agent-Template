import argparse, os, sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts import common, agent, gh, archive  # noqa: E402
from scripts.agent import load_prompts  # noqa: E402

def card_record(row, card):
    return {"full_name": row["full_name"], "url": row.get("url", ""),
            "language": row.get("language", ""), "stars": row.get("stars", 0),
            "pushed_at": row.get("pushed_at", ""), "status": row.get("status", ""),
            "score": row["score"], "one_liner": row.get("one_liner", ""), "card": card}

def run(cfg, date, client=None, fetch=None, card_fn=None):
    fetch = fetch or gh.fetch_readme
    client = client if client is not None else agent.make_client()
    card_fn = card_fn or agent.build_code_card
    prompts = load_prompts(os.path.join(common.ROOT, "prompts.yaml"))
    model = agent.model_name()
    min_score = int(cfg.get("llm", {}).get("min_score", 5))
    scored_path = common.data_dir("scored", f"{date}.json")
    scored = common.load_json(scored_path) if os.path.exists(scored_path) else []
    keepers = archive.threshold(scored, min_score)
    def work(row):
        try:
            readme = fetch(row["full_name"])
            res = card_fn(client, model, prompts, common.topic_brief(cfg), readme)
            card = res.get("card", "")
        except Exception as e:
            print(f"[card failed] {row['full_name']}: {e}", file=sys.stderr)
            card = ""
        return card_record(row, card)
    with ThreadPoolExecutor(max_workers=int(cfg.get("llm", {}).get("concurrency", 8))) as ex:
        out = list(ex.map(work, keepers))
    common.dump_json(common.data_dir("cards", f"{date}.json"), out)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(common.ROOT, "config.yaml"))
    ap.add_argument("--date", default=None)
    a = ap.parse_args()
    cfg = common.load_config(a.config)
    date = a.date or common.today()
    out = run(cfg, date)
    print(f"{sum(1 for r in out if r['card'])}/{len(out)} cards")

if __name__ == "__main__":
    main()
