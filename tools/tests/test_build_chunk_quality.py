import json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import build_chunk_quality as bcq

def test_build_adds_quality_score(tmp_path):
    meta = tmp_path / "chunks_meta.jsonl"
    chunks = tmp_path / "chunks.jsonl"
    meta.write_text(
        json.dumps({"work_id": "w", "char_start": 0}) + "\n" +
        json.dumps({"work_id": "w", "char_start": 9}) + "\n",
        encoding="utf-8",
    )
    chunks.write_text(
        json.dumps({"text": "## Part 13"}) + "\n" +
        json.dumps({"text": "Bhakti consists in love to God, and through the love of God, in the love of man, which is the essence of his teaching and the foundation of it. The practice of bhakti is not merely an emotional sentiment but a rigorous spiritual discipline that encompasses meditation, study, and service. Through the cultivation of devotion, one transcends the limitations of the ego and realizes the unity of all existence in the divine principle."}) + "\n",  # >200 chars so the length penalty doesn't drag a real-prose score below 0.7
        encoding="utf-8",
    )
    n = bcq.build_quality(meta, chunks)
    rows = [json.loads(l) for l in meta.read_text(encoding="utf-8").splitlines()]
    assert n == 2
    assert rows[0]["quality_score"] < 0.5   # heading = junk
    assert rows[1]["quality_score"] >= 0.7  # prose = clean
    # preserves existing fields + order
    assert rows[0]["work_id"] == "w" and rows[1]["char_start"] == 9

def test_build_is_idempotent(tmp_path):
    meta = tmp_path / "chunks_meta.jsonl"
    chunks = tmp_path / "chunks.jsonl"
    meta.write_text(json.dumps({"work_id": "w"}) + "\n", encoding="utf-8")
    chunks.write_text(json.dumps({"text": "## Part 13"}) + "\n", encoding="utf-8")
    bcq.build_quality(meta, chunks)
    first = meta.read_text(encoding="utf-8")
    bcq.build_quality(meta, chunks)
    assert meta.read_text(encoding="utf-8") == first
