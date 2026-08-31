from __future__ import annotations

import re
from datetime import datetime, timedelta

import httpx

from ..config import Config, require_env
from ..state import State
from .base import RawItem, save_raw

FIELDS = "summary,description,status,comment,updated,assignee,reporter"


def collect(cfg: Config, state: State) -> int:
    if not cfg.jira.base_url:
        print("jira: no base_url configured, skipping")
        return 0

    auth = (require_env("JIRA_EMAIL"), require_env("JIRA_TOKEN"))
    cursor = state.get_cursor("jira")
    if not cursor:
        cursor = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M")
    run_started = datetime.now().strftime("%Y-%m-%d %H:%M")

    jql = cfg.jira.jql.format(cursor=cursor)
    count = 0
    start_at = 0

    with httpx.Client(auth=auth, timeout=30) as client:
        while True:
            resp = client.get(
                f"{cfg.jira.base_url}/rest/api/2/search",
                params={
                    "jql": jql,
                    "fields": FIELDS,
                    "maxResults": 50,
                    "startAt": start_at,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            for issue in data.get("issues", []):
                key = issue["key"]
                f = issue["fields"]
                parts = []
                if f.get("description"):
                    parts.append(f["description"])
                for comment in (f.get("comment") or {}).get("comments", []):
                    author = (comment.get("author") or {}).get("displayName", "unknown")
                    parts.append(
                        "--- comment by {} ({}):\n{}".format(
                            author, comment.get("created", "")[:16], comment.get("body", "")
                        )
                    )

                updated = f.get("updated", "")
                assignee = (f.get("assignee") or {}).get("displayName") or (
                    f.get("reporter") or {}
                ).get("displayName", "unknown")
                status = (f.get("status") or {}).get("name", "")

                item = RawItem(
                    source="jira",
                    # updated timestamp in the ID: a later update becomes a new
                    # item, so the indexer picks up the change
                    id="jira-{}-{}".format(key, re.sub(r"[^0-9]", "", updated)[:12]),
                    url=f"{cfg.jira.base_url}/browse/{key}",
                    author=assignee,
                    timestamp=updated[:19] + "Z" if updated else "",
                    title="{} {} [{}]".format(key, f.get("summary", ""), status),
                    content="\n\n".join(parts) or "(no description)",
                    extra={"jira_key": key, "status": status},
                )
                save_raw(cfg.vault, item)
                count += 1

            start_at += len(data.get("issues", []))
            if start_at >= data.get("total", 0) or not data.get("issues"):
                break

    state.set_cursor("jira", run_started)
    print(f"jira: saved {count} items")
    return count
