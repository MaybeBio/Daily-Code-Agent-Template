import json, subprocess
from scripts import gh

def test_search_repos_parses_json(monkeypatch):
    payload = json.dumps([{"fullName": "a/b", "stargazersCount": 3}])
    monkeypatch.setattr(gh, "run", lambda cmd, **kw: payload)
    out = gh.search_repos("q.yaml", ">=2026-09-27", ["fullName", "stargazersCount"])
    assert out[0]["fullName"] == "a/b"

def test_search_repos_parses_python_repr(monkeypatch):
    payload = "[{'fullName': 'a/b', 'stargazersCount': 3}]"
    monkeypatch.setattr(gh, "run", lambda cmd, **kw: payload)
    out = gh.search_repos("q.yaml", ">=2026-09-27", ["fullName", "stargazersCount"])
    assert out[0]["fullName"] == "a/b"

def test_safe_repo_meta_falls_back_on_error(monkeypatch):
    def boom(cmd, **kw):
        raise subprocess.CalledProcessError(1, ["gh"])
    monkeypatch.setattr(gh, "run", boom)
    assert gh.safe_repo_meta("a/b") == {"full_name": "a/b", "url": "", "language": "",
                                        "stars": 0, "description": "", "pushed_at": ""}

def test_repo_meta_maps_fields(monkeypatch):
    raw = json.dumps({"full_name": "a/b", "html_url": "u", "language": "Python",
                      "stargazers_count": 5, "description": "d", "pushed_at": "2026-10-03T00:00:00Z"})
    monkeypatch.setattr(gh, "run", lambda cmd, **kw: raw)
    m = gh.repo_meta("a/b")
    assert m == {"full_name": "a/b", "url": "u", "language": "Python",
                 "stars": 5, "description": "d", "pushed_at": "2026-10-03T00:00:00Z"}

def test_fetch_tree_keeps_code_files_and_drops_dirs_and_data(monkeypatch):
    raw = json.dumps({"tree": [
        {"type": "tree", "path": "src"},
        {"type": "blob", "path": "src/a.py"},
        {"type": "blob", "path": "data/big.h5"},
        {"type": "blob", "path": "README.md"},
    ]})
    monkeypatch.setattr(gh, "run", lambda cmd, **kw: raw)
    assert gh.fetch_tree("a/b").splitlines() == ["README.md", "src/a.py"]

def test_fetch_tree_caps_and_marks_truncation(monkeypatch):
    raw = json.dumps({"tree": [{"type": "blob", "path": f"f{i}.py"} for i in range(250)]})
    monkeypatch.setattr(gh, "run", lambda cmd, **kw: raw)
    lines = gh.fetch_tree("a/b", limit=200).splitlines()
    assert len(lines) == 201 and lines[-1] == "..."
