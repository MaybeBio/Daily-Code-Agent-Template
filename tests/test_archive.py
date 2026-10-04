import os
from scripts import archive

def test_threshold_filters_and_sorts():
    scored = [
        {"full_name": "a/b", "score": 3},
        {"full_name": "c/d", "score": 9},
        {"full_name": "e/f", "score": None},
        {"full_name": "g/h", "score": 5},
    ]
    out = archive.threshold(scored, 5)
    assert [r["full_name"] for r in out] == ["c/d", "g/h"]

def test_repo_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(archive.common, "ROOT", str(tmp_path))
    assert archive.repo_dir("MaybeBio/GhResearcher") == str(tmp_path / "code" / "MaybeBio__GhResearcher")

def test_run_archives_only_threshold(monkeypatch, tmp_path):
    monkeypatch.setattr(archive.common, "ROOT", str(tmp_path))
    scored = [
        {"full_name": "hi/a", "score": 9, "one_liner": "x", "pushed_at": "t"},
        {"full_name": "lo/b", "score": 2, "one_liner": "y", "pushed_at": "t"},
    ]
    archive.common.dump_json(str(tmp_path / "data" / "scored" / "2026-10-05.json"), scored)
    clone_calls, wiki_calls = [], []
    out = archive.run({"llm": {"min_score": 5}}, "2026-10-05",
                      clone=lambda fn, d: clone_calls.append(fn) or True,
                      wiki=lambda s, fn, d: wiki_calls.append((s, fn)) or True)
    assert [r["full_name"] for r in out] == ["hi/a"]
    assert clone_calls == ["hi/a"]
    assert sorted(s for s, _ in wiki_calls) == ["codewiki", "deepwiki", "zread"]
    saved = archive.common.load_json(str(tmp_path / "data" / "archive" / "2026-10-05.json"))
    assert [r["full_name"] for r in saved] == ["hi/a"]
    assert saved[0]["clone_ok"] is True

def test_run_isolates_clone_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(archive.common, "ROOT", str(tmp_path))
    archive.common.dump_json(str(tmp_path / "data" / "scored" / "2026-10-05.json"),
                             [{"full_name": "a/b", "score": 8, "one_liner": "x"}])
    out = archive.run({"llm": {"min_score": 5}}, "2026-10-05",
                      clone=lambda fn, d: False, wiki=lambda s, fn, d: True)
    assert out[0]["clone_ok"] is False
    assert out[0]["wikis"]["deepwiki"] is True   # wiki 仍继续

def test_run_isolates_wiki_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(archive.common, "ROOT", str(tmp_path))
    archive.common.dump_json(str(tmp_path / "data" / "scored" / "2026-10-05.json"),
                             [{"full_name": "a/b", "score": 8, "one_liner": "x"}])
    out = archive.run({"llm": {"min_score": 5}}, "2026-10-05",
                      clone=lambda fn, d: True, wiki=lambda s, fn, d: s != "zread")
    assert out[0]["wikis"] == {"deepwiki": True, "codewiki": True, "zread": False}

def test_run_overwrites_existing_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(archive.common, "ROOT", str(tmp_path))
    archive.common.dump_json(str(tmp_path / "data" / "scored" / "2026-10-05.json"),
                             [{"full_name": "a/b", "score": 8, "one_liner": "x"}])
    base = str(tmp_path / "code" / "a__b")
    os.makedirs(os.path.join(base, "code"), exist_ok=True)
    open(os.path.join(base, "code", "stale.txt"), "w").write("old")
    def fake_clone(fn, dest):
        os.makedirs(dest, exist_ok=True)
        open(os.path.join(dest, "fresh.txt"), "w").write("new")
        return True
    def fake_wiki(src, fn, dest):
        os.makedirs(dest, exist_ok=True)
        return True
    archive.run({"llm": {"min_score": 5}}, "2026-10-05", clone=fake_clone, wiki=fake_wiki)
    assert not os.path.exists(os.path.join(base, "code", "stale.txt"))
    assert os.path.exists(os.path.join(base, "code", "fresh.txt"))

def test_run_defaults_min_score_when_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(archive.common, "ROOT", str(tmp_path))
    archive.common.dump_json(str(tmp_path / "data" / "scored" / "2026-10-05.json"),
                             [{"full_name": "a/b", "score": 4, "one_liner": "x"},
                              {"full_name": "c/d", "score": 6, "one_liner": "y"}])
    out = archive.run({}, "2026-10-05", clone=lambda fn, d: True, wiki=lambda s, fn, d: True)
    assert [r["full_name"] for r in out] == ["c/d"]

def test_run_missing_scored_yields_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(archive.common, "ROOT", str(tmp_path))
    calls = []
    out = archive.run({"llm": {"min_score": 5}}, "2026-10-05",
                      clone=lambda fn, d: calls.append(fn) or True,
                      wiki=lambda s, fn, d: calls.append(s) or True)
    assert out == [] and calls == []

def test_clone_repo_command(monkeypatch):
    captured = {}
    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
    monkeypatch.setattr(archive.subprocess, "run", fake_run)
    assert archive.clone_repo("a/b", "/dest") is True
    assert captured["cmd"] == ["degit", "a/b", "/dest", "--force"]

def test_export_wiki_command(monkeypatch):
    captured = []
    monkeypatch.setattr(archive.subprocess, "run",
                        lambda cmd, **kw: captured.append(cmd) or None)
    archive.export_wiki("codewiki", "a/b", "/dest")
    assert captured == [["repowiki-cli", "codewiki", "cp", "a/b", "/dest"]]

def test_wiki_dest_uses_google_code_wiki_for_codewiki(monkeypatch, tmp_path):
    monkeypatch.setattr(archive.common, "ROOT", str(tmp_path))
    archive.common.dump_json(str(tmp_path / "data" / "scored" / "2026-10-05.json"),
                             [{"full_name": "a/b", "score": 8, "one_liner": "x"}])
    dests = {}
    def fake_clone(fn, dest):
        return True
    def fake_wiki(src, fn, dest):
        dests[src] = dest
        return True
    archive.run({"llm": {"min_score": 5}}, "2026-10-05", clone=fake_clone, wiki=fake_wiki)
    assert dests["deepwiki"].endswith("deepwiki")
    assert dests["zread"].endswith("zread")
    assert dests["codewiki"].endswith("google_code_wiki")

def test_run_isolates_raising_archive(monkeypatch, tmp_path):
    monkeypatch.setattr(archive.common, "ROOT", str(tmp_path))
    archive.common.dump_json(str(tmp_path / "data" / "scored" / "2026-10-05.json"),
                             [{"full_name": "a/b", "score": 8, "one_liner": "x"}])
    def raise_clone(fn, dest):
        raise RuntimeError("boom")
    out = archive.run({"llm": {"min_score": 5}}, "2026-10-05", clone=raise_clone,
                      wiki=lambda s, fn, d: True)
    assert out[0]["clone_ok"] is False
    assert out[0]["wikis"] == {"deepwiki": False, "codewiki": False, "zread": False}
