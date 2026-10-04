import ast, json, subprocess

def run(cmd: list[str], **kw) -> str:
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    kw.setdefault("check", True)
    return subprocess.run(cmd, **kw).stdout

def search_repos(config_path: str, updated: str, fields: list[str]) -> list[dict]:
    cmd = ["ghresearcher", "search", "--config", config_path,
           "--updated", updated, "--json", ",".join(fields)]
    out = run(cmd)
    start, end = out.find("["), out.rfind("]")
    if start == -1 or end <= start:
        raise ValueError(f"no result array in ghresearcher stdout: {out[:500]!r}")
    return ast.literal_eval(out[start:end + 1])

def repo_meta(full_name: str) -> dict:
    out = run(["gh", "api", f"repos/{full_name}"])
    d = json.loads(out)
    return {"full_name": d["full_name"], "url": d.get("html_url", ""),
            "language": d.get("language") or "", "stars": d.get("stargazers_count", 0),
            "description": d.get("description") or "", "pushed_at": d.get("pushed_at", "")}

def fetch_readme(full_name: str) -> str:
    return run(["gh", "api", f"repos/{full_name}/readme",
                "-H", "Accept: application/vnd.github.raw"])

def safe_repo_meta(full_name: str) -> dict:
    try:
        return repo_meta(full_name)
    except Exception:
        return {"full_name": full_name, "url": "", "language": "",
                "stars": 0, "description": "", "pushed_at": ""}
