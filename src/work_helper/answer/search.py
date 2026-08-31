from __future__ import annotations

import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import List


def _grep_cmd() -> List[str]:
    if shutil.which("rg"):
        return ["rg", "-i", "--no-heading", "--line-number"]
    return ["grep", "-r", "-i", "-n"]


def search(vault: Path, term: str, folder: str = "") -> List[str]:
    """Return matching lines as 'path:line:text'."""
    root = vault / folder if folder else vault
    cmd = _grep_cmd() + [term, str(root)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode not in (0, 1):  # 1 = no matches
        raise RuntimeError(result.stderr.strip())
    return [line for line in result.stdout.splitlines() if line.strip()]


def top_files(vault: Path, terms: List[str], limit: int = 5) -> List[Path]:
    """Files with the most matches across all terms. Topic notes rank
    before raw JSON because they are already summarized."""
    counts = Counter()
    for term in terms:
        for line in search(vault, term):
            path = line.split(":", 1)[0]
            if "/raw/" in path or "/.state" in path:
                continue
            counts[path] += 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    return [Path(p) for p, _ in ranked[:limit]]
