from __future__ import annotations

import json
from pathlib import Path


class State:
    """Cursors and processed-item IDs, stored as JSON inside the vault."""

    def __init__(self, vault: Path):
        self.path = vault / ".state.json"
        data = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.cursors: dict = data.get("cursors", {})
        self.processed: set = set(data.get("processed", []))
        self.synced: dict = data.get("synced", {})  # source -> ISO time of last successful collect

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(
            {"cursors": self.cursors, "processed": sorted(self.processed), "synced": self.synced}, indent=2
        ))
        tmp.replace(self.path)
