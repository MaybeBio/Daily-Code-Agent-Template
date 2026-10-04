import os, subprocess
from scripts import daily

CFG = {"topic": "demo", "title": "Demo", "daily": {"enable_repo_table": True}}

def test_collect_skips_failing_watchlist(monkeypatch, tmp_path):
    for name in ("users", "users_core", "orgs"):
        d = tmp_path / "monitor" / "lists"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.txt").write_text("# comment only\n", encoding="utf-8")
    monkeypatch.setattr(daily.common, "ROOT", str(tmp_path))

    def boom(cmd, **kw):
        raise subprocess.CalledProcessError(1, ["ghresearcher"])

    monkeypatch.setattr(daily.gh, "run", boom)
    cfg = {"daily": {"watchlists": {"users": "monitor/lists/users.txt",
                                    "users_core": "monitor/lists/users_core.txt",
                                    "orgs": "monitor/lists/orgs.txt"}}}
    assert daily.collect("2026-10-04", cfg) == []

def test_build_daily_issue_table():
    table = [{"full_name": "a/b", "who": ["alice"], "event": "star",
              "stars": 5, "language": "Python", "description": "x", "url": "https://g/a/b"}]
    title, body = daily.build_daily_issue(table, raw_lines=12, cfg=CFG, date="2026-10-04")
    assert "2026-10-04" in title
    assert "a/b" in body and "alice" in body and "star" in body
    assert "| repo |" in body

def test_build_daily_issue_disabled_table():
    title, body = daily.build_daily_issue([], raw_lines=0, cfg={"topic": "d", "title": "D",
                                              "daily": {"enable_repo_table": False}}, date="2026-10-04")
    assert "| repo |" not in body
