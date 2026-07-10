# Phase 1A — Retrieval Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the buried-passage, bare-query, and OCR-junk retrieval failures by adding index-time junk scoring, a cross-encoder reranker over a widened candidate set, and LLM query rewriting + HyDE — all flag-gated and fail-safe, no re-embed.

**Architecture:** Three new pure/isolated modules (`chunk_quality`, `reranker`, `query_understanding`) plus wiring into `server._retrieve`. The reranker becomes the relevance authority; MMR is demoted to post-rerank dedup. Every stage degrades to today's behavior on failure.

**Tech Stack:** Python 3.8 (anaconda), NumPy, FlagEmbedding (`bge-reranker-v2-m3`), sentence-transformers (BGE-M3, already present), Anthropic Haiku (already used by `intent.py`/`query_translation.py`), pytest.

## Global Constraints

- No re-embedding. `quality_score` is written into `04_processed/embeddings/chunks_meta.jsonl` (row-aligned with `embeddings.npy`); embeddings untouched.
- Every new stage is **flag-gated** (env var, default off) and **fail-safe**: on error/timeout the pipeline uses today's behavior.
- Junk scoring is **script-agnostic** (Devanagari OR Latin letters both count as real prose) and uses a **bilingual** stopword set — the corpus is trilingual (Marathi/Hindi/English). This deviates from the spec's Devanagari-only heuristic on purpose, to avoid flagging legitimate English works.
- Junk is **downweighted, never deleted** (score multiplier); a hard floor excludes only the worst.
- Reranker runs in-process, lazy-loaded, device auto-detect, fp16. Model: `BAAI/bge-reranker-v2-m3`.
- `tools/eval_retrieval.py` is the regression gate: no stage is enabled until it validates with **zero regressions** vs. the current 11/12 baseline.
- Offline eval must not make API calls (`use_llm=False` disables rewrite/HyDE, mirroring `intent.py`).

---

### Task 1: `chunk_quality` — deterministic junk scoring (pure functions)

**Files:**
- Create: `tools/chunk_quality.py`
- Test: `tools/tests/test_chunk_quality.py`

**Interfaces:**
- Produces: `quality_score(text: str) -> float` (in `[0,1]`, 1.0 = clean prose), `is_junk(text: str, threshold: float = 0.5) -> bool`.

- [ ] **Step 1: Write the failing test**

```python
# tools/tests/test_chunk_quality.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import chunk_quality as cq

# Real prose (Marathi) scores high
MR_PROSE = ("रामभाऊंनी बांधलेल्या 'कार्लाइल कॉटेज' चा उल्लेख मागें आलाच आहे. "
            "'कार्लाइल कॉटेज' हौसेची असली तरी बेताची होती. त्यामुळे प्रकृतीला "
            "मानवेल व ध्यानधारणेला सोयीची होईल, अशी एखादी निवांत जागा त्यांना पाहिजे होती.")
# Real prose (English) must ALSO score high — corpus is trilingual
EN_PROSE = ("Bhakti does not consist in religious ceremonials, pilgrimages, or "
            "formal idol-worship; it consists in love to God, and through the love "
            "of God, in the love of man. This is the foundation of his teaching.")

def test_real_marathi_prose_high():
    assert cq.quality_score(MR_PROSE) >= 0.7
    assert cq.is_junk(MR_PROSE) is False

def test_real_english_prose_high():
    # The report's Devanagari-ratio heuristic would wrongly flag this; ours must not.
    assert cq.quality_score(EN_PROSE) >= 0.7
    assert cq.is_junk(EN_PROSE) is False

def test_heading_marker_is_junk():
    assert cq.is_junk("## Part 13") is True
    assert cq.is_junk("<!-- page 025 -->  (2)") is True
    assert cq.is_junk("काकांची चर्चा") is True  # bare title, <100 chars

def test_village_digit_list_is_junk():
    lst = "२० मोजे डि कसाळ  ३१ मोजे कागनरी  २१ मोजे कात्राळ  ३२ मौजे गुरवि नाळ  २२ मोजे करनाळ  ३३ मौजे करोळी"
    assert cq.is_junk(lst) is True  # high digit ratio + no stopwords

def test_symbol_garble_is_junk():
    assert cq.is_junk("aataziga ळटपवृक्षवन्जयु काणि रय्य ( राग-पुरि या धनाध्रि ; तार") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tools/tests/test_chunk_quality.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'chunk_quality'`

- [ ] **Step 3: Write minimal implementation**

