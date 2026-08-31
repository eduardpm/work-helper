from __future__ import annotations

import json
import re

from ..config import LMStudioConfig


def extract_json(text: str) -> dict:
    """Pull a JSON object out of a model response that may contain
    <think> blocks, code fences, or prose around the JSON."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"No JSON object in model response: {text[:200]!r}")
    return json.loads(text[start : end + 1])


class LLM:
    def __init__(self, cfg: LMStudioConfig):
        from openai import OpenAI

        self.client = OpenAI(base_url=cfg.base_url, api_key="lm-studio")
        self.model = cfg.model

    def chat(self, system: str, user: str, temperature: float = 0.2) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""

    def json_chat(self, system: str, user: str) -> dict:
        return extract_json(self.chat(system, user))
