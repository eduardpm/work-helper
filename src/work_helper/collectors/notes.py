from __future__ import annotations

import re
from datetime import datetime, timezone

from ..config import Config
from ..state import State
from .base import RawItem, iso, save_raw


def collect(cfg: Config, state: State) -> int:
    inbox = cfg.notes_inbox
    inbox.mkdir(parents=True, exist_ok=True)
    archive = inbox / "archive"

    count = 0
    for path in sorted(inbox.iterdir()):
        if path.suffix.lower() not in (".md", ".txt") or not path.is_file():
            continue
        mtime = path.stat().st_mtime
        timestamp = iso(datetime.fromtimestamp(mtime, tz=timezone.utc))
        slug = re.sub(r"[^A-Za-z0-9_-]", "-", path.stem)
        item = RawItem(
            source="notes",
            id=f"notes-{slug}-{int(mtime)}",
            url="",
            author="me",
            timestamp=timestamp,
            title=path.stem,
            content=path.read_text(),
        )
        save_raw(cfg.vault, item)
        archive.mkdir(exist_ok=True)
        path.rename(archive / path.name)
        count += 1

    print(f"notes: saved {count} items")
    return count