```python
# tools/chunk_quality.py
"""Deterministic per-chunk quality scoring to downweight OCR/structural junk.

The corpus is TRILINGUAL (Marathi/Hindi/English). So "real prose" is detected
by LETTER density (Devanagari OR Latin both count) plus stopword presence in
either language — NOT by Devanagari ratio, which would wrongly flag the ~60%
English canonical works. Junk = short structural fragments (headings, page
markers, bare titles), digit/list pages (page numbers, census/village lists),
and symbol garble (bad OCR). Pure functions; no I/O.
"""
from __future__ import annotations
import re

_DEVA = re.compile(r"[ऀ-ॿ]")
_LATIN = re.compile(r"[A-Za-z]")

# Bilingual stopwords — the highest-signal "coherent prose vs list/heading" check.
_EN_STOP = frozenset({
    "the", "and", "of", "to", "in", "a", "is", "that", "for", "it", "as",
    "with", "was", "his", "he", "on", "are", "this", "which", "by", "not",
})
_MR_STOP = frozenset({
    "आणि", "आहे", "या", "तो", "हे", "मध्ये", "पण", "व", "की", "नाही",
    "होते", "त्या", "हा", "ही", "तें", "त्यांनी", "असे", "होता",
})
_STOP = _EN_STOP | _MR_STOP


def _ratios(text: str) -> tuple[float, float, float]:
    """Return (letter_ratio, digit_ratio, symbol_ratio) over non-space chars."""
    non_space = [c for c in text if not c.isspace()]
    if not non_space:
        return 0.0, 0.0, 1.0
    n = len(non_space)
    letters = sum(1 for c in non_space if _DEVA.match(c) or _LATIN.match(c))
    digits = sum(1 for c in non_space if c.isdigit())
    symbols = n - letters - digits
    return letters / n, digits / n, symbols / n


def _stopword_count(text: str) -> int:
    toks = [t.strip(".,;:!?\"'()[]{}…।॥") for t in text.lower().split()]
    return sum(1 for t in toks if t in _STOP)


def quality_score(text: str) -> float:
    """Return a [0,1] prose-quality score (1.0 = clean prose, low = junk).

    Multiplicative soft penalties so any single strong junk signal pulls the
    score down. Thresholds are conservative to avoid false-positives on real
    (esp. short-but-legit) content; tune on labeled chunks if needed.
    """
    s = text.strip()
    if not s:
        return 0.0
    letter_r, digit_r, symbol_r = _ratios(s)
    stop_n = _stopword_count(s)
    length = len(s)

    score = 1.0
    # Length: short fragments (headings, markers, bare titles) are almost always junk.
    if length < 100:
        score *= 0.15
    elif length < 200:
        score *= 0.6
    # Letters must dominate real prose.
    if letter_r < 0.45:
        score *= 0.2
    elif letter_r < 0.6:
        score *= 0.6
    # Digit-heavy = page numbers / lists / census tables.
    if digit_r > 0.25:
        score *= 0.2
    elif digit_r > 0.15:
        score *= 0.6
    # Symbol-heavy = OCR garble.
    if symbol_r > 0.25:
        score *= 0.4
    # Coherent prose has stopwords; lists/headings/garble do not.
    if length >= 200 and stop_n < 2:
        score *= 0.3
    return round(max(0.0, min(1.0, score)), 4)


def is_junk(text: str, threshold: float = 0.5) -> bool:
    """True when quality_score is below `threshold` (default 0.5)."""
    return quality_score(text) < threshold
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tools/tests/test_chunk_quality.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add tools/chunk_quality.py tools/tests/test_chunk_quality.py
git commit -m "chunk_quality: script-agnostic deterministic junk scoring"
```

---

### Task 2: `build_chunk_quality` — write `quality_score` into `chunks_meta.jsonl`

**Files:**
- Create: `tools/build_chunk_quality.py`
- Test: `tools/tests/test_build_chunk_quality.py`

**Interfaces:**
- Consumes: `chunk_quality.quality_score` (Task 1).
- Produces: a CLI that rewrites `04_processed/embeddings/chunks_meta.jsonl` adding a `quality_score` float to each row (row order preserved, aligned with `embeddings.npy`). Idempotent. `build_quality(meta_path, chunks_path) -> int` (count updated) for testing.

- [ ] **Step 1: Write the failing test**

```python
# tools/tests/test_build_chunk_quality.py
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
        json.dumps({"text": "Bhakti consists in love to God, and through the love of God, in the love of man, which is the essence of his teaching and the foundation of it."}) + "\n",
        encoding="utf-8",
    )
    n = bcq.build_quality(meta, chunks)
    rows = [json.loads(l) for l in meta.read_text(encoding="utf-8").splitlines()]
    assert n == 2
    assert rows[0]["quality_score"] < 0.5   # heading = junk
    assert rows[1]["quality_score"] >= 0.7  # prose = clean
    # preserves existing fields + order
    assert rows[0]["work_id"] == "w" and rows[1]["char_start"] == 9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tools/tests/test_build_chunk_quality.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'build_chunk_quality'`

