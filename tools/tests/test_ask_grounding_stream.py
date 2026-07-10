# tools/tests/test_ask_grounding_stream.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import server

def test_replay_emits_fields_arrays_and_done():
    result = {
        "kind": "qa", "question": "q", "framing": "F",
        "citations": [{"quote": {"body": "b"}, "whyChosen": "w"}],
        "synthesis": "S",
    }
    events = list(server._replay_qa_as_sse(result))
    kinds = [k for k, _ in events]
    assert kinds[-1] == "done"
    # framing came through as a field, the citation as an array_item
    assert any(k == "field" and p.get("name") == "framing" for k, p in events)
    assert any(k == "array_item" and p.get("array") == "citations" for k, p in events)
    done = [p for k, p in events if k == "done"][0]
    assert done["response"]["synthesis"] == "S"
