from __future__ import annotations

import os
import shutil
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Sequence, Tuple


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


TERM_WEIGHT = 3
RELATED_WEIGHT = 1
MAX_WORKERS = 8


def search_many(vault: Path, terms: Sequence[str]) -> List[List[str]]:
    """Run one grep per term, concurrently. Each grep spends nearly all its
    time blocked on a child process, so threads overlap them even though the
    work stays in one interpreter. Results come back in the order the terms
    were given, not the order the greps finished."""
    if not terms:
        return []
    if len(terms) == 1:
        return [search(vault, terms[0])]

    workers = min(len(terms), MAX_WORKERS, (os.cpu_count() or 4) * 2)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda t: search(vault, t), terms))


def top_files(
    vault: Path,
    terms: List[str],
    related: Sequence[str] = (),
    limit: int = 5,
) -> List[Path]:
    """Files with the most matches, scored across both term groups. Terms
    taken straight from the question weigh more than the broader terms the
    model guessed, so expansion widens the net without drowning out an exact
    hit. Topic notes rank before raw JSON because they are already
    summarized."""
    weighted: List[Tuple[str, int]] = [(t, TERM_WEIGHT) for t in terms]
    weighted += [(t, RELATED_WEIGHT) for t in related]

    results = search_many(vault, [t for t, _ in weighted])

    scores: Counter = Counter()
    for (_, weight), lines in zip(weighted, results):
        for line in lines:
            path = line.split(":", 1)[0]
            if "/raw/" in path or "/.state" in path:
                continue
            scores[path] += weight

    # Path breaks ties so the ranking does not depend on grep timing.
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return [Path(p) for p, _ in ranked[:limit]]
