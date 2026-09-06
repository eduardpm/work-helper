import pytest

from work_helper.collectors.base import RawItem
from work_helper.indexer.categorize import categorize, normalize_slug, summarize_state
from work_helper.indexer.llm import extract_json


def test_extract_json_plain():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_with_think_and_fence():
    text = '<think>hmm {not json}</think>\n```json\n{"epics": ["x"]}\n```'
    assert extract_json(text) == {"epics": ["x"]}


def test_extract_json_fails_loudly():
    with pytest.raises(ValueError):
        extract_json("I cannot answer that.")


def test_normalize_slug():
    assert normalize_slug("Renovate Config!") == "renovate-config"
    assert normalize_slug("  ") == "misc"


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload

    def json_chat(self, system, user):
        self.last_user = user
        return self.payload


def test_categorize_normalizes_output():
    llm = FakeLLM(
        {
            "epics": ["Stock Depletion", "stock-depletion", "misc"],
            "event": "Blocker",
            "tags": ["Renovate", ""],
            "people": ["Anna"],
            "summary": " Discussed schedule. ",
            "todos": ["decide schedule"],
            "refs": ["PROJ-123"],
        }
    )
    item = RawItem(
        source="slack", id="x", url="", author="anna",
        timestamp="2026-08-31T10:00:00Z", title="t", content="c",
    )
    idx = categorize(llm, item, ["other-epic"])
    assert idx.epics == ["stock-depletion", "misc"]  # deduped, slugged
    assert idx.event == "blocker"
    assert idx.tags == ["renovate"]
    assert idx.summary == "Discussed schedule."
    assert "other-epic" in llm.last_user


def test_categorize_bad_epics_fall_back():
    llm = FakeLLM({"epics": [], "event": "party", "summary": "x"})
    item = RawItem(
        source="slack", id="x", url="", author="a",
        timestamp="2026-08-31T10:00:00Z", title="t", content="c",
    )
    idx = categorize(llm, item, [])
    assert idx.epics == ["misc"]
    assert idx.event == ""


def test_categorize_keeps_titles_from_epic_objects():
    llm = FakeLLM({"epics": [{"slug": "Stock Depletion", "title": "Stock depletion events"}, "misc"], "summary": "x"})
    item = RawItem(
        source="jira", id="x", url="", author="a",
        timestamp="2026-08-31T10:00:00Z", title="t", content="c",
    )
    idx = categorize(llm, item, [])
    assert idx.epics == ["stock-depletion", "misc"]
    assert idx.titles == {"stock-depletion": "Stock depletion events"}


def test_summarize_state_strips_links():
    class ChatLLM:
        def chat(self, system, user):
            return "### Summary\nSee [slack link](https://x/y) and PROJ-1.\n"

    assert summarize_state(ChatLLM(), "T", "", "") == "### Summary\nSee slack link and PROJ-1."
