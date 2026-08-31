from __future__ import annotations

from pathlib import Path

from ..collectors.base import iter_raw_files, load_raw
from ..config import Config
from ..state import State
from .categorize import categorize, list_epics, summarize_state
from .llm import LLM
from .render import epic_path, parse_epic, render_epic, update_daily, update_epic


def refresh_state(llm: LLM, vault: Path, slug: str) -> None:
    path = epic_path(vault, slug)
    meta, title, state, todos, log_body = parse_epic(path.read_text())
    new_state = summarize_state(llm, title, state, log_body)
    if new_state:
        path.write_text(render_epic(meta, title, new_state, todos, log_body))


def run_index(cfg: Config) -> int:
    state = State(cfg.vault)
    llm = LLM(cfg.lmstudio)
    epics = list_epics(cfg.vault)

    touched = set()
    count = 0
    for path in iter_raw_files(cfg.vault):
        item = load_raw(path)
        if item.id in state.processed:
            continue
        try:
            idx = categorize(llm, item, epics)
        except Exception as exc:
            print(f"  SKIP {item.id}: {exc}")
            continue
        for slug in idx.epics:
            update_epic(cfg.vault, item, idx, slug)
            if slug not in epics:
                epics.append(slug)
            touched.add(slug)
        update_daily(cfg.vault, item, idx)
        state.processed.add(item.id)
        state.save()  # save per item, so a crash loses nothing
        count += 1
        print(f"  {item.id} -> {', '.join(idx.epics)}")

    for slug in sorted(touched):
        try:
            refresh_state(llm, cfg.vault, slug)
            print(f"  state refreshed: epics/{slug}.md")
        except Exception as exc:
            print(f"  state SKIP {slug}: {exc}")

    print(f"index: processed {count} items, {len(touched)} epics touched")
    return count
