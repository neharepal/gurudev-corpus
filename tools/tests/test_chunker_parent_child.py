import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import chunker

def test_emits_parent_then_children():
    base = {"work_id": "demo", "language": "en", "kind": "canonical"}
    rows = list(chunker.emit_chunks_for_source(Path("x/text.md"),
        "Bhakti is the soul. Namasmaran is its practice.\n\nGrace descends fully.", base))
    parents = [r for r in rows if r.get("kind_level") == "parent"]
    children = [r for r in rows if r.get("parent_id")]
    assert parents and children
    # every child points at a real parent id
    pids = {p["id"] for p in parents}
    assert all(c["parent_id"] in pids for c in children)
    # child ids nest under parent ids
    assert all(c["id"].startswith(c["parent_id"] + "--") for c in children)
    # children carry embed_text + cite_text
    assert all("embed_text" in c and "cite_text" in c for c in children)
