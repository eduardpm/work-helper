from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import yaml

from ..collectors.base import RawItem, iso
from .categorize import ItemIndex

TODO_HEADING = "## TODO"
LOG_HEADING = "## Log"


def parse_topic(text: str) -> Tuple[dict, str, List[str], str]:
    """Split a topic note into (frontmatter, title, todo lines, log body).
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

    todos: List[str] = []
    log_body = ""
    if TODO_HEADING in body:
        after_todo = body.split(TODO_HEADING, 1)[1]
        todo_section = after_todo.split(LOG_HEADING, 1)[0]
        todos = [
            line.strip()
            for line in todo_section.splitlines()
            if line.strip().startswith("- [")
        ]
    if LOG_HEADING in body:
        log_body = body.split(LOG_HEADING, 1)[1].strip("\n")

    return meta, title, todos, log_body


def render_topic(meta: dict, title: str, todos: List[str], log_body: str) -> str:
    frontmatter = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip()
    todo_block = "\n".join(todos) if todos else "- [ ] (nothing tracked yet)"
    return "---\n{}\n---\n\n# {}\n\n{}\n\n{}\n\n{}\n\n{}\n".format(
        frontmatter, title, TODO_HEADING, todo_block, LOG_HEADING, log_body
    ).rstrip() + "\n"


def _merge_list(existing, new_items) -> List[str]:
    """First spelling of each entry wins, order preserved."""
    seen = {}
    for x in list(existing or []) + list(new_items):
        seen.setdefault(str(x).lower(), str(x))
    return list(seen.values())


def _todo_text(line: str) -> str:
    return line.split("]", 1)[-1].strip().lower()


def update_topic(vault: Path, item: RawItem, idx: ItemIndex) -> Path:
    path = vault / "topics" / f"{idx.topic}.md"
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        meta, title, todos, log_body = parse_topic(path.read_text())
        todos = [t for t in todos if "(nothing tracked yet)" not in t]
    else:
        meta, title, todos, log_body = {}, idx.topic_title, [], ""

    meta["tags"] = _merge_list(meta.get("tags"), idx.tags)
    meta["people"] = _merge_list(meta.get("people"), idx.people)
    meta["refs"] = _merge_list(meta.get("refs"), idx.refs)
    meta["updated"] = iso()[:10]

    existing_texts = {_todo_text(t) for t in todos}
    for todo in idx.todos:
        if todo.lower() not in existing_texts:
            todos.append(f"- [ ] {todo}")

    day = item.timestamp[:10]
    link = f" — [{item.source} link]({item.url})" if item.url else ""
    entry = "### {} {} — {}{}\n{}".format(day, item.source, item.title, link, idx.summary)
    log_body = entry + ("\n\n" + log_body if log_body else "")

    path.write_text(render_topic(meta, title or idx.topic_title, todos, log_body))
    return path


def update_daily(vault: Path, item: RawItem, idx: ItemIndex) -> Path:
    day = item.timestamp[:10] or iso()[:10]
    path = vault / "daily" / f"{day}.md"
    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.exists():
        path.write_text(f"# {day}\n\n")

    line = "- **{}** [[{}]] — {}\n".format(item.source, idx.topic, idx.summary)
    with path.open("a") as f:
        f.write(line)
    return path
