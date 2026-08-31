from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import httpx

from ..config import Config, require_env
from ..state import State
from .base import RawItem, iso, save_raw


def collect(cfg: Config, state: State) -> int:
    if not cfg.gitlab_url:
        print("gitlab: no base_url configured, skipping")
        return 0

    headers = {"PRIVATE-TOKEN": require_env("GITLAB_TOKEN")}
    api = f"{cfg.gitlab_url}/api/v4"
    cursor = state.cursors.get("gitlab")
    if not cursor:
        cursor = iso(datetime.now(timezone.utc) - timedelta(days=7))
    run_started = iso()

    count = 0
    with httpx.Client(headers=headers, timeout=30) as client:
        me = client.get(f"{api}/user")
        me.raise_for_status()
        username = me.json()["username"]

        merge_requests = {}
        for params in (
            {"scope": "created_by_me"},
            {"scope": "all", "reviewer_username": username},
        ):
            params.update({"updated_after": cursor, "per_page": 50})
            resp = client.get(f"{api}/merge_requests", params=params)
            resp.raise_for_status()
            for mr in resp.json():
                merge_requests[mr["id"]] = mr

        for mr in merge_requests.values():
            parts = [mr.get("description") or "(no description)"]
            notes_resp = client.get(
                "{}/projects/{}/merge_requests/{}/notes".format(
                    api, mr["project_id"], mr["iid"]
                ),
                params={"per_page": 100, "sort": "asc"},
            )
            if notes_resp.status_code == 200:
                for note in notes_resp.json():
                    if note.get("system"):
                        continue
                    author = (note.get("author") or {}).get("username", "unknown")
                    parts.append(
                        "--- comment by {} ({}):\n{}".format(
                            author, note.get("created_at", "")[:16], note.get("body", "")
                        )
                    )

            updated = mr.get("updated_at", "")
            item = RawItem(
                source="gitlab",
                id="gitlab-{}-{}-{}".format(
                    mr["project_id"], mr["iid"], re.sub(r"[^0-9]", "", updated)[:12]
                ),
                url=mr.get("web_url", ""),
                author=(mr.get("author") or {}).get("username", "unknown"),
                timestamp=updated,
                title="!{} {} [{}]".format(mr["iid"], mr.get("title", ""), mr.get("state", "")),
                content="\n\n".join(parts),
                extra={
                    "project_id": mr["project_id"],
                    "iid": mr["iid"],
                    "state": mr.get("state", ""),
                    "source_branch": mr.get("source_branch", ""),
                },
            )
            save_raw(cfg.vault, item)
            count += 1

    state.cursors["gitlab"] = run_started
    print(f"gitlab: saved {count} items")
    return count
