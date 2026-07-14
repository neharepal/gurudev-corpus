import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import chunker

def test_arthasahit_child_cites_verse_embeds_meaning():
    base = {"work_id": "tukaram-vachanamrut", "language": "mr", "kind": "canonical"}
    entry = "करीं धंदा परि आवडती पाय ॥१॥\nअर्थ - तुकाराम म्हणतात हे भक्तीचे वर्णन आहे."
    rows = list(chunker.emit_chunks_for_source(Path("x/text.md"), entry, base))
    kids = [r for r in rows if r.get("kind_level") == "child"]
    assert kids
    c = kids[0]
    assert "करीं धंदा" in c["cite_text"]              # verse is citable
    assert "अर्थ" not in c["cite_text"]                # meaning excluded from citation
    assert "म्हणतात" in c["embed_text"]                 # but meaning IS embedded for recall

def test_uncertain_split_is_retrieval_only():
    base = {"work_id": "sant-vachanamrut", "language": "mr", "kind": "canonical"}
    rows = list(chunker.emit_chunks_for_source(Path("x/text.md"),
        "गुरु गोविंद दोऊ खड़े । काके लागूं पाय ॥", base))
    kids = [r for r in rows if r.get("kind_level") == "child"]
    assert kids and all("cite_text" not in c for c in kids)   # never citable
