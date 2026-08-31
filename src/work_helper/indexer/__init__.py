from __future__ import annotations

from ..collectors.base import iter_raw_files, load_raw
from ..config import Config
from ..state import State
from .categorize import categorize, list_topics
from .llm import LLM
from .render import update_daily, update_topic


def run_index(cfg: Config) -> int:
    state = State(cfg.vault)
    llm = LLM(cfg.lmstudio)
    topics = list_topics(cfg.vault)

    count = 0
    for path in iter_raw_files(cfg.vault):
        item = load_raw(path)
        if item.id in state.processed:
            continue
        try:
            idx = categorize(llm, item, topics)
        except Exception as exc:
            print(f"  SKIP {item.id}: {exc}")
            continue
        update_topic(cfg.vault, item, idx)
        update_daily(cfg.vault, item, idx)
        if idx.topic not in topics:
            topics.append(idx.topic)
        state.processed.add(item.id)
        state.save()  # save per item, so a crash loses nothing
        count += 1
        print(f"  {item.id} -> topics/{idx.topic}.md")

    print(f"index: processed {count} items")
    return count
