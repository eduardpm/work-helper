from __future__ import annotations

import json
from pathlib import Path


class State:
    """Cursors and processed-item IDs, stored as JSON inside the vault."""

    def __init__(self, vault: Path):
        self.path = vault / ".state.json"
        if self.path.exists():
            self._data = json.loads(self.path.read_text())
        else:
            self._data = {"cursors": {}, "processed": []}
        self._processed = set(self._data.get("processed", []))

    def get_cursor(self, key: str, default: str = None) -> str:
        return self._data["cursors"].get(key, default)

    def set_cursor(self, key: str, value: str) -> None:
        self._data["cursors"][key] = value

    def is_processed(self, item_id: str) -> bool:
        return item_id in self._processed

    def mark_processed(self, item_id: str) -> None:
        self._processed.add(item_id)

    def save(self) -> None:
        self._data["processed"] = sorted(self._processed)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._data, indent=2))
        tmp.replace(self.path)
