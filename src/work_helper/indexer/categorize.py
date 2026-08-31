from __future__ import annotations

import re
from pathlib import Path
from typing import List

from pydantic import BaseModel, field_validator

from ..collectors.base import RawItem
from .llm import LLM

SYSTEM_PROMPT = """You index one work item into a personal knowledge vault.
The vault has one Markdown note per topic (a "topic" is one thread of work,
e.g. one ticket, one feature, one recurring theme).

Respond with ONE JSON object and nothing else:
{
  "topic": "kebab-case-slug",
  "topic_title": "Human readable topic title",
  "tags": ["lowercase", "keywords"],
  "people": ["names mentioned or involved"],
  "summary": "1-3 short sentences: what happened in this item",
  "todos": ["open action items stated or clearly implied, empty list if none"],
  "refs": ["ticket keys like PROJ-123 or MR numbers like !45 mentioned in the item"]
}

Rules:
- If the item belongs to one of the EXISTING TOPICS, reuse that exact slug.
- Ticket keys and MR numbers are the strongest signal that items share a topic.
- Only create a new topic when nothing existing fits.
- todos: only real open work, not things already done.
- Keep tags generic and reusable (e.g. "renovate", "ci", "deployment").
"""


class ItemIndex(BaseModel):
    """The model's JSON, coerced into shape. Everything here arrives from an
    LLM, so every field is cleaned rather than trusted."""

    topic: str = "misc"
    topic_title: str = "Untitled"
    summary: str = ""
    tags: List[str] = []
    people: List[str] = []
    todos: List[str] = []
    refs: List[str] = []

    @field_validator("topic", mode="before")
    @classmethod
    def _slug(cls, v) -> str:
        return normalize_slug(str(v or "misc"))

    @field_validator("summary", mode="before")
    @classmethod
    def _strip(cls, v) -> str:
        return str(v or "").strip()

    @field_validator("tags", "people", "todos", "refs", mode="before")
    @classmethod
    def _drop_blanks(cls, v) -> List[str]:
        return [str(x).strip() for x in (v or []) if str(x).strip()]

    @field_validator("tags")
    @classmethod
    def _lower(cls, v: List[str]) -> List[str]:
        return [t.lower() for t in v]


def normalize_slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "misc"


def list_topics(vault: Path) -> List[str]:
    folder = vault / "topics"
    if not folder.exists():
        return []
    return sorted(p.stem for p in folder.glob("*.md"))


def categorize(llm: LLM, item: RawItem, existing_topics: List[str]) -> ItemIndex:
    topics_block = "\n".join(f"- {t}" for t in existing_topics) or "(none yet)"
    user = (
        "EXISTING TOPICS:\n{}\n\n"
        "ITEM (source: {}, author: {}, date: {}, title: {}):\n{}"
    ).format(
        topics_block,
        item.source,
        item.author,
        item.timestamp[:10],
        item.title,
        item.content[:6000],
    )

    data = llm.json_chat(SYSTEM_PROMPT, user)
    if not data.get("topic_title"):
        data["topic_title"] = item.title or "Untitled"
    return ItemIndex(**data)
