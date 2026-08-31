from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field


class RawItem(BaseModel):
    source: str  # slack | jira | gitlab | notes
    id: str  # stable across re-fetches, e.g. "slack-C0123-1725000000.000100"
    url: str  # permalink, may be empty for notes
    author: str
    timestamp: str  # ISO 8601
    title: str
    content: str
    extra: dict = Field(default_factory=dict)


def _safe_filename(item_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", item_id)


def save_raw(vault: Path, item: RawItem) -> Path:
    """Write one raw item as JSON under raw/<day>/. Overwrites the same ID,
    so an updated Jira issue replaces its old snapshot instead of duplicating it."""
    day = (item.timestamp or iso())[:10]
    folder = vault / "raw" / day
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (_safe_filename(item.id) + ".json")
    path.write_text(item.model_dump_json(indent=2))
    return path


def load_raw(path: Path) -> RawItem:
    return RawItem.model_validate_json(path.read_text())


def iter_raw_files(vault: Path) -> list[Path]:
    return sorted((vault / "raw").glob("*/*.json"))


def iso(dt: datetime = None) -> str:
    """The one timestamp format the vault uses. Defaults to now, UTC."""
    return (dt or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