- [ ] **Step 3: Write minimal implementation**

```python
# tools/build_chunk_quality.py
"""One-time (idempotent) pass: add `quality_score` to each chunks_meta row.

Reads chunk text from 04_processed/chunks.jsonl (row-aligned) and the metadata
from 04_processed/embeddings/chunks_meta.jsonl, writes quality_score into each
meta row. Does NOT touch embeddings.npy — no re-embed. Atomic write via temp+replace.
"""
from __future__ import annotations
import json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chunk_quality

REPO = Path(__file__).resolve().parent.parent
META_PATH = REPO / "04_processed" / "embeddings" / "chunks_meta.jsonl"
CHUNKS_PATH = REPO / "04_processed" / "chunks.jsonl"


def _load_texts(chunks_path: Path) -> list[str]:
    texts: list[str] = []
    with chunks_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            try:
                texts.append(json.loads(line).get("text", "") if line else "")
            except Exception:
                texts.append("")
    return texts


def build_quality(meta_path: Path, chunks_path: Path) -> int:
    texts = _load_texts(chunks_path)
    rows: list[dict] = []
    with meta_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    updated = 0
    for i, row in enumerate(rows):
        text = texts[i] if i < len(texts) else ""
        row["quality_score"] = chunk_quality.quality_score(text)
        updated += 1
    tmp = meta_path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    os.replace(tmp, meta_path)
    return updated


if __name__ == "__main__":
    n = build_quality(META_PATH, CHUNKS_PATH)
    print(f"quality_score written for {n} chunks -> {META_PATH}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tools/tests/test_build_chunk_quality.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Run the build for real, then commit**

```bash
python tools/build_chunk_quality.py
# Expected: "quality_score written for 16386 chunks -> .../chunks_meta.jsonl"
git add tools/build_chunk_quality.py tools/tests/test_build_chunk_quality.py
git commit -m "build_chunk_quality: write quality_score into chunks_meta (no re-embed)"
```
Note: `chunks_meta.jsonl` is gitignored (under `04_processed`), so only the scripts are committed. The build is re-runnable on any machine.

---

### Task 3: Junk downweight in retrieval (flag-gated)

**Files:**
- Modify: `tools/server.py` — `_retrieve` (the block after `fused = retrieve.fused_candidate_scores(...)`, ~line 496).
- Test: `tools/tests/test_junk_downweight.py`

**Interfaces:**
- Consumes: `meta["quality_score"]` (Task 2), env `ENABLE_JUNK_WEIGHT`.
- Produces: `retrieve.apply_quality_weights(fused, metas, enabled) -> np.ndarray` (new helper in `retrieve.py`, so it is unit-testable without the server).

- [ ] **Step 1: Write the failing test**

```python
# tools/tests/test_junk_downweight.py
import sys, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import retrieve

def test_quality_weight_downranks_junk():
    fused = np.array([0.030, 0.030, 0.030], dtype=np.float32)
    metas = [
        {"quality_score": 1.0},   # clean
        {"quality_score": 0.1},   # junk
        {},                        # missing -> treated as 1.0 (fail-open)
    ]
    out = retrieve.apply_quality_weights(fused, metas, enabled=True)
    assert out[1] < out[0]          # junk downweighted below clean
    assert out[2] == fused[2]        # missing score = no penalty

def test_disabled_is_identity():
    fused = np.array([0.03, 0.03], dtype=np.float32)
    metas = [{"quality_score": 0.1}, {"quality_score": 1.0}]
    out = retrieve.apply_quality_weights(fused, metas, enabled=False)
    assert np.allclose(out, fused)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tools/tests/test_junk_downweight.py -q`
Expected: FAIL with `AttributeError: module 'retrieve' has no attribute 'apply_quality_weights'`

- [ ] **Step 3: Write minimal implementation**

Add to `tools/retrieve.py` (near `apply_intent_tier_weights`):

```python
def apply_quality_weights(
    fused: np.ndarray,
    metas: list,
    *,
    enabled: bool,
) -> np.ndarray:
    """Multiply fused candidate scores by each chunk's quality_score.

    Downweights OCR/structural junk so it cannot crowd the top-k on weak
    queries. Fail-open: a missing quality_score is treated as 1.0 (no penalty),
    so a corpus without the field behaves exactly as before. `enabled=False`
    returns the input unchanged.
    """
    if not enabled:
        return fused
    w = np.fromiter(
        (float(m.get("quality_score", 1.0)) for m in metas),
        dtype=np.float32, count=len(metas),
    )
    return fused * w
