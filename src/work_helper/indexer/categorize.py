from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, field_validator

from ..collectors.base import RawItem
from .llm import LLM

EVENT_KINDS = ("decision", "blocker", "discovery", "question", "progress")

SYSTEM_PROMPT = """You index one work item into a personal knowledge base
organized as EPICS: big threads of work (a feature, an initiative, a concept
under discussion, a recurring theme), like Jira epics. One item can belong to
more than one epic.

Respond with ONE JSON object and nothing else:
{{
  "epics": ["kebab-case-slug"],
  "event": "",
  "tags": ["lowercase", "keywords"],
  "people": ["names mentioned or involved"],
  "summary": "1-3 short sentences: what happened in this item, with names",
  "refs": ["ticket keys like PROJ-123 or MR numbers like !45 mentioned in the item"]
}}

Rules:
- epics: 1 to 3 slugs. Reuse an EXISTING EPICS slug whenever the item belongs
  there. Only invent a new slug when nothing existing fits.
- Ticket keys and MR numbers are the strongest signal that items share an epic.
- event: what kind of development this item is, one of {kinds} —
  or "" if none clearly fits.
- Keep tags generic and reusable (e.g. "renovate", "ci", "deployment").
""".format(kinds=", ".join(f'"{k}"' for k in EVENT_KINDS))

STATE_PROMPT = """You maintain the "State" section of an epic note in a personal
work knowledge base. The reader wants to catch up on this epic without reading
every message, ticket, and PR behind it.

Write Markdown with exactly these three headings, in this order:

### Summary
2-4 sentences: what this epic is about, in plain words, and why it matters.

### Where it stands
Bullet list, newest developments first: what was decided, built, merged or
agreed, with names and ticket or MR keys when the log has them.

### Blockers and questions
Bullet list of open blockers, disagreements or unanswered questions, each with
who is waiting on whom. Write "- none known" if there are none.

Rules: use "###" headings only, one blank line between blocks, short bullets,
prefer newer log entries when they conflict, do not repeat the log entry by
entry, do not invent anything. Respond with the State text only."""


class ItemIndex(BaseModel):
    """The model's JSON, coerced into shape. Everything here arrives from an
    LLM, so every field is cleaned rather than trusted."""

    epics: list[str] = ["misc"]
    event: str = ""
    summary: str = ""
    tags: list[str] = []
    people: list[str] = []
    todos: list[str] = []
    refs: list[str] = []

    @field_validator("epics", mode="before")
    @classmethod
    def _slugs(cls, v) -> list[str]:
        if isinstance(v, str):
            v = [v]
        slugs = []
        for x in v or []:
            slug = normalize_slug(str(x))
            if slug not in slugs:
                slugs.append(slug)
        return slugs[:3] or ["misc"]

    @field_validator("event", mode="before")
    @classmethod
    def _event(cls, v) -> str:
        v = str(v or "").strip().lower()
        return v if v in EVENT_KINDS else ""

    @field_validator("summary", mode="before")
    @classmethod
    def _strip(cls, v) -> str:
        return str(v or "").strip()

    @field_validator("tags", "people", "todos", "refs", mode="before")
    @classmethod
    def _drop_blanks(cls, v) -> list[str]:
        return [str(x).strip() for x in (v or []) if str(x).strip()]

    @field_validator("tags")
    @classmethod
    def _lower(cls, v: list[str]) -> list[str]:
        return [t.lower() for t in v]


def normalize_slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "misc"


def title_for(slug: str) -> str:
    return slug.replace("-", " ").capitalize()


def list_epics(vault: Path) -> list[str]:
    folder = vault / "epics"
    if not folder.exists():
        return []
    return sorted(p.stem for p in folder.glob("*.md"))


def categorize(llm: LLM, item: RawItem, existing_epics: list[str]) -> ItemIndex:
    epics_block = "\n".join(f"- {e}" for e in existing_epics) or "(none yet)"
    user = (
        f"EXISTING EPICS:\n{epics_block}\n\n"
        f"ITEM (source: {item.source}, author: {item.author}, date: {item.timestamp[:10]}, title: {item.title}):\n{item.content[:6000]}"
    )
    return ItemIndex(**llm.json_chat(SYSTEM_PROMPT, user))


def summarize_state(llm: LLM, title: str, state: str, log_body: str) -> str:
    user = "EPIC: {}\n\nCURRENT STATE:\n{}\n\nLOG (newest first):\n{}".format(
        title, state or "(empty)", log_body[:8000]
    )
    return llm.chat(STATE_PROMPT, user).strip()
