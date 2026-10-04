import re

_TS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| (.*)$")
_EMOJI_KIND = {"\U0001F680": "push", "⭐": "star", "\U0001F500": "pr",
               "\U0001F41B": "issue", "\U0001F4AC": "issue", "\U0001F195": "branch"}
_KIND_HINTS = [("starred", "star"), ("pushed to", "push"), ("forked", "fork"),
               ("opened PR", "pr"), ("reopened PR", "pr"), ("closed PR", "pr"),
               ("created branch", "branch"), ("opened issue", "issue"),
               ("created issue", "issue")]
_ANCHOR = re.compile(
    r"(?:starred|pushed to|forked|\bin\b|\bat\b)\s+"
    r"([A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*)")

def unwrap_records(text: str) -> list[str]:
    out, buf = [], None
    for raw in text.splitlines():
        if _TS.match(raw):
            if buf:
                out.append(buf)
            buf = raw.rstrip()
        elif buf is not None:
            buf += " " + raw.strip()
    if buf:
        out.append(buf)
    return out

def _kind(emoji_and_text: str) -> str:
    for emoji, kind in _EMOJI_KIND.items():
        if emoji in emoji_and_text:
            return kind
    for hint, kind in _KIND_HINTS:
        if hint in emoji_and_text:
            return kind
    return "other"

def parse_event(record: str) -> dict | None:
    m = _TS.match(record)
    if not m:
        return None
    ts, body = m.group(1), m.group(2)
    kind = _kind(body)
    # 去掉 emoji 与首个人名/actor token
    stripped = re.sub(r"^[^\w]+\s*", "", body)          # 去 emoji
    actor = stripped.split()[0] if stripped.split() else ""
    # 仓库：锚定事件动词/介词后第一个 owner/repo
    m2 = _ANCHOR.search(body)
    repo = m2.group(1) if m2 else None
    return {"ts": ts, "kind": kind, "actor": actor, "repo": repo, "text": body}

def extract_events(text: str) -> list[dict]:
    evs = []
    for rec in unwrap_records(text):
        ev = parse_event(rec)
        if ev and ev["repo"]:
            evs.append(ev)
    return evs

def repos_from_events(events: list[dict]) -> dict:
    out: dict = {}
    for e in events:
        r = out.setdefault(e["repo"], {"who": [], "kinds": []})
        if e["actor"] and e["actor"] not in r["who"]:
            r["who"].append(e["actor"])
        if e["kind"] not in r["kinds"]:
            r["kinds"].append(e["kind"])
    return out
