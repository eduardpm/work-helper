from work_helper.state import State


def test_cursor_roundtrip(tmp_path):
    state = State(tmp_path)
    assert state.get_cursor("slack:C1") is None
    state.set_cursor("slack:C1", "123.456")
    state.mark_processed("slack-C1-123.456")
    state.save()

    reloaded = State(tmp_path)
    assert reloaded.get_cursor("slack:C1") == "123.456"
    assert reloaded.is_processed("slack-C1-123.456")
    assert not reloaded.is_processed("other")
