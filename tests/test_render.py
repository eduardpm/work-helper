from work_helper.collectors.base import RawItem
from work_helper.indexer.categorize import ItemIndex
from work_helper.indexer.render import (
    parse_epic,
    render_epic,
    update_daily,
    update_epic,
)


def make_item(item_id="slack-C1-1.0"):
    return RawItem(
        source="slack",
        id=item_id,
        url="https://slack.example/p1",
        author="anna",
        timestamp="2026-08-31T10:00:00Z",
        title="renovate config question",
        content="anna: what about the renovate schedule?",
    )


def make_index(todos, epics=("renovate-config",), event=""):
    return ItemIndex(
        epics=list(epics),
        event=event,
        summary="Anna asked about the renovate schedule.",
        tags=["renovate"],
        people=["anna"],
        todos=todos,
        refs=["PROJ-123"],
    )


def test_create_and_update_epic(tmp_path):
    item = make_item()
    idx = make_index(["decide schedule"], event="question")
    path = update_epic(tmp_path, item, idx, "renovate-config")
    assert path.name == "renovate-config.md"

    meta, title, state, todos, log = parse_epic(path.read_text())
    assert title == "Renovate config"
    assert state == ""  # placeholder parses back as empty
    assert meta["tags"] == ["renovate"]
    assert meta["refs"] == ["PROJ-123"]
    assert todos == ["- [ ] decide schedule"]
    assert "slack link" in log
    assert "**question**" in log

    # second item: duplicate todo must not double, new todo must appear
    item2 = make_item("slack-C1-2.0")
    update_epic(tmp_path, item2, make_index(["Decide schedule", "update config MR"]), "renovate-config")
    _, _, _, todos, log = parse_epic(path.read_text())
    assert todos == ["- [ ] decide schedule", "- [ ] update config MR"]
    assert log.count("### 2026-08-31") == 2


def test_state_survives_update(tmp_path):
    path = update_epic(tmp_path, make_item(), make_index([]), "renovate-config")
    meta, title, state, todos, log = parse_epic(path.read_text())
    path.write_text(render_epic(meta, title, "Waiting on Anna.", todos, log))

    update_epic(tmp_path, make_item("slack-C1-2.0"), make_index([]), "renovate-config")
    _, _, state, _, _ = parse_epic(path.read_text())
    assert state == "Waiting on Anna."


def test_checked_todo_survives_update(tmp_path):
    item = make_item()
    path = update_epic(tmp_path, item, make_index(["decide schedule"]), "renovate-config")
    # user ticks the box in Obsidian
    path.write_text(path.read_text().replace("- [ ] decide schedule", "- [x] decide schedule"))

    update_epic(tmp_path, make_item("slack-C1-2.0"), make_index(["decide schedule"]), "renovate-config")
    _, _, _, todos, _ = parse_epic(path.read_text())
    assert todos == ["- [x] decide schedule"]


def test_daily_note_links_all_epics(tmp_path):
    item = make_item()
    path = update_daily(tmp_path, item, make_index([], epics=("renovate-config", "ci")))
    text = path.read_text()
    assert text.startswith("# 2026-08-31")
    assert "[[renovate-config]]" in text
    assert "[[ci]]" in text
