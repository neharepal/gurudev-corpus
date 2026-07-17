"""Tests for tools/verify_arthasahit_ingest.py — the post-ingest checker
for the 7 RFC-017 arthasahit works.

Uses synthetic JSONL + a tiny numpy array on disk so we can exercise both
PASS and FAIL paths without touching the live 04_processed/ artifacts.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import verify_arthasahit_ingest as V


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _bootstrap_ok_corpus(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Minimal PASSing fixture: one child per arthasahit work + one prose child.

    - Each arthasahit work gets exactly ONE parent+child pair so we tick
      check (1) "every arthasahit work has children".
    - Alternating child pattern: cite_text=verse (no अर्थ) vs. no cite_text
      key (retrieval-only) so we cover both accepted shapes.
    - One non-arthasahit child so we exercise the scope-skip branch.
    - Row alignment: chunks.jsonl / chunks_meta.jsonl / embeddings.npy all
      have the same row count.
    """
    chunks = tmp_path / "chunks.jsonl"
    parents = tmp_path / "parents.jsonl"
    meta = tmp_path / "chunks_meta.jsonl"
    emb = tmp_path / "embeddings.npy"

    child_rows: list[dict] = []
    parent_rows: list[dict] = []
    for i, wid in enumerate(sorted(V.ARTHASAHIT_WORK_IDS)):
        pid = f"{wid}--mr--0000"
        parent_rows.append({
            "id": pid, "kind_level": "parent", "work_id": wid,
            "language": "mr", "text": "verse\nअर्थ - meaning",
        })
        row = {
            "id": f"{pid}--000", "kind_level": "child", "parent_id": pid,
            "work_id": wid, "language": "mr",
            "text": "करीं धंदा परि आवडती पाय\nअर्थ - meaning",
            "embed_text": "करीं धंदा परि आवडती पाय\nअर्थ - meaning",
        }
        if i % 2 == 0:
            # Even: citable — cite the verse only.
            row["cite_text"] = "करीं धंदा परि आवडती पाय"
        # Odd: retrieval-only (no cite_text key).
        child_rows.append(row)

    # Add a prose child to prove the verifier ignores non-arthasahit rows.
    child_rows.append({
        "id": "some-prose-work--en--0000--000", "kind_level": "child",
        "parent_id": "some-prose-work--en--0000", "work_id": "some-prose-work",
        "language": "en", "text": "prose", "cite_text": "prose",
    })
    parent_rows.append({
        "id": "some-prose-work--en--0000", "kind_level": "parent",
        "work_id": "some-prose-work", "language": "en", "text": "prose",
    })

    _write_jsonl(chunks, child_rows)
    _write_jsonl(parents, parent_rows)

    # chunks_meta is chunks with `text` stripped (embedder's write_meta shape).
    meta_rows = [{k: v for k, v in r.items() if k != "text"} for r in child_rows]
    _write_jsonl(meta, meta_rows)

    # embeddings.npy: same row count as chunks/meta, dim=4 (small but real).
    arr = np.zeros((len(child_rows), 4), dtype=np.float32)
    np.save(emb, arr)

    return chunks, parents, meta, emb


def test_verify_pass_on_clean_synthetic_corpus(tmp_path):
    chunks, parents, meta, emb = _bootstrap_ok_corpus(tmp_path)

    art_errors, art_stats = V.verify_arthasahit_children(chunks, parents)
    align_errors, align_stats = V.verify_row_alignment(chunks, meta, emb)

    assert art_errors == [], art_errors
    assert align_errors == [], align_errors
    assert art_stats["total_arthasahit_children"] == 7
    # Half citable, half retrieval-only across the 7 works (4 vs 3 given
    # sorted order + even/odd split — either way both are non-zero).
    assert art_stats["citable"] > 0
    assert art_stats["retrieval_only"] > 0
    assert set(art_stats["children_by_work"].keys()) == V.ARTHASAHIT_WORK_IDS
    assert (align_stats["chunks_lines"] == align_stats["meta_lines"]
            == align_stats["emb_rows"])


def test_verify_fails_when_artha_leaks_into_cite_text(tmp_path):
    """FAIL fixture: a child that SHOULD have been retrieval-only instead
    surfaced the sadhak's meaning in cite_text (the exact bug the arthasahit
    branch guards against). The verifier must catch this."""
    chunks, parents, meta, emb = _bootstrap_ok_corpus(tmp_path)

    # Corrupt one child: leak the marker word into cite_text.
    rows = [json.loads(l) for l in chunks.read_text(encoding="utf-8").splitlines() if l.strip()]
    for r in rows:
        if r["work_id"] == "tukaram-vachanamrut":
            r["cite_text"] = "करीं धंदा\nअर्थ - the sadhak's meaning that must not be cited"
            break
    _write_jsonl(chunks, rows)

    art_errors, _ = V.verify_arthasahit_children(chunks, parents)
    assert art_errors, "expected at least one error"
    assert any(V.ARTHA_MARKER in e for e in art_errors), art_errors


def test_verify_work_id_filter_scopes_checks(tmp_path):
    chunks, parents, _, _ = _bootstrap_ok_corpus(tmp_path)

    art_errors, art_stats = V.verify_arthasahit_children(
        chunks, parents, only_work_id="tukaram-vachanamrut",
    )
    assert art_errors == []
    assert set(art_stats["children_by_work"].keys()) == {"tukaram-vachanamrut"}
    assert art_stats["total_arthasahit_children"] == 1


def test_verify_work_id_filter_rejects_non_arthasahit(tmp_path):
    chunks, parents, _, _ = _bootstrap_ok_corpus(tmp_path)
    art_errors, _ = V.verify_arthasahit_children(
        chunks, parents, only_work_id="some-prose-work",
    )
    assert art_errors and "not one of the 7" in art_errors[0]


def test_verify_flags_missing_work(tmp_path):
    """If Neha runs the verifier before all 7 works are ingested, we surface
    the missing work_id rather than silently passing."""
    chunks, parents, _, _ = _bootstrap_ok_corpus(tmp_path)

    # Drop tukaram-vachanamrut rows entirely.
    rows = [json.loads(l) for l in chunks.read_text(encoding="utf-8").splitlines() if l.strip()]
    kept = [r for r in rows if r.get("work_id") != "tukaram-vachanamrut"]
    _write_jsonl(chunks, kept)

    art_errors, _ = V.verify_arthasahit_children(chunks, parents)
    assert any("tukaram-vachanamrut" in e and "no child rows" in e for e in art_errors), art_errors


def test_verify_flags_dangling_parent_id(tmp_path):
    chunks, parents, _, _ = _bootstrap_ok_corpus(tmp_path)

    parent_rows = [json.loads(l) for l in parents.read_text(encoding="utf-8").splitlines() if l.strip()]
    kept = [p for p in parent_rows if p.get("id") != "tukaram-vachanamrut--mr--0000"]
    _write_jsonl(parents, kept)

    art_errors, _ = V.verify_arthasahit_children(chunks, parents)
    assert any("not found in parents.jsonl" in e for e in art_errors), art_errors


def test_verify_flags_row_alignment_mismatch(tmp_path):
    chunks, parents, meta, emb = _bootstrap_ok_corpus(tmp_path)

    # Truncate embeddings.npy to one fewer row — the classic partial-write bug.
    arr = np.load(emb, mmap_mode="r")
    np.save(emb, np.array(arr[:-1]))

    align_errors, _ = V.verify_row_alignment(chunks, meta, emb)
    assert any("row-alignment" in e for e in align_errors), align_errors
