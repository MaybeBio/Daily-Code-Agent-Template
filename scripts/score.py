import argparse, os, sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts import common, agent, gh  # noqa: E402
from scripts.agent import load_prompts  # noqa: E402

def _fallback_text(row, tree):
    desc = (row.get("description") or "").strip()
    if not desc and not tree:
        return ""
    parts = [f"仓库:{row['full_name']}"]
    if row.get("language"):
        parts.append(f"语言:{row['language']}")
    if desc:
        parts.append(f"描述:{desc}")
    if tree:
        parts.append(f"目录树:\n{tree}")
    return "\n".join(parts)

def _score_one(row, cfg, client, prompts, model, fetch, fetch_tree):
    try:
        readme = fetch(row["full_name"])
    except Exception:
        readme = ""
    text = (readme or "").strip()
    if not text:
        try:
            tree = fetch_tree(row["full_name"])
        except Exception:
            tree = ""
        text = _fallback_text(row, tree)
    if not text:
        return {"score": 0, "one_liner": "无 README/描述/目录树,跳过"}
    return agent.score_repo(client, model, prompts, common.topic_brief(cfg), text)

def run(cfg, date, client=None, fetch=None, fetch_tree=None):
    fetch = fetch or gh.fetch_readme
    fetch_tree = fetch_tree or gh.fetch_tree
    client = client if client is not None else agent.make_client()
    prompts = load_prompts(os.path.join(common.ROOT, "prompts.yaml"))
    model = agent.model_name()
    cand_path = common.data_dir("candidates", f"{date}.json")
    candidates = common.load_json(cand_path) if os.path.exists(cand_path) else []
    out = []
    def work(row):
        try:
            res = _score_one(row, cfg, client, prompts, model, fetch, fetch_tree)
        except Exception:
            res = {"score": None, "one_liner": "[llm failed]"}
        return {**row, **res}
    with ThreadPoolExecutor(max_workers=int(cfg.get("llm", {}).get("concurrency", 8))) as ex:
        out = list(ex.map(work, candidates))
    common.dump_json(common.data_dir("scored", f"{date}.json"), out)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(common.ROOT, "config.yaml"))
    a = ap.parse_args()
    cfg = common.load_config(a.config)
    print(len(run(cfg, common.today())))

if __name__ == "__main__":
    main()
