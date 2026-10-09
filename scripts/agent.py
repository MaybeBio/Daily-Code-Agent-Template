import json, os, time
import yaml
from openai import OpenAI

DEFAULT_MODEL = "deepseek-chat"

def load_prompts(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def make_client() -> OpenAI:
    return OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.environ["LLM_API_KEY"])

def model_name() -> str:
    return os.environ.get("LLM_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL

def score_repo(client, model, prompts, topic_desc, readme) -> dict:
    p = prompts["score"]
    msgs = [{"role": "system", "content": p["system"]},
            {"role": "user", "content": p["user"].format(topic=topic_desc, readme=readme[:12000])}]
    last = None
    for attempt in range(4):
        try:
            r = client.chat.completions.create(model=model, messages=msgs, temperature=0.0,
                                                response_format={"type": "json_object"})
            obj = json.loads(r.choices[0].message.content)
            return {"score": int(obj["score"]), "one_liner": str(obj.get("one_liner", ""))}
        except Exception as e:      # 网络/限流/解析
            last = e
            if attempt < 3:
                time.sleep(2 ** attempt)
    raise last

def build_code_card(client, model, prompts, topic_desc, readme) -> dict:
    p = prompts["code_card"]
    msgs = [{"role": "system", "content": p["system"]},
            {"role": "user", "content": p["user"].format(topic=topic_desc, readme=readme)}]
    last = None
    for attempt in range(4):
        try:
            r = client.chat.completions.create(model=model, messages=msgs, temperature=0.0,
                                                response_format={"type": "json_object"})
            obj = json.loads(r.choices[0].message.content)
            return {"card": str(obj.get("card", ""))}
        except Exception as e:      # 网络/限流/解析
            last = e
            if attempt < 3:
                time.sleep(2 ** attempt)
    raise last
