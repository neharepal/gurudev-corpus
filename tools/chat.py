#!/usr/bin/env python3
"""
End-to-end chat CLI for the Gurudev Corpus.

Usage:
    python3 tools/chat.py "What are Gurudev's views on Bhakti?"
    python3 tools/chat.py --mode pravachan "Adhyay 12 of the Geeta and Gurudev's life"
    python3 tools/chat.py --mode reading --work pathway-to-god-in-hindi-literature \\
        --passage-text "..." "what does intuitive apprehension mean?"

Wires together:
  1. retrieve.py — embed the question, MMR-rerank, return top-K chunks with metadata
  2. prompts.py  — pick mode-specific system prompt and format the user message
  3. llm_client.py — call Anthropic API with prompt caching

Per ADR-007 (quote-first) and ADR-008 (retrieval-side dedup), the heavy lifting
is in the system prompts and the retrieval rerank — this CLI just plumbs them.

Requires ANTHROPIC_API_KEY in env (per ADR-003).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent

# Make sibling modules importable when run as a script.
sys.path.insert(0, str(REPO / "tools"))

import numpy as np

from prompts import (
    _passage_label,
    build_pravachan_user_message,
    build_reading_user_message,
    build_user_message,
    get_system_prompt,
)
from llm_client import (
    ChatClient,
    MissingApiKeyError,
    cache_stats,
    pick_model,
)
from render import render_markdown
import intent
import retrieve  # imports load_corpus, embed_query, mmr_rerank, load_chunk_text


def run_retrieval(
    question: str,
    *,
    top_k: int,
    candidates: int,
    mmr_lambda: float,
    max_per_source: int,
    metadata_filter: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], float]:
    """Embed question, retrieve + rerank, attach chunk text. Return (chunks, elapsed_seconds)."""
    t0 = time.time()
    embeddings, metas, manifest = retrieve.load_corpus()

    # Optional metadata filter (e.g., restrict to current work in reading mode).
    if metadata_filter:
        mask = np.ones(len(metas), dtype=bool)
        for k, v in metadata_filter.items():
            mask &= np.array(
                [m.get(k) == v for m in metas], dtype=bool
            )
        if not mask.any():
            return [], time.time() - t0
        keep_idx = np.where(mask)[0]
        embeddings = embeddings[keep_idx]
        metas = [metas[i] for i in keep_idx]
    else:
        keep_idx = None

    subset_texts = (
        [retrieve.load_chunk_text(metas[i], int(keep_idx[i])) for i in range(len(metas))]
        if keep_idx is not None
        else None
    )

    model_name = manifest.get("model", "BAAI/bge-m3")
    qvec = retrieve.embed_query(question, model_name)
    scores = embeddings @ qvec
    query_intent = intent.classify_intent(question)
    scores = retrieve.apply_intent_tier_weights(scores, metas, query_intent)

    cand_n = min(candidates, len(scores))
    fused = retrieve.fused_candidate_scores(question, scores, metas, texts=subset_texts)
    cand_idx = np.argpartition(-fused, cand_n - 1)[:cand_n]
    cand_idx = cand_idx[np.argsort(-fused[cand_idx])]
    cand_scores = fused[cand_idx]  # MMR ranks on fused (dense+lexical), not raw dense

    reranked = retrieve.mmr_rerank(
        qvec, cand_idx, cand_scores, embeddings, metas,
        top_k=top_k,
        mmr_lambda=mmr_lambda,
        max_per_source=max_per_source,
    )

    # Reassemble chunks with their text loaded from chunks.jsonl.
    # When a metadata filter is applied, idx refers to the filtered subset;
    # translate back to the original corpus row to fetch text.
    chunks: list[dict[str, Any]] = []
    for idx, mmr_score in reranked:
        meta = metas[idx]
        original_idx = int(keep_idx[idx]) if keep_idx is not None else int(idx)
        text = retrieve.load_chunk_text(meta, original_idx)
        chunks.append({
            "meta": meta,
            "text": text,
            "cos_score": float(scores[idx]),
            "mmr_score": float(mmr_score),
        })
    return chunks, time.time() - t0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Chat CLI for the Gurudev Corpus (Q&A / Pravachan / Reading)."
    )
    p.add_argument("question", help="The question, topic, or inline reading question.")
    p.add_argument(
        "--mode",
        choices=["qa", "pravachan", "reading"],
        default="qa",
        help="Mode: qa (default), pravachan, or reading.",
    )
    p.add_argument(
        "--top-k", type=int, default=None,
        help="Final result count after rerank. Default: 8 (qa), 15 (pravachan), 5 (reading).",
    )
    p.add_argument(
        "--candidates", type=int, default=30,
        help="Initial pool size before MMR rerank.",
    )
    p.add_argument(
        "--mmr-lambda", type=float, default=0.7,
        help="MMR balance (1.0=pure relevance, 0.0=pure diversity).",
    )
    p.add_argument(
        "--max-per-source", type=int, default=2,
        help="Per-source cap (per ADR-008).",
    )

    # Reading-mode extras.
    p.add_argument(
        "--work", default=None,
        help="Reading mode: restrict retrieval to this work_id.",
    )
    p.add_argument(
        "--passage-text", default=None,
        help="Reading mode: the current passage the devotee is reading.",
    )
    p.add_argument(
        "--passage-title", default=None,
        help="Reading mode: a human-readable work title.",
    )

    # Output options.
    p.add_argument(
        "--show-chunks", action="store_true",
        help="Print retrieved chunks (with metadata + text) before the answer.",
    )
    p.add_argument(
        "--json", action="store_true",
        help="Emit a machine-readable JSON envelope instead of plain text.",
    )

    args = p.parse_args()

    if args.top_k is None:
        args.top_k = {"qa": 8, "pravachan": 15, "reading": 5}[args.mode]

    # Build retrieval filter (reading mode: scope to the current work).
    metadata_filter: dict[str, Any] | None = None
    if args.mode == "reading" and args.work:
        metadata_filter = {"work_id": args.work}

    # When retrieval is scoped to a single work, the per-source cap defeats
    # itself — every candidate is from the same work, so the cap fires after
    # `max_per_source` chunks. Effectively disable it in that case.
    effective_max_per_source = args.max_per_source
    if metadata_filter and "work_id" in metadata_filter:
        effective_max_per_source = args.top_k

    # Retrieve.
    print(f"\n[retrieval] mode={args.mode} top-k={args.top_k}", file=sys.stderr)
    try:
        chunks, retrieval_elapsed = run_retrieval(
            args.question,
            top_k=args.top_k,
            candidates=args.candidates,
            mmr_lambda=args.mmr_lambda,
            max_per_source=effective_max_per_source,
            metadata_filter=metadata_filter,
        )
    except SystemExit:
        # retrieve.load_corpus calls sys.exit(2) when embeddings aren't built.
        raise

    print(f"[retrieval] {len(chunks)} chunks in {retrieval_elapsed:.1f}s", file=sys.stderr)

    if args.show_chunks:
        for i, c in enumerate(chunks, 1):
            m = c["meta"]
            print(
                f"\n--- chunk {i}  [{m.get('kind')} · {m.get('language')}]  "
                f"{m.get('title') or m.get('work_id')}  cos={c['cos_score']:.3f}",
                file=sys.stderr,
            )
            print((c["text"] or "")[:400] + ("..." if len(c["text"] or "") > 400 else ""),
                  file=sys.stderr)

    if not chunks:
        print(
            "\n[no chunks retrieved] The matcher did not surface anything for this "
            "question — corpus is genuinely silent on it, or the filter is too narrow.",
            file=sys.stderr,
        )
        if args.mode == "reading" and metadata_filter:
            print("    Try without --work to broaden the search.", file=sys.stderr)
        return 1

    # Build the user-turn message per mode.
    if args.mode == "pravachan":
        user_message = build_pravachan_user_message(chunks, args.question)
    elif args.mode == "reading":
        passage = args.passage_text or ""
        title = args.passage_title or (args.work or "(current passage)")
        user_message = build_reading_user_message(passage, chunks, args.question, title)
    else:
        user_message = build_user_message(chunks, args.question)

    system_prompt = get_system_prompt(args.mode)

    # Call the LLM.
    print(f"[llm] model={pick_model(args.mode)}  invoking…", file=sys.stderr)
    try:
        client = ChatClient()
    except MissingApiKeyError as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        return 2

    label_to_chunk = {_passage_label(i): c for i, c in enumerate(chunks)}
    t0 = time.time()
    parsed, response = client.ask_structured(
        mode=args.mode,
        system_prompt=system_prompt,
        user_message=user_message,
        label_to_chunk=label_to_chunk,
    )
    llm_elapsed = time.time() - t0

    answer = render_markdown(parsed)
    stats = cache_stats(response)

    print(
        f"[llm] done in {llm_elapsed:.1f}s  "
        f"input={stats['input']}  output={stats['output']}  "
        f"cache_read={stats['cache_read']}  cache_creation={stats['cache_creation']}",
        file=sys.stderr,
    )

    if args.json:
        envelope = {
            "mode": args.mode,
            "question": args.question,
            "model": pick_model(args.mode),
            "chunks_used": [
                {
                    "meta": {k: v for k, v in c["meta"].items() if k != "text"},
                    "cos_score": c["cos_score"],
                    "mmr_score": c["mmr_score"],
                }
                for c in chunks
            ],
            "answer_markdown": answer,
            "answer": parsed.model_dump(),
            "usage": stats,
            "elapsed_seconds": {
                "retrieval": round(retrieval_elapsed, 3),
                "llm": round(llm_elapsed, 3),
            },
        }
        print(json.dumps(envelope, ensure_ascii=False, indent=2))
    else:
        print(answer)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
