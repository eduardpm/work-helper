from work_helper.collectors.base import RawItem
from work_helper.indexer.categorize import ItemIndex
from work_helper.indexer.render import parse_topic, update_daily, update_topic


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


def make_index(todos):
    return ItemIndex(
        topic="renovate-config",
        topic_title="Renovate config",
        summary="Anna asked about the renovate schedule.",
        tags=["renovate"],
        people=["anna"],
        todos=todos,
        refs=["PROJ-123"],
    )


def test_create_and_update_topic(tmp_path):
    item = make_item()
    path = update_topic(tmp_path, item, make_index(["decide schedule"]))
    assert path.name == "renovate-config.md"

    meta, title, todos, log = parse_topic(path.read_text())
    assert title == "Renovate config"
    assert meta["tags"] == ["renovate"]
    assert meta["refs"] == ["PROJ-123"]
    assert todos == ["- [ ] decide schedule"]
    assert "slack link" in log

    # second item: duplicate todo must not double, new todo must appear
    item2 = make_item("slack-C1-2.0")
    update_topic(tmp_path, item2, make_index(["Decide schedule", "update config MR"]))
    _, _, todos, log = parse_topic(path.read_text())
    assert todos == ["- [ ] decide schedule", "- [ ] update config MR"]
    assert log.count("### 2026-08-31") == 2


def test_checked_todo_survives_update(tmp_path):
    item = make_item()
    path = update_topic(tmp_path, item, make_index(["decide schedule"]))
    # user ticks the box in Obsidian
    path.write_text(path.read_text().replace("- [ ] decide schedule", "- [x] decide schedule"))

    update_topic(tmp_path, make_item("slack-C1-2.0"), make_index(["decide schedule"]))
    _, _, todos, _ = parse_topic(path.read_text())
    assert todos == ["- [x] decide schedule"]


def test_daily_note(tmp_path):
    item = make_item()
    path = update_daily(tmp_path, item, make_index([]))
    text = path.read_text()
    assert text.startswith("# 2026-08-31")
    assert "[[renovate-config]]" in text
