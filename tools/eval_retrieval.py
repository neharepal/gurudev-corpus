#!/usr/bin/env python3
"""
Offline retrieval eval harness — Phase 1 quality check.

Runs a gold set of queries against the real retrieval ranking using
locally-cached BGE-M3 embeddings.  No server, no LLM API calls.

Usage:
    python3 tools/eval_retrieval.py
    python3 tools/eval_retrieval.py --top-k 10 --verbose

Exit code: 0 always (non-blocking for CI); caller checks PASS/FAIL counts.

Notes on translation in this harness:
  - EN→MR and MR→EN translation (query_translation module) require Haiku
    and are disabled here (use_llm=False) to comply with the no-paid-API
    constraint.  The MR query tests therefore exercise bge-m3's native
    cross-lingual matching, which is the pre-fix baseline.  The full
    bidirectional benefit (translate_to_english) is only active in the live
    server.  A FAIL on a MR query in this harness does NOT mean the
    bidirectional fix is broken — it means the cross-lingual baseline alone
    is insufficient and the translation path is needed in production.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Path setup — make tools/ importable
# ---------------------------------------------------------------------------
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import retrieve  # noqa: E402
import intent   # noqa: E402
import query_translation  # noqa: E402
import chunk_quality  # noqa: E402
import reranker as reranker_mod  # noqa: E402
import server as server_mod  # noqa: E402  # RFC-017 small-to-big helper + parents loader

# ---------------------------------------------------------------------------
# Gold set
# Each entry: (query, [expected_work_id, ...], description)
# "expected" = at least one of these work_ids must appear in top_k.
# ---------------------------------------------------------------------------
GOLD = [
    # EN: flagship "One God One World One Humanity" query
    (
        "What are Gurudev's views on 'One God, One World, One Humanity'?",
        ["gandhi-and-other-indian-saints", "pathway-to-god-in-the-vedas"],
        "EN: One God One World One Humanity → gandhi or pathway-to-god-in-the-vedas",
    ),
    # MR: same concept in Devanagari — tests cross-lingual retrieval of EN works
    # (full bidirectional fix adds translate_to_english; baseline = bge-m3 only)
    (
        "एक ईश्वर, एक विश्व, एक मानवता याविषयी गुरुदेव काय म्हणतात?",
        ["gandhi-and-other-indian-saints", "pathway-to-god-in-the-vedas"],
        "MR: same concept (Devanagari) → same EN works [cross-lingual baseline; "
        "translate_to_english needed for full fix]",
    ),
    # EN: bhakti / devotion — Gurudev's own works
    (
        "What does Gurudev say about bhakti and devotion to God?",
        [
            "pathway-to-god-in-kannada-literature",
            "pathway-to-god-in-hindi-literature",
            "hindu-mysticism",
            "mysticism-in-maharashtra",
            "bhagavadgita-as-pathway-to-god-realization",
            "pathway-to-god-in-the-vedas",
            "constructive-survey-of-upanishadic-philosophy",
        ],
        "EN: bhakti / devotion → a Pathway-to-God or mysticism work",
    ),
    # EN: sadhana / spiritual practice
    (
        "What are the stages of sadhana in Gurudev's teaching?",
        [
            "constructive-survey-of-upanishadic-philosophy",
            "pathway-to-god-in-kannada-literature",
            "pathway-to-god-in-hindi-literature",
            "gurudev-paramarthik-shikvan",
            "sadhakbodh",
            "parmartha-sopan",
        ],
        "EN: stages of sadhana → a canonical or Kaka-authored work",
    ),
    # MR: साधना (sadhana) in Devanagari → should find Marathi canonical works
    (
        "साधनेचे टप्पे कोणते? गुरुदेव काय सांगतात?",
        [
            "parmartha-sopan",
            "parmartha-mandir",
            "gurudev-paramarthik-shikvan",
            "sadhakbodh",
            "kakanchi-pravachane",
            "charitra-tatvajnan-tulpule",
        ],
        "MR: stages of sadhana (Devanagari) → Marathi canonical/biography work",
    ),
    # EN: Nimbargi lineage / sampradaya background
    (
        "Who was Nimbargi Maharaj and what is the Inchgeri sampradaya?",
        [
            "bodhsudha",
            "sonari-pane-2000",
            "ranade-and-his-spiritual-lineage",
            "nimbargi-maharaj-charitra-athavani-mr",
            "acpr-silver-jubilee-vol1",
            "acpr-silver-jubilee-vol2",
        ],
        "EN: Nimbargi Maharaj / Inchgeri lineage → a lineage/biography work",
    ),
    # EN: Upanishads / Vedanta — navigates to Gurudev's scholarly works
    (
        "Gurudev's interpretation of the Upanishads",
        [
            "constructive-survey-of-upanishadic-philosophy",
            "vedant",
            "creative-period",
            "contemporary-indian-philosophy",
        ],
        "EN: Upanishads interpretation → Constructive Survey or Vedanta work",
    ),
    # MR: आत्मज्ञान (self-knowledge) — Devanagari test against Marathi works
    (
        "आत्मज्ञानाविषयी गुरुदेव रानडे यांचे विचार काय आहेत?",
        [
            "parmartha-mandir",
            "parmartha-sopan",
            "charitra-tatvajnan-tulpule",
            "gurudev-paramarthik-shikvan",
            "kakanchi-pravachane",
        ],
        "MR: self-knowledge (आत्मज्ञान) → Marathi canonical or biography work",
    ),
    # -----------------------------------------------------------------------
    # GAP 1 cases: entity/place queries with Marathi inflection
    # BM25 suffix-stripping fix: "भुवनातील" → stem "भुवन", "आश्रमातील" → "आश्रम"
    # -----------------------------------------------------------------------
    # (a) Entity/place query — Adhyatma Bhuvan incidents
    # "भुवनातील" → stem "भुवन" → BM25 hits guru-ha-parabrahma-kewal (12 chunks
    #   with both अध्यात्म+भुवन) and charitra-tatvajnan-tulpule (10 chunks).
    # "घटना" (incidents) is an uninflected exact match in those biography works.
    # In offline eval: BM25 fix alone should surface at least one biography.
    (
        "अध्यात्म भुवनातील सर्व घटना",
        [
            "guru-ha-parabrahma-kewal",
            "charitra-tatvajnan-tulpule",
            "shri-gurudevanchya-athvani-pustak",
            "punyasmruti",
            "पुण्यस्मृती",
            "jivandarshan-deshpande",
        ],
        "GAP1-a MR entity: Adhyatma Bhuvan incidents (inflected भुवनातील) → biography/athvani",
    ),
    # (b) Common-word entity query — Inchgeri ashram (place name)
    # "इंचगेरी" is an exact match (no inflection); "आश्रमातील" → stem "आश्रम".
    # javak-patre-tipane (130 chunks), guru-ha-parabrahma-kewal (86 chunks),
    # charitra-tatvajnan-tulpule (67 chunks) all mention इंचगेरी.
    (
        "इंचगेरी आश्रमातील संत आणि भक्त",
        [
            "guru-ha-parabrahma-kewal",
            "charitra-tatvajnan-tulpule",
            "sonari-pane-2000",
            "nimbargi-maharaj-charitra-athavani-mr",
            "javak-patre-tipane",
            "jivandarshan-deshpande",
        ],
        "GAP1-b MR entity: Inchgeri ashram (place name + inflected आश्रमातील) → biography/athvani",
    ),
    # -----------------------------------------------------------------------
    # GAP 2 case: English query whose answer is Marathi athvani/biography
    # In OFFLINE eval (use_llm=False): translation is skipped; this tests
    # bge-m3's native cross-lingual ability alone.  A FAIL here does NOT mean
    # the GAP 2 fix is broken — the server-side EN→MR translation + cross-
    # lingual BM25 (bm25_queries fix) carry it in production.
    # -----------------------------------------------------------------------
    (
        "What incidents happened with Gurudev Ranade at the Inchgeri ashram?",
        [
            "guru-ha-parabrahma-kewal",
            "charitra-tatvajnan-tulpule",
            "shri-gurudevanchya-athvani-pustak",
            "jivandarshan-deshpande",
            "nimbargi-maharaj-charitra-athavani-mr",
            "ranade-and-his-spiritual-lineage",
            "acpr-silver-jubilee-vol1",
        ],
        "GAP2 EN→MR-athvani: incidents at Inchgeri → Marathi biography/athvani "
        "[cross-lingual baseline; EN→MR translation + BM25 fix needed for full recall]",
    ),
    # -----------------------------------------------------------------------
    # GAP 3 case: verbose entity query whose distinctive term is diluted by
    # generic Marathi question/meta filler words (बद्दल, या, काय, माहिती, मिळेल).
    # charitra-tatvajnan-tulpule holds the most Carlyle Cottage chunks (15) but
    # the filler words dilute the distinctive "कॉटेज" BM25 signal.  The BM25
    # stopword extension drops the filler so कार्लाईल/कॉटेज + the book-title
    # words (चरित्र/तत्वज्ञान) dominate.  Content words (चरित्र, तत्वज्ञान) are
    # deliberately NOT stopwords — here they are the target book's title.
    (
        "कार्लाईल कॉटेज बद्दल चरित्र आणि तत्वज्ञान या ग्रंथातून काय माहिती मिळेल",
        [
            # Only charitra: guru-ha-parabrahma-kewal always surfaces and would
            # mask the real target.  The dilution bug is that charitra (which
            # holds the most Carlyle chunks) drops out.
            "charitra-tatvajnan-tulpule",
        ],
        "GAP3 MR verbose-entity: Carlyle Cottage (filler-diluted) → charitra-tatvajnan-tulpule",
    ),
    # -----------------------------------------------------------------------
    # New entity/doctrinal gold cases (Task 8)
    # -----------------------------------------------------------------------
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
    # -----------------------------------------------------------------------
    # RFC-017 Task 8 gold cases: small-to-big recall on a buried sentence.
    # The "lightning" incident sits as one sentence inside a big biography /
    # athvani section, so its whole-parent cosine is low and pre-Phase-2 it
    # never surfaces (the motivating miss ranked ~2300th). On the CHILD index
    # the sentence's own cosine ranks it directly; with ENABLE_SMALL_TO_BIG=1
    # the ranked child expands back to its parent for context. The optional
    # 4th field is a dict of options — `expected_text_substr` asserts the
    # surfaced result's text actually contains the specific sentence, not
    # just any chunk of the same work. Three phrasings of the same incident
    # exercise complementary retrieval paths (specific-room MR phrasing hits
    # `devotee`/nimbargi bio; house-level EN/MR hit charitra/guru-ha/etc.).
    # -----------------------------------------------------------------------
    (
        "निंबाळला महाराजांच्या राहत्या खोलीजवळ वीज पडली होती का?",
        ["devotee", "nimbargi-maharaj-charitra-athavani-mr"],
        "PHASE2 buried-sentence: lightning struck near Maharaj's room (one line in a big athvani section)",
    ),
    (
        "the incident when lightning struck Gurudev's house",
        ["charitra-tatvajnan-tulpule", "guru-ha-parabrahma-kewal",
         "punyasmruti", "पुण्यस्मृती", "shri-gurudevanchya-athvani-pustak",
         "jivandarshan-deshpande"],
        "RFC-017 recall EN: lightning at Gurudev's house -> biography w/ वीज पडली",
        {"expected_text_substr": "वीज"},
    ),
    (
        "गुरुदेवांच्या घरावर वीज पडली त्या घटनेबद्दल सांगा",
        ["charitra-tatvajnan-tulpule", "guru-ha-parabrahma-kewal",
         "punyasmruti", "पुण्यस्मृती", "shri-gurudevanchya-athvani-pustak",
         "jivandarshan-deshpande"],
        "RFC-017 recall MR: lightning at Gurudev's house (Devanagari) -> biography",
        {"expected_text_substr": "वीज"},
    ),
]


def _rerank_candidates(query, candidates, reranker_obj, *, top_k):
    """Reorder [(idx, text), ...] by cross-encoder relevance; keep top_k.

    Fail-safe: if reranker is unavailable or returns wrong count, keep MMR order.
    Mirrors server._rerank_candidates.
    """
    if not reranker_obj.available() or not candidates:
        return candidates[:top_k]
    texts = [t for _, t in candidates]
    scores = reranker_obj.rerank(query, texts)
    if len(scores) != len(candidates):
        return candidates[:top_k]
    order = sorted(range(len(candidates)), key=lambda i: scores[i], reverse=True)
    return [candidates[i] for i in order[:top_k]]


def run_retrieval(
    query: str,
    *,
    embeddings: np.ndarray,
    metas: list,
    model_name: str,
    top_k: int,
    candidates: int,
    junk: bool = False,
    rerank: bool = False,
    small_to_big: bool = False,
    parents_by_id: dict | None = None,
) -> list[dict]:
    """Run the full retrieval pipeline (mirrors server._retrieve, no LLM calls).

    When junk=True, applies quality-weight downranking (mirrors ENABLE_JUNK_WEIGHT).
    When rerank=True, applies widen→MMR-dedup→cross-encoder rerank (mirrors ENABLE_RERANK).
    When small_to_big=True, ranked children are grouped into distinct parents
    (RFC-017 Task 6): each result's `chunk_text` is the PARENT section (the
    context the answer model would read) and `cite_text` is the top matched
    child's citable span. work_id / title / author come from the parent.
    Each result dict includes a 'chunk_text' key for junk-in-top-k counting.
    """
    qvec = retrieve.embed_query(query, model_name)
    scores = embeddings @ qvec

    # Translation: use_llm=False — no Haiku calls in offline eval.
    # EN→MR translation is skipped; cross-lingual bge-m3 provides baseline.
    # MR→EN translation is skipped; the server uses it at use_llm=True.

    # Intent classification: heuristic only, no LLM fallback.
    query_intent = intent.classify_intent(query, use_llm_fallback=False)
    scores = retrieve.apply_intent_tier_weights(scores, metas, query_intent)

    cand_n = min(candidates, len(scores))
    fused = retrieve.fused_candidate_scores(query, scores, metas)

    # Apply quality-weight downranking when --junk is active.
    if junk:
        fused = retrieve.apply_quality_weights(fused, metas, enabled=True)

    cand_idx = np.argpartition(-fused, cand_n - 1)[:cand_n]
    cand_idx = cand_idx[np.argsort(-fused[cand_idx])]
    cand_scores = fused[cand_idx]

    if rerank:
        # Mirror server._retrieve rerank path:
        # widen to candidates, MMR-dedup pre-pass (generous cap), then cross-encoder.
        widen = min(retrieve.INITIAL_CANDIDATES, len(cand_idx))
        pool = cand_idx[:widen]
        deduped = retrieve.mmr_rerank(
            qvec, pool, fused[pool], embeddings, metas,
            top_k=len(pool),
            mmr_lambda=retrieve.MMR_LAMBDA,
            max_per_source=2,
        )
        cand_pairs = [(int(idx), retrieve.load_chunk_text(metas[idx], int(idx)))
                      for idx, _mmr in deduped]
        top = _rerank_candidates(query, cand_pairs, reranker_mod.get_reranker(), top_k=top_k)
        reranked = [(idx, 0.0) for idx, _txt in top]
    else:
        reranked = retrieve.mmr_rerank(
            qvec, cand_idx, cand_scores, embeddings, metas,
            top_k=top_k,
            mmr_lambda=retrieve.MMR_LAMBDA,
            max_per_source=2,
        )

    if small_to_big and parents_by_id:
        rows = server_mod.small_to_big_results(
            reranked, metas, keep_idx=None, parents_by_id=parents_by_id,
            dense_scores=scores, max_per_parent=2, top_k=top_k,
        )
        return [{
            "work_id": r["meta"].get("work_id", ""),
            "title": r["meta"].get("title", ""),
            "author": r["meta"].get("author", ""),
            "cos_score": r["cos_score"],
            "mmr_score": r["mmr_score"],
            "lang": r["meta"].get("language", "?"),
            "chunk_text": r["text"],                    # parent (context)
            "cite_text": r["meta"].get("cite_text", ""),  # top child's citable span
            "retrieval_only": bool(r["meta"].get("retrieval_only")),
        } for r in rows]

    results = []
    for idx, mmr_score in reranked:
        meta = metas[idx]
        chunk_text = retrieve.load_chunk_text(meta, int(idx))
        results.append({
            "work_id": meta.get("work_id", ""),
            "title": meta.get("title", ""),
            "author": meta.get("author", ""),
            "cos_score": float(scores[idx]),
            "mmr_score": float(mmr_score),
            "lang": meta.get("language", "?"),
            "chunk_text": chunk_text,
            "cite_text": meta.get("cite_text", ""),
        })
    return results


def main() -> int:
    p = argparse.ArgumentParser(description="Offline retrieval eval harness")
    p.add_argument("--top-k", type=int, default=8, help="Results per query (default 8)")
    p.add_argument("--candidates", type=int, default=retrieve.INITIAL_CANDIDATES,
                   help="Initial candidate pool (default from retrieve.INITIAL_CANDIDATES)")
    p.add_argument("--verbose", "-v", action="store_true", help="Show all top-k results per query")
    p.add_argument("--junk", action="store_true", help="Apply quality-weight downranking")
    p.add_argument("--rerank", action="store_true", help="Cross-encoder rerank the candidate pool")
    p.add_argument("--small-to-big", action="store_true",
                   help="RFC-017: group ranked children into distinct parents (loads parents.jsonl)")
    args = p.parse_args()

    flags = []
    if args.junk:
        flags.append("junk-downweight")
    if args.rerank:
        flags.append("cross-encoder-rerank")
    if args.small_to_big:
        flags.append("small-to-big")
    flag_str = " + ".join(flags) if flags else "baseline"

    print("=" * 72)
    print(f"Retrieval eval harness  (top_k={args.top_k}, candidates={args.candidates}, mode={flag_str})")
    print("No LLM calls — bge-m3 cross-lingual baseline only.")
    print("=" * 72)

    # Load corpus once
    t0 = time.time()
    try:
        embeddings, metas, manifest = retrieve.load_corpus()
    except SystemExit:
        print("ERROR: embeddings not found. Run tools/embedder.py first.", file=sys.stderr)
        return 1
    model_name = manifest.get("model", "BAAI/bge-m3")
    print(
        f"Corpus: {embeddings.shape[0]:,} chunks × {embeddings.shape[1]}-dim  "
        f"model={model_name}  loaded in {time.time() - t0:.1f}s\n"
    )

    # Warm the sentence-transformer model (first encode is slow)
    print("Warming embedder...", end=" ", flush=True)
    t0 = time.time()
    retrieve.embed_query("warmup", model_name)
    print(f"done ({time.time() - t0:.1f}s)\n")

    parents_by_id: dict | None = None
    if args.small_to_big:
        t0 = time.time()
        parents_by_id = server_mod._load_parents_by_id()
        if not parents_by_id:
            print("ERROR: --small-to-big requires 04_processed/parents.jsonl (found empty).",
                  file=sys.stderr)
            return 1
        print(f"Parents: {len(parents_by_id):,} loaded in {time.time() - t0:.1f}s\n")

    n_pass = 0
    n_fail = 0
    total_junk_in_topk = 0

    for gold_entry in GOLD:
        # Gold entries are 3-tuples; RFC-017 gold cases add an optional 4th dict
        # of assertions (e.g. `expected_text_substr`).
        opts: dict = {}
        if len(gold_entry) == 4:
            query, expected_ids, description, opts = gold_entry
        else:
            query, expected_ids, description = gold_entry
        t0 = time.time()
        results = run_retrieval(
            query,
            embeddings=embeddings,
            metas=metas,
            model_name=model_name,
            top_k=args.top_k,
            candidates=args.candidates,
            junk=args.junk,
            rerank=args.rerank,
            small_to_big=args.small_to_big,
            parents_by_id=parents_by_id,
        )
        elapsed = time.time() - t0

        returned_work_ids = [r["work_id"] for r in results]
        hit = any(wid in returned_work_ids for wid in expected_ids)

        # Optional stricter check: the surfaced chunk_text must contain a
        # specific substring (verifies the specific sentence/verse surfaced,
        # not just any chunk from the same work).
        expected_substr = opts.get("expected_text_substr")
        substr_hit = True
        if expected_substr:
            substr_hit = any(
                (wid in expected_ids) and (expected_substr in (r.get("chunk_text") or ""))
                for wid, r in zip(returned_work_ids, results)
            )

        status = "PASS" if (hit and substr_hit) else "FAIL"
        if status == "PASS":
            n_pass += 1
        else:
            n_fail += 1

        # Count junk chunks in this query's top-k.
        junk_count = sum(1 for r in results if chunk_quality.is_junk(r["chunk_text"]))
        total_junk_in_topk += junk_count

        print(f"[{status}]  {description}")
        print(f"       Query   : {query[:90]}")
        print(f"       Expected: {expected_ids}")
        print(f"       Got     : {returned_work_ids}  ({elapsed:.2f}s)  junk_in_top_k={junk_count}")
        if expected_substr:
            marker = "OK" if substr_hit else "MISSING"
            print(f"       Substr  : {expected_substr!r} in top-k → {marker}")

        if args.verbose:
            for rank, r in enumerate(results, 1):
                is_junk_flag = chunk_quality.is_junk(r["chunk_text"])
                extra = ""
                if args.small_to_big:
                    ct = (r.get("cite_text") or "").replace("\n"," ")[:60]
                    if r.get("retrieval_only"):
                        extra = "  [retrieval-only]"
                    elif ct:
                        extra = f"  cite={ct!r}"
                print(
                    f"         #{rank:2d}  cos={r['cos_score']:.4f}  mmr={r['mmr_score']:.4f}"
                    f"  [{r['lang']}]  {r['work_id']}  ({r['title'][:50]})"
                    f"{'  [JUNK]' if is_junk_flag else ''}{extra}"
                )
        print()

    print("=" * 72)
    print(f"Results: {n_pass} PASS / {n_fail} FAIL out of {n_pass + n_fail} queries")
    print(f"Junk-in-top-k (total across gold set): {total_junk_in_topk}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
