import json
from scripts import gh

def test_search_repos_parses_json(monkeypatch):
    payload = json.dumps([{"fullName": "a/b", "stargazersCount": 3}])
    monkeypatch.setattr(gh, "run", lambda cmd, **kw: payload)
    out = gh.search_repos("q.yaml", ">=2026-09-27", ["fullName", "stargazersCount"])
    assert out[0]["fullName"] == "a/b"

def test_repo_meta_maps_fields(monkeypatch):
    raw = json.dumps({"full_name": "a/b", "html_url": "u", "language": "Python",
                      "stargazers_count": 5, "description": "d", "pushed_at": "2026-10-03T00:00:00Z"})
    monkeypatch.setattr(gh, "run", lambda cmd, **kw: raw)
    m = gh.repo_meta("a/b")
    assert m == {"full_name": "a/b", "url": "u", "language": "Python",
                 "stars": 5, "description": "d", "pushed_at": "2026-10-03T00:00:00Z"}
