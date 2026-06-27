#!/usr/bin/env python3
"""Retrieval-only ranking probe (RFC-011).

Prints the intent-aware ranked chunks for a query WITHOUT calling the answer
LLM, so you can check citation *priority* (canonical vs souvenir, athvani vs
doctrine) at zero Anthropic API cost. Intent is computed heuristic-only here,
so this never makes a paid call.

Usage:
    /Users/neharepal/opt/anaconda3/bin/python tools/rank_probe.py "your question"
    /Users/neharepal/opt/anaconda3/bin/python tools/rank_probe.py "..." --top-k 10
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import numpy as np

import intent
import retrieve


def main() -> int:
    p = argparse.ArgumentParser(description="Hybrid retrieval ranking probe (no API).")
    p.add_argument("query", help="the question to rank citations for")
    p.add_argument("--top-k", type=int, default=8)
    p.add_argument("--candidates", type=int, default=30)
    p.add_argument("--mmr-lambda", type=float, default=0.7)
    p.add_argument("--max-per-source", type=int, default=1)
    p.add_argument("--no-hybrid", action="store_true",
                   help="Use dense-only candidate selection (pre-hybrid behaviour).")
    args = p.parse_args()

    embeddings, metas, manifest = retrieve.load_corpus()
    model_name = manifest.get("model", "BAAI/bge-m3")
    qvec = retrieve.embed_query(args.query, model_name)

    cos = embeddings @ qvec
    qintent = intent.classify_intent(args.query, use_llm_fallback=False)
    weighted = retrieve.apply_intent_tier_weights(cos, metas, qintent)

    if args.no_hybrid:
        selection_scores = weighted
        mode_label = "dense-only"
    else:
        selection_scores = retrieve.fused_candidate_scores(args.query, weighted, metas)
        mode_label = "hybrid (dense+BM25+RRF)"

    cand_n = min(args.candidates, len(selection_scores))
    cand_idx = np.argpartition(-selection_scores, cand_n - 1)[:cand_n]
    cand_idx = cand_idx[np.argsort(-selection_scores[cand_idx])]
    reranked = retrieve.mmr_rerank(
        qvec, cand_idx, selection_scores[cand_idx], embeddings, metas,
        top_k=args.top_k, mmr_lambda=args.mmr_lambda,
        max_per_source=args.max_per_source,
    )

    print(f"query  : {args.query}")
    print(f"intent : {qintent}  (heuristic-only — no API call)")
    print(f"mode   : {mode_label}\n")
    print(f"{'#':>2}  {'tier':<13} {'kind':<10} {'cos':>6} {'wt':>6}  work")
    print(f"{'--':>2}  {'-'*13} {'-'*10} {'-'*6} {'-'*6}  {'-'*40}")
    for rank, (idx, _mmr) in enumerate(reranked, 1):
        m = metas[idx]
        tier = retrieve.chunk_tier(m)
        work = (m.get("title") or m.get("work_id") or "?")[:48]
        print(f"{rank:>2}  {tier:<13} {m.get('kind','?'):<10} "
              f"{cos[idx]:6.3f} {weighted[idx]:6.3f}  {work}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
