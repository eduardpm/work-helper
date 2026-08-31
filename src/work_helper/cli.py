from __future__ import annotations

import argparse
import sys

from .config import load_config
from .state import State

SOURCES = ("slack", "jira", "gitlab", "notes")


def cmd_collect(cfg, args) -> int:
    from .collectors import gitlab, jira, notes, slack

    modules = {"slack": slack, "jira": jira, "gitlab": gitlab, "notes": notes}
    wanted = SOURCES if args.source == "all" else (args.source,)

    state = State(cfg.vault)
    total = 0
    for name in wanted:
        try:
            total += modules[name].collect(cfg, state)
        except SystemExit as exc:
            print(f"{name}: {exc}")
        except Exception as exc:
            print(f"{name}: FAILED: {exc}")
    state.save()
    print(f"collected {total} items total")
    return 0


def cmd_index(cfg, args) -> int:
    from .indexer import run_index

    run_index(cfg)
    return 0


def cmd_ask(cfg, args) -> int:
    from .answer.answer import ask

    print()
    print(ask(cfg, args.question))
    return 0


def cmd_search(cfg, args) -> int:
    from .answer.search import search

    matches = search(cfg.vault, args.term)
    for line in matches:
        print(line)
    if not matches:
        print("no matches")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="work-helper",
        description="Collect work data, categorize it locally, store it in an Obsidian vault.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_collect = sub.add_parser("collect", help="fetch new items into vault/raw/")
    p_collect.add_argument("source", nargs="?", default="all", choices=SOURCES + ("all",))
    p_collect.set_defaults(func=cmd_collect)

    p_index = sub.add_parser("index", help="categorize raw items with LM Studio")
    p_index.set_defaults(func=cmd_index)

    p_ask = sub.add_parser("ask", help="answer a question from the vault")
    p_ask.add_argument("question")
    p_ask.set_defaults(func=cmd_ask)

    p_search = sub.add_parser("search", help="ripgrep the vault, no LLM")
    p_search.add_argument("term")
    p_search.set_defaults(func=cmd_search)

    args = parser.parse_args(argv)
    try:
        cfg = load_config()
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    cfg.vault.mkdir(parents=True, exist_ok=True)
    return args.func(cfg, args)


if __name__ == "__main__":
    sys.exit(main())
