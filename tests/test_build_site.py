import json, os
from scripts import build_site

def test_score_tier():
    assert build_site.score_tier(8) == "high"
    assert build_site.score_tier(5) == "mid"
    assert build_site.score_tier(3) == "low"
    assert build_site.score_tier(None) == "none"

def test_wiki_url():
    assert build_site.wiki_url("deepwiki", "a/b") == "https://deepwiki.com/a/b"
    assert build_site.wiki_url("codewiki", "a/b") == "https://codewiki.google/github.com/a/b"
    assert build_site.wiki_url("zread", "a/b") == "https://zread.ai/a/b"
    assert build_site.wiki_url("nope", "a/b") == ""

def test_load_cards_empty(tmp_path):
    assert build_site.load_cards(str(tmp_path)) == []

def test_load_issue_url_missing(tmp_path):
    assert build_site.load_issue_url(str(tmp_path)) == ""

def test_site_base_path_and_base_prefix():
    assert build_site.site_base_path("") == ""
    assert build_site.site_base_path("https://example.com/repos/foo") == "/repos/foo"

def test_window_range():
    assert build_site.window_range("2026-10-06", 7) == ("2026-09-30", "2026-10-06")
    assert build_site.window_range("bad", 7) == ("", "")

def _write_cards(tmp_path, rows):
    d = str(tmp_path / "data" / "cards")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "2026-10-05.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)

def test_build_site_renders(tmp_path):
    _write_cards(tmp_path, [{"full_name": "a/b", "url": "https://github.com/a/b",
                             "language": "Python", "stars": 5,
                             "pushed_at": "2026-10-01T00:00:00Z",
                             "score": 8, "one_liner": "one",
                             "card": "## 是什么\nhello"}])
    open(str(tmp_path / "data" / "latest_issue.txt"), "w").write("https://github.com/x/y/issues/1")
    build_site.build_site(str(tmp_path), {"title": "T", "site_base_url": ""})
    idx = open(str(tmp_path / "site" / "index.html"), encoding="utf-8").read()
    assert "当周 Issue" in idx and "https://github.com/x/y/issues/1" in idx
    arch = open(str(tmp_path / "site" / "archive.html"), encoding="utf-8").read()
    assert "a/b" in arch
    detail = open(str(tmp_path / "site" / "repos" / "a__b" / "index.html"), encoding="utf-8").read()
    assert "https://deepwiki.com/a/b" in detail and "hello" in detail

def test_build_site_empty_no_crash(tmp_path):
    build_site.build_site(str(tmp_path), {"title": "T", "site_base_url": ""})
    idx = open(str(tmp_path / "site" / "index.html"), encoding="utf-8").read()
    assert "本周推荐" in idx

def test_build_site_no_issue_link(tmp_path):
    _write_cards(tmp_path, [{"full_name": "a/b", "url": "u", "language": "Py", "stars": 1,
                             "pushed_at": "t", "score": 8,
                             "one_liner": "x", "card": "## 是什么\nhi"}])
    build_site.build_site(str(tmp_path), {"title": "T", "site_base_url": ""})
    idx = open(str(tmp_path / "site" / "index.html"), encoding="utf-8").read()
    assert "当周 Issue" not in idx

def test_build_site_empty_card(tmp_path):
    _write_cards(tmp_path, [{"full_name": "a/b", "url": "u", "language": "Py", "stars": 1,
                             "pushed_at": "t", "score": 8,
                             "one_liner": "x", "card": ""}])
    build_site.build_site(str(tmp_path), {"title": "T", "site_base_url": ""})
    detail = open(str(tmp_path / "site" / "repos" / "a__b" / "index.html"), encoding="utf-8").read()
    assert "Code Card" not in detail

def test_build_site_latest_card_wins(tmp_path):
    d = str(tmp_path / "data" / "cards")
    os.makedirs(d, exist_ok=True)
    older = {"full_name": "a/b", "url": "u", "language": "Py", "stars": 1,
             "pushed_at": "t", "score": 7, "one_liner": "old",
             "card": "## 是什么\nOLD"}
    newer = {"full_name": "a/b", "url": "u", "language": "Py", "stars": 1,
             "pushed_at": "t", "score": 9, "one_liner": "new",
             "card": "## 是什么\nNEW"}
    with open(os.path.join(d, "2026-09-28.json"), "w", encoding="utf-8") as f:
        json.dump([older], f, ensure_ascii=False)
    with open(os.path.join(d, "2026-10-05.json"), "w", encoding="utf-8") as f:
        json.dump([newer], f, ensure_ascii=False)
    build_site.build_site(str(tmp_path), {"title": "T", "site_base_url": ""})
    detail = open(str(tmp_path / "site" / "repos" / "a__b" / "index.html"), encoding="utf-8").read()
    assert "NEW" in detail and "OLD" not in detail
