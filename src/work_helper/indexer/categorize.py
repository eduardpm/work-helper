from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

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


@dataclass
class ItemIndex:
    topic: str
    topic_title: str
    summary: str
    tags: List[str] = field(default_factory=list)
    people: List[str] = field(default_factory=list)
    todos: List[str] = field(default_factory=list)
    refs: List[str] = field(default_factory=list)


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

    def str_list(key: str) -> List[str]:
        value = data.get(key) or []
        return [str(v).strip() for v in value if str(v).strip()]

    return ItemIndex(
        topic=normalize_slug(str(data.get("topic", "misc"))),
        topic_title=str(data.get("topic_title") or item.title or "Untitled"),
        summary=str(data.get("summary", "")).strip(),
        tags=[t.lower() for t in str_list("tags")],
        people=str_list("people"),
        todos=str_list("todos"),
        refs=str_list("refs"),
    )
