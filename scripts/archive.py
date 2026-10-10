import argparse, os, random, shutil, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts import common  # noqa: E402

WIKI_SOURCES = ["deepwiki", "codewiki", "zread"]

# 仓库在该 wiki 源上尚未被索引(404/not indexed),与瞬时网络故障区分。
_NOT_INDEXED_MARKERS = (
    "404", "not found", "not indexed", "no pages", "no wiki",
    "no documentation", "does not exist", "is empty", "empty repository",
)
# 永久性失败(索引缺失 + 认证/配置错误):重试也救不回,直接放弃。
_PERMANENT_MARKERS = _NOT_INDEXED_MARKERS + (
    "invalid", "authentication failed", "bad credentials", "requires authentication",
)

def threshold(scored, min_score):
    keep = [r for r in scored if r.get("score") is not None and r["score"] >= min_score]
    keep.sort(key=lambda r: r["score"], reverse=True)
    return keep

def repo_dir(full_name):
    return os.path.join(common.ROOT, "code", full_name.replace("/", "__"))

def _wiki_dir(source):
    return "google_code_wiki" if source == "codewiki" else source

def _error_text(err):
    if isinstance(err, subprocess.CalledProcessError):
        return f"{err.stderr or ''} {err.stdout or ''}".lower()
    return str(err).lower()

def _is_not_indexed(err):
    return any(m in _error_text(err) for m in _NOT_INDEXED_MARKERS)

def _is_permanent(err):
    return any(m in _error_text(err) for m in _PERMANENT_MARKERS)

def _run_retry(cmd, tag, attempts=5):
    last = None
    for i in range(attempts):
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            return True, None
        except Exception as e:
            last = e
            if _is_permanent(e):      # 404/无此仓库/认证错 → 别再白试
                break
            if i < attempts - 1:
                time.sleep(2 ** (i + 2) + random.random())
    print(f"[{tag} failed] {' '.join(cmd)}: {last}", file=sys.stderr)
    return False, last

def clone_repo(full_name, dest):
    ok, _ = _run_retry(["degit", full_name, dest, "--force"], "clone")
    if ok:
        return True
    shutil.rmtree(dest, ignore_errors=True)  # degit 可能留下半截目录
    ok, _ = _run_retry(["git", "clone", "--depth", "1",
                        f"https://github.com/{full_name}.git", dest], "clone:git")
    return ok

def _submit_zread(full_name):
    if not os.environ.get("ZREAD_TOKEN"):
        return False, None
    return _run_retry(["repowiki-cli", "zread", "submit", full_name], "wiki:zread:submit")

def export_wiki(source, full_name, dest):
    ok, err = _run_retry(["repowiki-cli", source, "cp", full_name, dest], f"wiki:{source}")
    if ok:
        return "ok"
    if source == "zread" and _is_not_indexed(err):
        sub_ok, _ = _submit_zread(full_name)
        if sub_ok:
            return "submitted"
    return "not_indexed" if _is_not_indexed(err) else "failed"

def archive_one(row, clone, wiki):
    full_name = row["full_name"]
    base = repo_dir(full_name)
    shutil.rmtree(base, ignore_errors=True)
    os.makedirs(base, exist_ok=True)
    clone_ok = clone(full_name, os.path.join(base, "code"))
    wikis = {s: wiki(s, full_name, os.path.join(base, _wiki_dir(s))) for s in WIKI_SOURCES}
    return {"full_name": full_name, "score": row.get("score"),
            "one_liner": row.get("one_liner", ""), "clone_ok": clone_ok, "wikis": wikis}

def _safe_archive_one(row, clone, wiki):
    try:
        return archive_one(row, clone, wiki)
    except Exception as e:
        print(f"[archive failed] {row['full_name']}: {e}", file=sys.stderr)
        return {"full_name": row["full_name"], "score": row.get("score"),
                "one_liner": row.get("one_liner", ""), "clone_ok": False,
                "wikis": {s: "failed" for s in WIKI_SOURCES}}

def run(cfg, date, clone=None, wiki=None):
    clone = clone or clone_repo
    wiki = wiki or export_wiki
    min_score = int(cfg.get("llm", {}).get("min_score", 5))
    scored_path = common.data_dir("scored", f"{date}.json")
    scored = common.load_json(scored_path) if os.path.exists(scored_path) else []
    keep = threshold(scored, min_score)
    # 低并发:网络工具(degit/repowiki-cli)串行太慢,但太高会触发 repowiki 限流。
    workers = max(1, int(cfg.get("archive", {}).get("concurrency", 4)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        archived = list(ex.map(lambda r: _safe_archive_one(r, clone, wiki), keep))
    common.dump_json(common.data_dir("archive", f"{date}.json"), archived)
    return archived

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(common.ROOT, "config.yaml"))
    ap.add_argument("--date", default=None)
    a = ap.parse_args()
    cfg = common.load_config(a.config)
    date = a.date or common.today()
    out = run(cfg, date)
    ok_clone = sum(1 for r in out if r["clone_ok"])
    parts = [f"{len(out)} archived; clone ok {ok_clone}/{len(out)}"]
    for s in WIKI_SOURCES:
        counts = {st: sum(1 for r in out if r["wikis"].get(s) == st)
                  for st in ("ok", "submitted", "not_indexed", "failed")}
        nonzero = " ".join(f"{st}:{n}" for st, n in counts.items() if n)
        parts.append(f"{s} {nonzero or '-'}")
    print("; ".join(parts))

if __name__ == "__main__":
    main()
