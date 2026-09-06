from __future__ import annotations

import re
from pathlib import Path

import yaml

from ..collectors.base import RawItem, iso
from .categorize import ItemIndex, title_for

STATE_HEADING = "## State"
TODO_HEADING = "## TODO"
LOG_HEADING = "## Log"

NO_STATE = "(no state summary yet)"
DUE_MARK = re.compile(r"\s*📅\s*(\d{4}-\d{2}-\d{2})")  # Obsidian Tasks due-date format


def epic_path(vault: Path, slug: str) -> Path:
    return vault / "epics" / f"{slug}.md"


def parse_epic(text: str) -> tuple[dict, str, str, list[str], str]:
    """Split an epic note into (frontmatter, title, state, todo lines, log body).
    Assumes the fixed structure this module writes."""
    meta = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            meta = yaml.safe_load(parts[1]) or {}
            body = parts[2]

    title = ""
    for line in body.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break

    state = ""
    if STATE_HEADING in body:
        state = body.split(STATE_HEADING, 1)[1].split(TODO_HEADING, 1)[0].strip()
        if state == NO_STATE:
            state = ""

    todos: list[str] = []
    log_body = ""
    if TODO_HEADING in body:
        after_todo = body.split(TODO_HEADING, 1)[1]
        todo_section = after_todo.split(LOG_HEADING, 1)[0]
        # one entry per checkbox line; indented lines below it (the description) stay attached
        for line in todo_section.splitlines():
            stripped = line.strip()
            if stripped.startswith("- ["):
                todos.append(stripped)
            elif todos and stripped and line[:1] in (" ", "\t"):
                todos[-1] += "\n    " + stripped
    if LOG_HEADING in body:
        log_body = body.split(LOG_HEADING, 1)[1].strip("\n")

    return meta, title, state, todos, log_body


def render_epic(
    meta: dict, title: str, state: str, todos: list[str], log_body: str
) -> str:
    frontmatter = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip()
    todo_block = "\n".join(todos) if todos else "- [ ] (nothing tracked yet)"
    return (
        f"---\n{frontmatter}\n---\n\n# {title}\n\n{STATE_HEADING}\n\n{state or NO_STATE}\n\n{TODO_HEADING}\n\n{todo_block}\n\n{LOG_HEADING}\n\n{log_body}\n".rstrip()
        + "\n"
    )


def _merge_list(existing, new_items) -> list[str]:
    """First spelling of each entry wins, order preserved."""
    seen = {}
    for x in list(existing or []) + list(new_items):
        seen.setdefault(str(x).lower(), str(x))
    return list(seen.values())


def update_epic(vault: Path, item: RawItem, idx: ItemIndex, slug: str) -> Path:
    path = epic_path(vault, slug)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        meta, title, state, todos, log_body = parse_epic(path.read_text())
        todos = [t for t in todos if "(nothing tracked yet)" not in t]
    else:
        meta, title, state, todos, log_body = {}, idx.titles.get(slug) or title_for(slug), "", [], ""

    meta["tags"] = _merge_list(meta.get("tags"), idx.tags)
    meta["people"] = _merge_list(meta.get("people"), idx.people)
    meta["refs"] = _merge_list(meta.get("refs"), idx.refs)
    meta["updated"] = iso()[:10]

    # TODOs belong to the user (dashboard, Obsidian); the indexer only preserves them.

    day = item.timestamp[:10]
    link = f" — [{item.source} link]({item.url})" if item.url else ""
    event = f"**{idx.event}** — " if idx.event else ""
    entry = f"### {day} {item.source} — {item.title}{link}\n{event}{idx.summary}"
    log_body = entry + ("\n\n" + log_body if log_body else "")

    path.write_text(render_epic(meta, title or title_for(slug), state, todos, log_body))
    return path


def update_daily(vault: Path, item: RawItem, idx: ItemIndex) -> Path:
    day = item.timestamp[:10] or iso()[:10]
    path = vault / "daily" / f"{day}.md"
    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.exists():
        path.write_text(f"# {day}\n\n")

    links = " ".join(f"[[{e}]]" for e in idx.epics)
    line = f"- **{item.source}** {links} — {idx.summary}\n"
    with path.open("a") as f:
        f.write(line)
    return path