```

Then in `tools/server.py` `_retrieve`, immediately after the `fused = retrieve.fused_candidate_scores(...)` call and before `cand_idx = np.argpartition(...)`:

```python
    fused = retrieve.apply_quality_weights(
        fused, sub_metas, enabled=os.environ.get("ENABLE_JUNK_WEIGHT") == "1"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tools/tests/test_junk_downweight.py tools/tests/test_hybrid_retrieval.py -q`
Expected: PASS (all)

- [ ] **Step 5: Validate offline (no regression), then commit**

```bash
python tools/eval_retrieval.py --top-k 8
# Expected: still 11 PASS / 1 FAIL (the documented MR cross-lingual case). No new failures.
git add tools/retrieve.py tools/server.py tools/tests/test_junk_downweight.py
git commit -m "retrieval: quality-weight downranking of junk chunks (ENABLE_JUNK_WEIGHT)"
```

---

### Task 4: `reranker` — cross-encoder wrapper (lazy, fail-safe)

**Files:**
- Create: `tools/reranker.py`
- Test: `tools/tests/test_reranker.py`

**Interfaces:**
- Produces: `class Reranker` with `rerank(query: str, passages: list[str]) -> list[float]` and `available() -> bool`; module-level `get_reranker() -> Reranker` singleton. Injectable `_scorer` for tests (no model download in CI).

- [ ] **Step 1: Write the failing test**

```python
# tools/tests/test_reranker.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import reranker as rr

def test_rerank_orders_by_injected_scorer():
    # Inject a fake cross-encoder so the test needs no model download.
    r = rr.Reranker(scorer=lambda pairs: [len(p[1]) for p in pairs])
    scores = r.rerank("q", ["short", "a much longer passage"])
    assert scores[1] > scores[0]
    assert r.available() is True

def test_rerank_empty_passages():
    r = rr.Reranker(scorer=lambda pairs: [1.0 for _ in pairs])
    assert r.rerank("q", []) == []

def test_unavailable_when_load_fails():
    def boom():
        raise RuntimeError("no model")
    r = rr.Reranker(loader=boom)
    assert r.available() is False
    assert r.rerank("q", ["a", "b"]) == []   # fail-safe: empty -> caller falls back
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tools/tests/test_reranker.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'reranker'`

- [ ] **Step 3: Write minimal implementation**

```python
# tools/reranker.py
"""Cross-encoder reranker (BAAI/bge-reranker-v2-m3), lazy + fail-safe.

Retrieval is a bi-encoder: query and passage are embedded independently, so
relevance is never judged against the actual query. A cross-encoder scores
(query, passage) jointly with full attention and recomputes relevance from
scratch — the tool that rescues a buried-but-relevant passage (MMR cannot).

Loaded once, in-process, at first use. Any load/scoring failure disables the
reranker (available()==False, rerank()==[]) so the caller falls back to the
existing MMR ranking. `scorer`/`loader` hooks let tests avoid a model download.
"""
from __future__ import annotations
from typing import Callable, Optional

_MODEL = "BAAI/bge-reranker-v2-m3"


class Reranker:
    def __init__(
        self,
        *,
        scorer: Optional[Callable[[list], list]] = None,
        loader: Optional[Callable[[], Callable[[list], list]]] = None,
    ) -> None:
        self._scorer = scorer
        self._loader = loader or _default_loader
        self._tried = scorer is not None

    def _ensure(self) -> None:
        if self._tried:
            return
        self._tried = True
        try:
            self._scorer = self._loader()
        except Exception:
            self._scorer = None

    def available(self) -> bool:
        self._ensure()
        return self._scorer is not None

    def rerank(self, query: str, passages: list) -> list:
        """Return one relevance score per passage (higher = more relevant).

        Returns [] on unavailability/failure so the caller can detect it and
        fall back. Never raises.
        """
        if not passages:
            return []
        self._ensure()
        if self._scorer is None:
            return []
        try:
            pairs = [[query, p] for p in passages]
            scores = self._scorer(pairs)
            return [float(s) for s in scores]
        except Exception:
            return []


def _default_loader() -> Callable[[list], list]:
    """Load bge-reranker-v2-m3 via FlagEmbedding; return a pair-scoring fn."""
    from FlagEmbedding import FlagReranker
    fr = FlagReranker(_MODEL, use_fp16=True)  # auto-detects CUDA; CPU/MPS otherwise
    def score(pairs: list) -> list:
        out = fr.compute_score(pairs, normalize=True)
        return out if isinstance(out, list) else [out]
    return score


_singleton: Optional[Reranker] = None


def get_reranker() -> Reranker:
    global _singleton
    if _singleton is None:
        _singleton = Reranker()
    return _singleton
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tools/tests/test_reranker.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add tools/reranker.py tools/tests/test_reranker.py
git commit -m "reranker: lazy fail-safe bge-reranker-v2-m3 cross-encoder wrapper"
```

---

### Task 5: Wire reranker into `_retrieve` (widen → rerank → top_k), flag-gated

**Files:**
- Modify: `tools/server.py` — `_retrieve` (candidate selection + rerank, replacing the direct MMR-to-top_k path when enabled), ~lines 500–512.
- Test: `tools/tests/test_retrieve_rerank_wiring.py`

**Interfaces:**
- Consumes: `reranker.get_reranker()` (Task 4), `retrieve.load_chunk_text`, env `ENABLE_RERANK`, `RERANK_CANDIDATES` (default `str(retrieve.INITIAL_CANDIDATES)`).
- Produces: reranked `out` list ordered by cross-encoder score; on reranker-unavailable, identical output to today (MMR path).

- [ ] **Step 1: Write the failing test**

```python
# tools/tests/test_retrieve_rerank_wiring.py
# Verifies _rerank_candidates reorders (idx, text) pairs by the reranker and
# keeps top_k; falls back to input order when the reranker is unavailable.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import server

class _FakeRer:
    def __init__(self, avail, scores=None): self._a=avail; self._s=scores
    def available(self): return self._a
    def rerank(self, q, passages): return self._s or []

def test_rerank_reorders_and_truncates():
    cands = [(0, "alpha"), (1, "beta"), (2, "gamma")]
    rer = _FakeRer(True, scores=[0.1, 0.9, 0.5])  # beta best, gamma, alpha
    out = server._rerank_candidates("q", cands, rer, top_k=2)
    assert [i for i, _ in out] == [1, 2]

def test_rerank_unavailable_keeps_input_order():
    cands = [(0, "a"), (1, "b"), (2, "c")]
    rer = _FakeRer(False)
    out = server._rerank_candidates("q", cands, rer, top_k=2)
    assert [i for i, _ in out] == [0, 1]   # first top_k of the input (MMR) order
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tools/tests/test_retrieve_rerank_wiring.py -q`
Expected: FAIL with `AttributeError: module 'server' has no attribute '_rerank_candidates'`

- [ ] **Step 3: Write minimal implementation**

Add a helper to `tools/server.py` (module level, near `_retrieve`):

```python
def _rerank_candidates(question, candidates, reranker_obj, *, top_k):
    """Reorder [(idx, text), ...] by cross-encoder relevance; keep top_k.

    Fail-safe: if the reranker is unavailable or returns the wrong count,
    keep the input order (already MMR-ranked) and just truncate to top_k.
    """
    if not reranker_obj.available() or not candidates:
        return candidates[:top_k]
    texts = [t for _, t in candidates]
    scores = reranker_obj.rerank(question, texts)
    if len(scores) != len(candidates):
        return candidates[:top_k]
    order = sorted(range(len(candidates)), key=lambda i: scores[i], reverse=True)
    return [candidates[i] for i in order[:top_k]]
```

Then modify `_retrieve` so that when `ENABLE_RERANK == "1"`: build a widened candidate pool (up to `RERANK_CANDIDATES`) from `cand_idx`, load each chunk's text, run MMR only for dedup (large `max_per_source`), then `_rerank_candidates(...)` to `top_k`. Replace the current `reranked = retrieve.mmr_rerank(...)` block with:

```python
    import reranker as _reranker_mod
    rerank_on = os.environ.get("ENABLE_RERANK") == "1"
    if rerank_on:
        widen = int(os.environ.get("RERANK_CANDIDATES", str(retrieve.INITIAL_CANDIDATES)))
        pool = cand_idx[:widen]
        # MMR first only to drop near-duplicate OCR chunks, generous cap.
        deduped = retrieve.mmr_rerank(
            qvec, pool, fused[pool], sub_emb, sub_metas,
            top_k=len(pool), mmr_lambda=mmr_lambda, max_per_source=max_per_source,
        )
        cand_pairs = []
        for idx, _mmr in deduped:
            oidx = int(keep_idx[idx]) if keep_idx is not None else int(idx)
            cand_pairs.append((idx, retrieve.load_chunk_text(sub_metas[idx], oidx)))
        top = _rerank_candidates(question, cand_pairs, _reranker_mod.get_reranker(), top_k=top_k)
        reranked = [(idx, 0.0) for idx, _txt in top]  # score slot unused downstream
    else:
        reranked = retrieve.mmr_rerank(
            qvec, cand_idx, cand_scores, sub_emb, sub_metas,
            top_k=top_k, mmr_lambda=mmr_lambda, max_per_source=max_per_source,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tools/tests/test_retrieve_rerank_wiring.py tools/tests/test_hybrid_retrieval.py -q`
Expected: PASS (all)

- [ ] **Step 5: Validate offline with rerank enabled, then commit**

```bash
ENABLE_RERANK=1 python tools/eval_retrieval.py --top-k 8   # first run downloads the model (~2.3GB)
# Expected: >= 11 PASS, zero regressions; entity queries (Carlyle GAP3) should hold or improve.
git add tools/server.py tools/tests/test_retrieve_rerank_wiring.py
git commit -m "retrieval: cross-encoder rerank over widened pool (ENABLE_RERANK)"
```
Note: `eval_retrieval.py` calls `server`-independent retrieval; add a `--rerank` path to it in Task 8 so the harness exercises the reranker directly.

---

### Task 6: `query_understanding` — rewrite + HyDE (mirror `query_translation`)

**Files:**
- Create: `tools/query_understanding.py`
- Test: `tools/tests/test_query_understanding.py`

**Interfaces:**
- Produces: `rewrite_query(q, *, use_llm=True, rewriter=None) -> Optional[str]`, `hypothetical_doc(q, *, use_llm=True, generator=None) -> Optional[str]`. Return `None` when disabled / failed / empty / echo of input.

- [ ] **Step 1: Write the failing test**

```python
# tools/tests/test_query_understanding.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import query_understanding as qu

def test_rewrite_uses_injected_and_strips():
    out = qu.rewrite_query("कारलाईल कॉटेज", rewriter=lambda q: "  कारलाईल कॉटेज कुठे बांधली?  ")
    assert out == "कारलाईल कॉटेज कुठे बांधली?"

def test_rewrite_none_on_echo_or_empty():
    assert qu.rewrite_query("x", rewriter=lambda q: "x") is None
    assert qu.rewrite_query("x", rewriter=lambda q: "") is None

def test_rewrite_none_when_llm_disabled():
    assert qu.rewrite_query("anything", use_llm=False) is None

def test_hyde_uses_injected():
    out = qu.hypothetical_doc("bhakti", generator=lambda q: "Bhakti is devotion to God, love of man.")
    assert "devotion" in out

def test_hyde_failsafe_on_exception():
    def boom(q): raise RuntimeError("down")
    assert qu.hypothetical_doc("q", generator=boom) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tools/tests/test_query_understanding.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'query_understanding'`

- [ ] **Step 3: Write minimal implementation**

```python
# tools/query_understanding.py
"""Query rewriting + HyDE for retrieval (mirrors query_translation.py).

A bare/short query lands in a sparse embedding region; a full-prose rewrite or
a hypothetical answer paragraph (HyDE) moves the search ANCHOR into the
descriptive-prose neighborhood where the answer actually lives — the effect we
already observe when a user asks a full question. Retrieval embeds these
ADDITIONAL query strings alongside the original (BM25 on the original stays the
exact-match backbone). Cached Haiku; any failure returns None (no-op).
"""
from __future__ import annotations
from functools import lru_cache
from typing import Callable, Optional

_MODEL = "claude-haiku-4-5"
_client = None


def _get_client():
    global _client
    if _client is None:
        from anthropic import Anthropic
        _client = Anthropic()
    return _client


def _clean(out: Optional[str], original: str) -> Optional[str]:
    if not out:
        return None
    out = out.strip()
    if not out or out == original.strip():
        return None
    return out


def rewrite_query(query, *, use_llm=True, rewriter: Optional[Callable[[str], Optional[str]]] = None):
    if not query or not query.strip():
        return None
    if rewriter is None and not use_llm:
        return None
    fn = rewriter or _default_rewrite
    try:
        return _clean(fn(query), query)
    except Exception:
        return None


def hypothetical_doc(query, *, use_llm=True, generator: Optional[Callable[[str], Optional[str]]] = None):
    if not query or not query.strip():
        return None
    if generator is None and not use_llm:
        return None
    fn = generator or _default_hyde
    try:
        out = fn(query)
        return out.strip() if out and out.strip() else None
    except Exception:
        return None


@lru_cache(maxsize=512)
def _default_rewrite(query: str) -> Optional[str]:
    prompt = (
        "Rewrite this search query for a Marathi/Hindi/English corpus about "
        "Gurudev R. D. Ranade and the Nimbargi (Inchgeri) lineage into a fuller, "
        "explicit search query. Keep the SAME language/script. Expand a bare "
        "topic into what a reader would want to know (what it is, who/where/when, "
        "significance). Do NOT invent facts. Output ONLY the rewritten query.\n\n"
        f"Query: {query}\nRewritten:"
    )
    r = _get_client().messages.create(model=_MODEL, max_tokens=96,
                                      messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in r.content if getattr(b, "type", None) == "text").strip() or None


@lru_cache(maxsize=512)
def _default_hyde(query: str) -> Optional[str]:
    prompt = (
        "Write a short hypothetical passage (2-4 sentences) that would answer "
        "this question about Gurudev R. D. Ranade / the Nimbargi (Inchgeri) "
        "lineage, in the SAME language/script as the question. It is a SEARCH "
        "AID, not a shown answer: stay general, do not fabricate specific names, "
        "dates, or numbers. Output ONLY the passage.\n\n"
        f"Question: {query}\nPassage:"
    )
    r = _get_client().messages.create(model=_MODEL, max_tokens=160,
                                      messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in r.content if getattr(b, "type", None) == "text").strip() or None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tools/tests/test_query_understanding.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add tools/query_understanding.py tools/tests/test_query_understanding.py
git commit -m "query_understanding: LLM rewrite + HyDE (cached, fail-safe)"
```

---

### Task 7: Wire rewrite + HyDE into `_retrieve` (flag-gated)

**Files:**
- Modify: `tools/server.py` — `_retrieve`, the dense/BM25 assembly block (~lines 475–499, alongside the existing translation vectors).
- Test: `tools/tests/test_query_understanding_wiring.py`

**Interfaces:**
- Consumes: `query_understanding.rewrite_query`, `query_understanding.hypothetical_doc` (Task 6), env `ENABLE_QUERY_REWRITE`, `ENABLE_HYDE`.
- Produces: extra dense vectors (per-passage MAX into `scores`) and extra `bm25_queries` entries, exactly like the existing `q_dev`/`q_en` translation path.

- [ ] **Step 1: Write the failing test**

```python
# tools/tests/test_query_understanding_wiring.py
# _extra_query_strings returns the rewrite/HyDE strings to fold into retrieval,
# honoring the env flags; empty when disabled.
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import server

def test_extra_queries_when_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_QUERY_REWRITE", "1")
    monkeypatch.setenv("ENABLE_HYDE", "1")
    monkeypatch.setattr(server.query_understanding, "rewrite_query", lambda q: "REWRITE")
    monkeypatch.setattr(server.query_understanding, "hypothetical_doc", lambda q: "HYDE")
    assert server._extra_query_strings("q") == ["REWRITE", "HYDE"]

def test_extra_queries_empty_when_disabled(monkeypatch):
    monkeypatch.delenv("ENABLE_QUERY_REWRITE", raising=False)
    monkeypatch.delenv("ENABLE_HYDE", raising=False)
    assert server._extra_query_strings("q") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tools/tests/test_query_understanding_wiring.py -q`
Expected: FAIL with `AttributeError: module 'server' has no attribute '_extra_query_strings'`

- [ ] **Step 3: Write minimal implementation**

Add `import query_understanding` to `tools/server.py` imports, and a helper:

```python
def _extra_query_strings(question):
    """Rewrite + HyDE strings to fold into retrieval, per env flags. [] if off."""
    extras = []
    if os.environ.get("ENABLE_QUERY_REWRITE") == "1":
        rw = query_understanding.rewrite_query(question)
        if rw:
            extras.append(rw)
    if os.environ.get("ENABLE_HYDE") == "1":
        hy = query_understanding.hypothetical_doc(question)
        if hy:
            extras.append(hy)
    return extras
```

Then in `_retrieve`, after the existing `q_dev`/`q_en` handling and before `query_intent = intent.classify_intent(...)`:

```python
    _extras = _extra_query_strings(question)
    for _e in _extras:
        scores = np.maximum(scores, sub_emb @ _embed_query(_e))
```

And extend the BM25 extras list to include them:

```python
    _bm25_extras = [q for q in ([q_dev, q_en] + _extras) if q]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tools/tests/test_query_understanding_wiring.py tools/tests/test_work_scoped_qa.py -q`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add tools/server.py tools/tests/test_query_understanding_wiring.py
git commit -m "retrieval: fold query rewrite + HyDE into dense+BM25 (ENABLE_QUERY_REWRITE/HYDE)"
```

---

### Task 8: Extend the eval harness — rerank path, junk metric, entity gold cases

**Files:**
- Modify: `tools/eval_retrieval.py` (add `--rerank`/`--junk` flags mirroring the server; add gold cases; add a junk-in-top-k counter).
- Test: run the harness (this task's deliverable is the measurement, validated by its own output).

**Interfaces:**
- Consumes: `retrieve.apply_quality_weights` (Task 3), `reranker.get_reranker` (Task 4), `chunk_quality.is_junk` (Task 1).

- [ ] **Step 1: Add entity/doctrinal gold cases**

Append to the `GOLD` list in `tools/eval_retrieval.py` (bare Carlyle + Bhakti, so the harness measures the exact failures this plan targets):

```python
    (
        "कारलाईल कॉटेज",
        ["charitra-tatvajnan-tulpule", "guru-ha-parabrahma-kewal"],
        "BARE entity: Carlyle Cottage (2-word) -> a biography with cottage content",
    ),
    (
        "What are Gurudev's views on Bhakti?",
        ["pathway-to-god-in-kannada-literature", "pathway-to-god-in-hindi-literature",
         "gurudev-paramarthik-shikvan", "kakanchi-pravachane", "bhagavadgita-as-pathway-to-god-realization"],
        "DOCTRINAL: Bhakti -> a canonical/pravachan work",
    ),
```

- [ ] **Step 2: Add `--junk` and `--rerank` flags to the harness**

In `main()` argparse add:

```python
    p.add_argument("--junk", action="store_true", help="Apply quality-weight downranking")
    p.add_argument("--rerank", action="store_true", help="Cross-encoder rerank the candidate pool")
```

In `run_retrieval(...)`, after `fused = retrieve.fused_candidate_scores(...)`:

```python
    if junk:
        fused = retrieve.apply_quality_weights(fused, metas, enabled=True)
```

and gate the final ranking on `rerank` (mirror Task 5's widen→dedup→cross-encoder, using `reranker.get_reranker()` and `retrieve.load_chunk_text`). Thread `junk`/`rerank` from args into `run_retrieval`.

- [ ] **Step 3: Add a junk-in-top-k counter to the summary**

After collecting `results` per query, count how many returned chunks are junk and accumulate:

```python
        junk_in_topk = sum(1 for r in results if chunk_quality.is_junk(
            retrieve.load_chunk_text(r_meta, r_idx)))  # r_meta/r_idx captured in run_retrieval
```
Print total junk-in-top-k across the gold set in the summary line. (Extend `run_retrieval` to return the chunk index/meta so the caller can load text; or compute the flag inside `run_retrieval` and return it per result.)

- [ ] **Step 4: Run the harness in all four modes and record the numbers**

```bash
python tools/eval_retrieval.py --top-k 8                       # baseline
python tools/eval_retrieval.py --top-k 8 --junk                # + junk downweight
python tools/eval_retrieval.py --top-k 8 --junk --rerank       # + rerank (downloads model 1st run)
```
Expected: PASS count is `>=` baseline in every mode (zero regressions); junk-in-top-k strictly decreases with `--junk`; the BARE-Carlyle gold case flips to PASS with `--rerank`.

- [ ] **Step 5: Commit**

```bash
git add tools/eval_retrieval.py
git commit -m "eval: rerank/junk modes, junk-in-top-k metric, entity+doctrinal gold cases"
```

---

## Final validation (whole plan)

- [ ] Run the full retrieval test suite:
  `python -m pytest tools/tests/test_chunk_quality.py tools/tests/test_build_chunk_quality.py tools/tests/test_junk_downweight.py tools/tests/test_reranker.py tools/tests/test_retrieve_rerank_wiring.py tools/tests/test_query_understanding.py tools/tests/test_query_understanding_wiring.py tools/tests/test_hybrid_retrieval.py -q`
  Expected: all PASS.
- [ ] `python tools/eval_retrieval.py --top-k 8 --junk --rerank` — record PASS count and junk-in-top-k; confirm zero regressions and the BARE-Carlyle case now PASSes.
- [ ] Restart the server with the validated flags enabled:
  `ENABLE_JUNK_WEIGHT=1 ENABLE_RERANK=1 ENABLE_QUERY_REWRITE=1 ENABLE_HYDE=1 ...` and spot-check the bare Carlyle query live.

## Notes for the implementer

- `chunks_meta.jsonl` and `chunks.jsonl` live under `04_processed/` and are gitignored — commit only the scripts; the build (Task 2) regenerates the data locally.
- The reranker's first load downloads ~2.3 GB; on Apple Silicon FlagEmbedding uses MPS/CPU. If load is slow in CI, the injected-`scorer` tests keep the suite model-free.
- Grounding (Citations API + enforcement + verifier) is deliberately NOT here — it is Phase 1B, a separate plan on the synthesis path.
