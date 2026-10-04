from scripts import search, merge, score, issue

def _wire(monkeypatch, tmp_path, pushed_at):
    for mod in (search, merge, score):
        monkeypatch.setattr(mod.common, "ROOT", str(tmp_path))
    monkeypatch.setattr(search.common, "today", lambda: "2026-10-04")
    monkeypatch.setattr(merge.common, "today", lambda: "2026-10-04")
    monkeypatch.setattr(score.common, "today", lambda: "2026-10-04")
    monkeypatch.setattr(search.gh, "search_repos",
                        lambda *a, **k: [{"fullName": "a/b", "url": "u", "language": "Py",
                                          "stargazersCount": 9, "description": "d",
                                          "pushedAt": pushed_at}])
    monkeypatch.setattr(merge.gh, "repo_meta",
                        lambda fn: {"pushed_at": pushed_at, "stars": 9, "language": "Py",
                                    "description": "d", "url": "u"})
    monkeypatch.setattr(score, "load_prompts", lambda p: {"score": {"system": "", "user": "{topic}{readme}"}})
    monkeypatch.setattr(score.agent, "score_repo", lambda *a, **k: {"score": 8, "one_liner": "n"})
    monkeypatch.setattr(score.agent, "model_name", lambda: "m")

def test_e2e_then_seen_on_second_run(monkeypatch, tmp_path):
    _wire(monkeypatch, tmp_path, "2026-10-03")
    cfg = {"topic": "t", "title": "T", "window_days": 7, "llm": {"concurrency": 1},
           "search": {"config": "q.yaml"}}
    search.run(cfg, "2026-10-04", ">=2026-09-27")
    cands = merge.run(cfg, "2026-10-04")["candidates"]
    assert len(cands) == 1 and cands[0]["status"] == "new"
    scored = score.run(cfg, "2026-10-04", client=object(), fetch=lambda fn: "readme")
    title, body = issue.build_weekly_issue(scored, cfg, "2026-09-27", "2026-10-04")
    assert "1 新增" in title and "a/b" in body
    # 第二次:commit 未变 → seen,候选为空
    assert merge.run(cfg, "2026-10-04")["candidates"] == []
