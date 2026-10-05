import types
from scripts import cards, agent

PROMPTS = {"code_card": {"system": "s", "user": "{topic}\n{readme}"}}

def _fake_client(content):
    msg = types.SimpleNamespace(content=content)
    resp = types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])
    return types.SimpleNamespace(chat=types.SimpleNamespace(
        completions=types.SimpleNamespace(create=lambda **kw: resp)))

def test_card_record_shape():
    row = {"full_name": "a/b", "url": "https://github.com/a/b", "language": "Python",
           "stars": 5, "pushed_at": "t", "status": "new", "score": 8, "one_liner": "x"}
    out = cards.card_record(row, "## 是什么\n...")
    assert out == {"full_name": "a/b", "url": "https://github.com/a/b", "language": "Python",
                   "stars": 5, "pushed_at": "t", "status": "new", "score": 8,
                   "one_liner": "x", "card": "## 是什么\n..."}

def test_run_cards_only_keepers(monkeypatch, tmp_path):
    monkeypatch.setattr(cards.common, "ROOT", str(tmp_path))
    scored = [
        {"full_name": "hi/a", "url": "u", "language": "Python", "stars": 1, "status": "new",
         "score": 9, "one_liner": "x"},
        {"full_name": "lo/b", "url": "u", "language": "Go", "stars": 1, "status": "new",
         "score": 2, "one_liner": "y"},
    ]
    cards.common.dump_json(str(tmp_path / "data" / "scored" / "2026-10-05.json"), scored)
    monkeypatch.setattr(cards, "load_prompts", lambda p: PROMPTS)
    out = cards.run({"llm": {"min_score": 5}, "topic": "t"}, "2026-10-05",
                    client=object(), fetch=lambda fn: "README",
                    card_fn=lambda c, m, p, topic, readme: {"card": "card:" + readme})
    assert [r["full_name"] for r in out] == ["hi/a"]
    saved = cards.common.load_json(str(tmp_path / "data" / "cards" / "2026-10-05.json"))
    assert saved[0]["card"] == "card:README"
    assert set(saved[0]) == {"full_name", "url", "language", "stars", "pushed_at",
                             "status", "score", "one_liner", "card"}

def test_run_card_failure_is_isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(cards.common, "ROOT", str(tmp_path))
    cards.common.dump_json(str(tmp_path / "data" / "scored" / "2026-10-05.json"),
                           [{"full_name": "a/b", "url": "u", "language": "Py", "stars": 1,
                             "status": "new", "score": 8, "one_liner": "x"}])
    monkeypatch.setattr(cards, "load_prompts", lambda p: PROMPTS)
    def boom(fn):
        raise RuntimeError("fetch failed")
    out = cards.run({"llm": {"min_score": 5}, "topic": "t"}, "2026-10-05",
                    client=object(), fetch=boom,
                    card_fn=lambda c, m, p, t, r: {"card": "x"})
    assert out[0]["card"] == ""

def test_run_defaults_min_score_when_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(cards.common, "ROOT", str(tmp_path))
    cards.common.dump_json(str(tmp_path / "data" / "scored" / "2026-10-05.json"),
                           [{"full_name": "a/b", "url": "u", "language": "Py", "stars": 1,
                             "status": "new", "score": 4, "one_liner": "x"},
                            {"full_name": "c/d", "url": "u", "language": "Py", "stars": 1,
                             "status": "new", "score": 6, "one_liner": "y"}])
    monkeypatch.setattr(cards, "load_prompts", lambda p: PROMPTS)
    out = cards.run({"topic": "t"}, "2026-10-05",
                    client=object(), fetch=lambda fn: "r",
                    card_fn=lambda c, m, p, t, r: {"card": "x"})
    assert [r["full_name"] for r in out] == ["c/d"]

def test_run_missing_scored_yields_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(cards.common, "ROOT", str(tmp_path))
    calls = []
    monkeypatch.setattr(cards, "load_prompts", lambda p: PROMPTS)
    out = cards.run({"llm": {"min_score": 5}, "topic": "t"}, "2026-10-05",
                    client=object(), fetch=lambda fn: calls.append(fn) or "r",
                    card_fn=lambda c, m, p, t, r: {"card": "x"})
    assert out == [] and calls == []

def test_build_code_card_parses_json():
    client = _fake_client('{"card": "## 是什么\\nhello"}')
    out = agent.build_code_card(client, "m", PROMPTS, "topic", "README")
    assert out == {"card": "## 是什么\nhello"}
