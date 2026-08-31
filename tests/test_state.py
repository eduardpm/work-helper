from work_helper.state import State


def test_cursor_roundtrip(tmp_path):
    state = State(tmp_path)
    assert state.cursors.get("slack:C1") is None
    state.cursors["slack:C1"] = "123.456"
    state.processed.add("slack-C1-123.456")
    state.save()

    reloaded = State(tmp_path)
    assert reloaded.cursors["slack:C1"] == "123.456"
    assert "slack-C1-123.456" in reloaded.processed
    assert "other" not in reloaded.processed
