import json, os
from datetime import datetime
from zoneinfo import ZoneInfo
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def topic_brief(cfg: dict) -> str:
    """人类可读的课题说明,喂给 LLM;优先 topic_desc,其次 title,最后 topic(slug)。"""
    for key in ("topic_desc", "title", "topic"):
        val = (cfg.get(key) or "").strip()
        if val:
            return val
    return ""

def data_dir(*parts: str) -> str:
    d = os.path.join(ROOT, "data", *parts[:-1])
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, parts[-1])

def read_registry() -> dict:
    path = data_dir("registry.json")
    if not os.path.exists(path):
        return {"topic": "", "repos": {}}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def write_registry(reg: dict) -> None:
    dump_json(data_dir("registry.json"), reg)

def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def dump_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def today() -> str:
    tz = os.environ.get("TZ", "Asia/Shanghai")
    return datetime.now(ZoneInfo(tz)).strftime("%Y-%m-%d")
