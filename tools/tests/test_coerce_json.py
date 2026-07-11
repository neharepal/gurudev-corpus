"""Regression: the model sometimes stringifies a list field in tool-use input.

QAResponse.citations arrived as a JSON *string* ('[{...}]') instead of an array,
failing pydantic with `type=list_type`. _coerce_json_containers repairs this before
validation. See llm_client._coerce_json_containers.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from llm_client import _coerce_json_containers


def test_stringified_list_field_is_parsed():
    inp = {"framing": "Bhakti is the soul.",
           "citations": '[{"label": "A", "whyChosen": "x"}]'}
    out = _coerce_json_containers(inp)
    assert isinstance(out["citations"], list)
    assert out["citations"][0]["label"] == "A"


def test_stringified_object_field_is_parsed():
    out = _coerce_json_containers({"quote": '{"quoteStart": "Devotion ascends"}'})
    assert isinstance(out["quote"], dict)
    assert out["quote"]["quoteStart"] == "Devotion ascends"


def test_prose_untouched():
    # a real list already; prose that merely starts with '[' but isn't JSON
    inp = {"framing": "[note] not json", "synthesis": "Plain.", "citations": [{"label": "A"}]}
    out = _coerce_json_containers(inp)
    assert out["framing"] == "[note] not json"        # invalid JSON → left as str
    assert out["synthesis"] == "Plain."
    assert out["citations"] == [{"label": "A"}]        # already a list → unchanged


def test_non_dict_input_passthrough():
    assert _coerce_json_containers("not a dict") == "not a dict"
    assert _coerce_json_containers(None) is None
