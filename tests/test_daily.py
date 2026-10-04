from scripts import daily

CFG = {"topic": "demo", "title": "Demo", "daily": {"enable_repo_table": True}}

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
