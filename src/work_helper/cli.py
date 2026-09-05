from __future__ import annotations

import argparse
import sys

from .collectors import SOURCES, collect_sources
from .config import load_config


def cmd_collect(cfg, args) -> int:
    wanted = SOURCES if args.source == "all" else (args.source,)
    results = collect_sources(cfg, wanted)
    for name, result in results.items():
        if not isinstance(result, int):
            print(f"{name}: {result}")
    print(f"collected {sum(r for r in results.values() if isinstance(r, int))} items total")
    return 0


def cmd_index(cfg, args) -> int:
    from .indexer import run_index

    run_index(cfg)
    return 0


def cmd_sync(cfg, args) -> int:
    args.source = "all"
    cmd_collect(cfg, args)
    return cmd_index(cfg, args)


def cmd_dashboard(cfg, args) -> int:
    from .dashboard import serve

    vault = cfg.vault if cfg else None
    if args.demo:
        from .demo import seed_demo

        vault = seed_demo()
        print(f"demo vault: {vault}", flush=True)
    serve(vault, args.port, open_browser=not args.no_open, cfg=cfg)
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

    p_sync = sub.add_parser("sync", help="collect all sources, then index")
    p_sync.set_defaults(func=cmd_sync)

    p_dash = sub.add_parser("dashboard", help="open the local dashboard app in the browser")
    p_dash.add_argument("--port", type=int, default=8787)
    p_dash.add_argument("--no-open", action="store_true", help="do not open the browser")
    p_dash.add_argument("--demo", action="store_true", help="serve a throwaway vault with seed data")
    p_dash.set_defaults(func=cmd_dashboard)

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
        if not getattr(args, "demo", False):
            print(exc, file=sys.stderr)
            return 1
        cfg = None  # --demo needs no config
    if cfg:
        cfg.vault.mkdir(parents=True, exist_ok=True)
    return args.func(cfg, args)


if __name__ == "__main__":
    sys.exit(main())
