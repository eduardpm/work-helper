from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class RawItem:
    source: str          # slack | jira | gitlab | notes
    id: str              # stable across re-fetches, e.g. "slack-C0123-1725000000.000100"
    url: str             # permalink, may be empty for notes
    author: str
    timestamp: str       # ISO 8601
    title: str
    content: str
    extra: dict = field(default_factory=dict)


def _safe_filename(item_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", item_id)


def save_raw(vault: Path, item: RawItem) -> Path:
    """Write one raw item as JSON under raw/<day>/. Overwrites the same ID,
    so an updated Jira issue replaces its old snapshot instead of duplicating it."""
    day = (item.timestamp or utc_now_iso())[:10]
    folder = vault / "raw" / day
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (_safe_filename(item.id) + ".json")
    path.write_text(json.dumps(asdict(item), indent=2, ensure_ascii=False))
    return path


def load_raw(path: Path) -> RawItem:
    return RawItem(**json.loads(path.read_text()))


def iter_raw_files(vault: Path):
    root = vault / "raw"
    if not root.exists():
        return
    for path in sorted(root.glob("*/*.json")):
        yield path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
