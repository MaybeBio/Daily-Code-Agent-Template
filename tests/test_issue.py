import csv
from scripts import issue

SCORED = [
    {"full_name": "a/b", "url": "u", "language": "Py", "stars": 9,
     "pushed_at": "2026-10-03", "status": "updated", "score": 9, "one_liner": "hi"},
    {"full_name": "c/d", "url": "u2", "language": "R", "stars": 2,
     "pushed_at": "2026-10-02", "status": "new", "score": 5, "one_liner": "yo"},
]

def test_issue_groups_and_sorts():
    title, body = issue.build_weekly_issue(SCORED, {"title": "T", "topic": "t"}, "2026-09-27", "2026-10-04")
    assert "1 新增" in title and "1 更新" in title
    assert "## 新增（1）" in body and "## 更新（1）" in body
    # grouped: 新增 section (c/d) precedes 更新 section (a/b); each section present
    assert body.index("## 新增") < body.index("c/d") < body.index("## 更新") < body.index("a/b")

def test_csv_columns(tmp_path):
    p = tmp_path / "w.csv"
    issue.write_csv(SCORED, str(p))
    rows = list(csv.DictReader(open(p)))
    assert list(rows[0].keys()) == ["repo", "url", "language", "stars",
                                    "last_commit", "status", "score", "one_liner"]
