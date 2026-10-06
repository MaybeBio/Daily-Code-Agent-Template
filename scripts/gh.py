import ast, json, os, subprocess

_CODE_EXT = frozenset({
    ".py", ".pyx", ".pxd", ".pyi", ".pyw",
    ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx",
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
    ".java", ".kt", ".kts", ".scala", ".groovy", ".gradle",
    ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh", ".hxx",
    ".rs", ".go", ".zig",
    ".rb", ".rake", ".php", ".phtml", ".pl", ".pm", ".lua", ".tcl",
    ".sh", ".bash", ".zsh", ".fish", ".ps1", ".psm1", ".psd1",
    ".swift", ".m", ".mm",
    ".cs", ".fs", ".fsx", ".vb",
    ".r", ".jl", ".ipynb",
    ".hs", ".lhs", ".elm", ".ex", ".exs", ".erl", ".hrl",
    ".clj", ".cljs", ".cljc", ".edn",
    ".dart", ".vue", ".svelte",
    ".xsl", ".xslt", ".svg",
    ".proto", ".avsc", ".thrift",
    ".tf", ".tfvars", ".hcl",
    ".cmake", ".mk", ".meson",
    ".sql", ".psql",
    ".graphql", ".gql",
    ".md", ".mdx", ".rst", ".markdown",
    ".tex", ".sty", ".cls", ".bib",
})

def run(cmd: list[str], **kw) -> str:
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    kw.setdefault("check", True)
    return subprocess.run(cmd, **kw).stdout

def search_repos(config_path: str, updated: str, fields: list[str],
                 query: str | None = None) -> list[dict]:
    cmd = ["ghresearcher", "search"]
    if query:
        cmd += ["repos", query]
    cmd += ["--config", config_path, "--updated", updated, "--json", ",".join(fields)]
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

def fetch_tree(full_name: str, limit: int = 200) -> str:
    # HEAD + recursive=1 直接取默认分支整棵树,免去先查 default_branch/tree_sha 的两次调用
    out = run(["gh", "api", f"repos/{full_name}/git/trees/HEAD?recursive=1"])
    tree = json.loads(out).get("tree", [])
    paths = sorted(e["path"] for e in tree
                   if e.get("type") == "blob"
                   and os.path.splitext(e.get("path", ""))[1].lower() in _CODE_EXT)
    if len(paths) > limit:
        paths = paths[:limit] + ["..."]
    return "\n".join(paths)

def safe_repo_meta(full_name: str) -> dict:
    try:
        return repo_meta(full_name)
    except Exception:
        return {"full_name": full_name, "url": "", "language": "",
                "stars": 0, "description": "", "pushed_at": ""}
