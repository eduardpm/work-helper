from __future__ import annotations

from datetime import datetime, timezone

from ..config import Config, require_env
from ..state import State
from .base import RawItem, iso, save_raw


def collect(cfg: Config, state: State) -> int:
    from slack_sdk import WebClient

    if not cfg.slack_channels:
        print("slack: no channels configured, skipping")
        return 0

    client = WebClient(token=require_env("SLACK_TOKEN"))
    names = {}

    def name(user_id: str) -> str:
        if not user_id:
            return "unknown"
        if user_id not in names:
            try:
                user = client.users_info(user=user_id)["user"]
                names[user_id] = (
                    user["profile"].get("display_name")
                    or user.get("real_name")
                    or user_id
                )
            except Exception:
                names[user_id] = user_id
        return names[user_id]

    count = 0
    for channel in cfg.slack_channels:
        cursor_key = f"slack:{channel}"
        oldest = state.cursors.get(cursor_key, "0")
        latest_seen = float(oldest)
        page_cursor = None

        while True:
            resp = client.conversations_history(
                channel=channel, oldest=oldest, limit=200, cursor=page_cursor
            )
            for msg in resp["messages"]:
                ts = msg["ts"]
                latest_seen = max(latest_seen, float(ts))
                if msg.get("subtype") or not msg.get("text"):
                    continue

                lines = ["{}: {}".format(name(msg.get("user")), msg["text"])]
                if msg.get("reply_count"):
                    replies = client.conversations_replies(channel=channel, ts=ts)
                    for reply in replies["messages"][1:]:
                        lines.append(
                            "{}: {}".format(name(reply.get("user")), reply.get("text", ""))
                        )

                try:
                    url = client.chat_getPermalink(channel=channel, message_ts=ts)["permalink"]
                except Exception:
                    url = ""

                item = RawItem(
                    source="slack",
                    id=f"slack-{channel}-{ts}",
                    url=url,
                    author=name(msg.get("user")),
                    timestamp=iso(datetime.fromtimestamp(float(ts), tz=timezone.utc)),
                    title=msg["text"][:80],
                    content="\n".join(lines),
                    extra={"channel": channel, "replies": msg.get("reply_count", 0)},
                )
                save_raw(cfg.vault, item)
                count += 1

            if resp.get("has_more"):
                page_cursor = resp["response_metadata"]["next_cursor"]
            else:
                break

        state.cursors[cursor_key] = f"{latest_seen:.6f}"

    print(f"slack: saved {count} items")
    return count
