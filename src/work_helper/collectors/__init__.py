
SOURCES = ("slack", "jira", "gitlab", "notes")


def collect_sources(cfg, wanted) -> dict:
    """Run the given collectors. Returns {source: new_item_count | error string}
    and records a sync time for each source that succeeded."""
    from ..state import State
    from . import gitlab, jira, notes, slack
    from .base import iso

    modules = {"slack": slack, "jira": jira, "gitlab": gitlab, "notes": notes}
    state = State(cfg.vault)
    results = {}
    for name in wanted:
        try:
            results[name] = modules[name].collect(cfg, state)
            state.synced[name] = iso()
        except SystemExit as exc:  # missing token
            results[name] = str(exc)
        except Exception as exc:  # noqa: BLE001 - one broken source must not stop the others
            results[name] = f"FAILED: {exc}"
    state.save()
    return results
