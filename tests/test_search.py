from scripts import search

def test_run_normalizes_and_writes(monkeypatch, tmp_path):
    monkeypatch.setattr(search.common, "ROOT", str(tmp_path))
    monkeypatch.setattr(search.gh, "search_repos", lambda *a, **k: [{
        "fullName": "a/b", "url": "u", "language": "Python", "stargazersCount": 7,
        "description": "d", "pushedAt": "2026-10-03T00:00:00Z"}])
    rows = search.run({"search": {"config": "q.yaml"}}, "2026-10-04", ">=2026-09-27")
    assert rows[0]["full_name"] == "a/b" and rows[0]["stars"] == 7
    assert (tmp_path / "data" / "search" / "2026-10-04.json").exists()
