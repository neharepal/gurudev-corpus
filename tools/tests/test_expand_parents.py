import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server

def test_expand_groups_by_parent_and_caps():
    metas = [
        {"id":"w--en--0000--000","parent_id":"w--en--0000","cite_text":"c0","kind_level":"child"},
        {"id":"w--en--0000--005","parent_id":"w--en--0000","cite_text":"c5","kind_level":"child"},
        {"id":"w--en--0001--002","parent_id":"w--en--0001","cite_text":"d2","kind_level":"child"},
    ]
    parents = {"w--en--0000":{"text":"PARENT-0"}, "w--en--0001":{"text":"PARENT-1"}}
    groups = server.expand_children_to_parents([0,1,2], metas, parents, max_per_parent=2, top_k=8)
    assert [g["parent_id"] for g in groups] == ["w--en--0000","w--en--0001"]
    assert groups[0]["parent_text"] == "PARENT-0"
    assert len(groups[0]["children"]) == 2      # both children of parent 0, capped at 2
