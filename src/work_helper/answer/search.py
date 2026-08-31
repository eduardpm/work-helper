from __future__ import annotations

import os
import shutil
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Sequence


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


MAX_WORKERS = 8


def search_many(vault: Path, terms: Sequence[str]) -> List[List[str]]:
    """Run one grep per term, concurrently. Each grep blocks on a child
    process, so threads overlap them."""
    if len(terms) < 2:
        return [search(vault, t) for t in terms]
    workers = min(len(terms), MAX_WORKERS, (os.cpu_count() or 4) * 2)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda t: search(vault, t), terms))


def top_files(vault: Path, terms: List[str], limit: int = 5) -> List[Path]:
    """Files with the most matches across all terms. Topic notes rank
    before raw JSON because they are already summarized."""
    counts: Counter = Counter()
    for lines in search_many(vault, terms):
        for line in lines:
            path = line.split(":", 1)[0]
            if "/raw/" in path or "/.state" in path:
                continue
            counts[path] += 1
    # Path breaks ties so ranking does not depend on grep timing.
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [Path(p) for p, _ in ranked[:limit]]
