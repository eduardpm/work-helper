import pytest

from work_helper.collectors.base import RawItem
from work_helper.indexer.categorize import categorize, normalize_slug
from work_helper.indexer.llm import extract_json


def test_extract_json_plain():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_with_think_and_fence():
    text = '<think>hmm {not json}</think>\n```json\n{"topic": "x"}\n```'
    assert extract_json(text) == {"topic": "x"}


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
            "topic": "Renovate Config",
            "topic_title": "Renovate config",
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
    idx = categorize(llm, item, ["other-topic"])
    assert idx.topic == "renovate-config"
    assert idx.tags == ["renovate"]
    assert idx.summary == "Discussed schedule."
    assert "other-topic" in llm.last_user
