import argparse, os, shutil, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts import common  # noqa: E402

WIKI_SOURCES = ["deepwiki", "codewiki", "zread"]

def threshold(scored, min_score):
    keep = [r for r in scored if r.get("score") is not None and r["score"] >= min_score]
    keep.sort(key=lambda r: r["score"], reverse=True)
    return keep

def repo_dir(full_name):
    return os.path.join(common.ROOT, "code", full_name.replace("/", "__"))

def _wiki_dir(source):
    return "google_code_wiki" if source == "codewiki" else source

def clone_repo(full_name, dest):
    try:
        subprocess.run(["degit", full_name, dest, "--force"],
                       capture_output=True, text=True, check=True)
        return True
    except Exception:
        return False

def export_wiki(source, full_name, dest):
    try:
        subprocess.run(["repowiki-cli", source, "cp", full_name, dest],
                       capture_output=True, text=True, check=True)
        return True
    except Exception:
        return False

def archive_one(row, clone, wiki):
    full_name = row["full_name"]
    base = repo_dir(full_name)
    shutil.rmtree(base, ignore_errors=True)
    os.makedirs(base, exist_ok=True)
    clone_ok = clone(full_name, os.path.join(base, "code"))
    wikis = {s: wiki(s, full_name, os.path.join(base, _wiki_dir(s))) for s in WIKI_SOURCES}
    return {"full_name": full_name, "score": row.get("score"),
            "one_liner": row.get("one_liner", ""), "clone_ok": clone_ok, "wikis": wikis}

def run(cfg, date, clone=None, wiki=None):
    clone = clone or clone_repo
    wiki = wiki or export_wiki
    min_score = int(cfg.get("llm", {}).get("min_score", 5))
    scored_path = common.data_dir("scored", f"{date}.json")
    scored = common.load_json(scored_path) if os.path.exists(scored_path) else []
    archived = [archive_one(r, clone, wiki) for r in threshold(scored, min_score)]
    common.dump_json(common.data_dir("archive", f"{date}.json"), archived)
    return archived

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(common.ROOT, "config.yaml"))
    ap.add_argument("--date", default=None)
    a = ap.parse_args()
    cfg = common.load_config(a.config)
    date = a.date or common.today()
    print(len(run(cfg, date)))

if __name__ == "__main__":
    main()
