from scripts import score

CFG = {"topic": "demo", "title": "D", "llm": {"concurrency": 2}}
PROMPTS = {"score": {"system": "s", "user": "{topic}\n{readme}"}}

def test_run_scores_and_updates_registry(monkeypatch, tmp_path):
    monkeypatch.setattr(score.common, "ROOT", str(tmp_path))
    score.common.dump_json(str(tmp_path / "data" / "candidates" / "2026-10-04.json"),
                           [{"full_name": "a/b", "url": "u", "pushed_at": "2026-10-03",
                             "stars": 1, "language": "", "description": "", "status": "new"}])
    monkeypatch.setattr(score, "load_prompts", lambda p: PROMPTS)
    monkeypatch.setattr(score.agent, "score_repo",
                        lambda *a, **k: {"score": 9, "one_liner": "nice"})
    rows = score.run(CFG, "2026-10-04", client=object(), fetch=lambda fn: "readme text")
    assert rows[0]["score"] == 9 and rows[0]["one_liner"] == "nice"
    reg = score.common.read_registry()
    assert reg["repos"]["a/b"]["score"] == 9
    assert reg["repos"]["a/b"]["last_scored_commit"] == "2026-10-03"

def test_fetch_failure_is_marked_not_raised(monkeypatch, tmp_path):
    monkeypatch.setattr(score.common, "ROOT", str(tmp_path))
    score.common.dump_json(str(tmp_path / "data" / "candidates" / "2026-10-04.json"),
                           [{"full_name": "a/b", "url": "u", "pushed_at": "2026-10-03",
                             "stars": 1, "language": "", "description": "", "status": "new"}])
    monkeypatch.setattr(score, "load_prompts", lambda p: PROMPTS)
    def boom(fn):
        raise RuntimeError("404")
    rows = score.run(CFG, "2026-10-04", client=object(), fetch=boom)
    assert rows[0]["score"] is None and rows[0]["one_liner"] == "[fetch failed]"
