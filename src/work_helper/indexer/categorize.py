from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, field_validator, model_validator

from ..collectors.base import RawItem
from .llm import LLM

EVENT_KINDS = ("decision", "blocker", "discovery", "question", "progress")

SYSTEM_PROMPT = """You index one work item into a personal knowledge base
organized as EPICS: big threads of work (a feature, an initiative, a concept
under discussion, a recurring theme), like Jira epics. One item can belong to
more than one epic.

Respond with ONE JSON object and nothing else:
{{
  "epics": [{{"slug": "kebab-case-slug", "title": "Short human title of the epic"}}],
  "event": "",
  "tags": ["lowercase", "keywords"],
  "people": ["names mentioned or involved"],
  "summary": "everything this item tells us: every fact, decision, number, date, name, reason and open question, in as many sentences as needed",
  "refs": ["ticket keys like PROJ-123 or MR numbers like !45 mentioned in the item"]
}}

Rules:
- epics: 1 to 3. Reuse an EXISTING EPICS slug whenever the item belongs there
  (title may be "" then). Only invent a new epic when nothing existing fits.
- A slug or title names the TOPIC of the work, never a ticket key or MR number:
  PROJ-123 is a ref, "checkout-redesign" is an epic.
- Ticket keys and MR numbers are the strongest signal that items share an epic.
- event: what kind of development this item is, one of {kinds} —
  or "" if none clearly fits.
- summary: complete rather than short. The item text is not read again later;
  this summary is all the knowledge base keeps of it.
- Keep tags generic and reusable (e.g. "renovate", "ci", "deployment").
""".format(kinds=", ".join(f'"{k}"' for k in EVENT_KINDS))

# Shared with the Codex chat rules in dashboard.py, so both writers agree.
STATE_FORMAT = """The State is a Markdown document with exactly these "###" headings, in this order:

### Summary
What this epic is about and why it matters. Explain the concepts, terms and
mechanics involved so a reader new to the topic understands it fully. Use
paragraphs and bullets; put key terms in **bold**.

### Where it stands
Bullets, newest first, each starting with its date: what was decided, built,
merged or agreed, with names and ticket or MR keys.

### Decisions
Bullets: each decision, who made it, and the reasoning behind it.

### Blockers and questions
Bullets: open blockers, disagreements and unanswered questions, each with who is
waiting on whom. Write "- none known" if there are none.

Be thorough: length is not a concern, completeness is. Keep every fact, number,
name, date, definition and rationale the log contains; never fold two distinct
facts into one sentence. No URLs or Markdown links: cite items by ticket key, MR
number or date. One blank line between blocks."""

STATE_PROMPT = f"""You maintain the "State" section of an epic note in a personal
work knowledge base. The reader wants to learn everything about this epic
without reading the messages, tickets and PRs behind it.

{STATE_FORMAT}

Prefer newer log entries when they conflict. Do not invent anything. Respond
with the State text only."""

LINK = re.compile(r"\[([^\]]+)\]\(https?://[^)\s]+\)")


class ItemIndex(BaseModel):
    """The model's JSON, coerced into shape. Everything here arrives from an
    LLM, so every field is cleaned rather than trusted."""

    epics: list[str] = ["misc"]
    titles: dict[str, str] = {}  # slug -> title, for epics the model proposed
    event: str = ""
    summary: str = ""
    tags: list[str] = []
    people: list[str] = []
    todos: list[str] = []
    refs: list[str] = []

    @model_validator(mode="before")
    @classmethod
    def _split_epics(cls, data):
        """epics may arrive as slugs or as {"slug", "title"} objects."""
        if not isinstance(data, dict):
            return data
        raw = data.get("epics") or []
        if isinstance(raw, (str, dict)):
            raw = [raw]
        titles, slugs = dict(data.get("titles") or {}), []
        for e in raw:
            if isinstance(e, dict):
                slug = normalize_slug(str(e.get("slug") or ""))
                if str(e.get("title") or "").strip():
                    titles[slug] = str(e["title"]).strip()
                slugs.append(slug)
            else:
                slugs.append(str(e))
        return {**data, "epics": slugs, "titles": titles}

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
        title, state or "(empty)", log_body[:40000]  # needs a 16k+ context in LM Studio
    )
    return LINK.sub(r"\1", llm.chat(STATE_PROMPT, user)).strip()
