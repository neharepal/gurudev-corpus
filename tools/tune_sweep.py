#!/usr/bin/env python3
"""
Batch driver for retrieval/answer tuning runs.

Loads the embedding model + corpus once, runs N questions in sequence,
writes a per-question markdown report and one summary.md to
`tuning/runs/<timestamp>/`.

Usage:
    /Users/neharepal/opt/anaconda3/bin/python tools/tune_sweep.py

Add ANTHROPIC_API_KEY in env. Set TOKENIZERS_PARALLELISM=false to silence the
HuggingFace fork warning.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import numpy as np

import intent
import retrieve
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
from schemas import QAResponse


QUESTIONS: list[dict[str, Any]] = [
    {
        "mode": "qa",
        "lang": "en",
        "question": "What are Gurudev's views on bhakti?",
    },
    {
        "mode": "qa",
        "lang": "en",
        "question": "What information do you have about gurudev's 60 years of age?",
    },
    {
        "mode": "qa",
        "lang": "en",
        "question": "What is the Nimbargi Sampraday?",
    },
    {
        "mode": "reading",
        "lang": "en",
        "question": "I want to read the Pathway to God in Hindi Literature",
        "work": "pathway-to-god-in-hindi-literature",
    },
    {
        "mode": "qa",
        "lang": "mr",
        "question": "गुरुदेवांचे नामस्मरणाविषयी विचार काय आहेत?",
    },
    {
        "mode": "pravachan",
        "lang": "mr",
        "question": "गीतेच्या बाराव्या अध्यायाचा सार काय?",
    },
]


def load_model_once(model_name: str):
    from sentence_transformers import SentenceTransformer
    print(f"[load] embedding model: {model_name}", file=sys.stderr)
    t = time.time()
    m = SentenceTransformer(model_name, trust_remote_code=True)
    print(f"[load] model ready in {time.time() - t:.1f}s", file=sys.stderr)
    return m


def embed_with(model, query: str, model_name: str) -> np.ndarray:
    if "e5" in model_name.lower():
        query = "query: " + query
    vec = model.encode([query], normalize_embeddings=True, convert_to_numpy=True)
    return vec[0].astype(np.float32)


def retrieve_for(
    *,
    model,
    model_name: str,
    embeddings: np.ndarray,
    metas: list[dict],
    question: str,
    top_k: int,
    candidates: int,
    mmr_lambda: float,
    max_per_source: int,
    metadata_filter: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], float]:
    t0 = time.time()

    if metadata_filter:
        mask = np.ones(len(metas), dtype=bool)
        for k, v in metadata_filter.items():
            mask &= np.array([m.get(k) == v for m in metas], dtype=bool)
        if not mask.any():
            return [], time.time() - t0
        keep_idx = np.where(mask)[0]
        sub_emb = embeddings[keep_idx]
        sub_metas = [metas[i] for i in keep_idx]
    else:
        keep_idx = None
        sub_emb = embeddings
        sub_metas = metas

    qvec = embed_with(model, question, model_name)
    scores = sub_emb @ qvec
    # Heuristic-only here so sweeps stay deterministic and make no API calls.
    query_intent = intent.classify_intent(question, use_llm_fallback=False)
    scores = retrieve.apply_intent_tier_weights(scores, sub_metas, query_intent)

    cand_n = min(candidates, len(scores))
    cand_idx = np.argpartition(-scores, cand_n - 1)[:cand_n]
    cand_idx = cand_idx[np.argsort(-scores[cand_idx])]
    cand_scores = scores[cand_idx]

    reranked = retrieve.mmr_rerank(
        qvec, cand_idx, cand_scores, sub_emb, sub_metas,
        top_k=top_k,
        mmr_lambda=mmr_lambda,
        max_per_source=max_per_source,
    )

    chunks: list[dict[str, Any]] = []
    for idx, mmr_score in reranked:
        meta = sub_metas[idx]
        original_idx = int(keep_idx[idx]) if keep_idx is not None else int(idx)
        text = retrieve.load_chunk_text(meta, original_idx)
        chunks.append({
            "meta": meta,
            "text": text,
            "cos_score": float(scores[idx]),
            "mmr_score": float(mmr_score),
        })
    return chunks, time.time() - t0


def build_user_msg(mode: str, question: str, chunks: list[dict[str, Any]], work_title: str | None) -> str:
    if mode == "pravachan":
        return build_pravachan_user_message(chunks, question)
    if mode == "reading":
        return build_reading_user_message("", chunks, question, work_title or "(current passage)")
    return build_user_message(chunks, question)


def write_question_report(
    out_path: Path,
    q: dict,
    chunks: list[dict],
    answer: str,
    retrieval_s: float,
    llm_s: float,
    stats: dict,
    classification: str | None = None,
) -> dict:
    mode = q["mode"]
    lang = q["lang"]
    question = q["question"]
    cos_scores = [c["cos_score"] for c in chunks]
    kinds = [c["meta"].get("kind", "?") for c in chunks]
    bio_pct = (sum(1 for k in kinds if k == "biography") / max(len(kinds), 1)) * 100
    if classification is None:
        # Fall back to parsing the markdown for the audit line (legacy).
        for line in answer.splitlines():
            s = line.strip().lower()
            if "_classification:" in s:
                classification = s.split("_classification:")[-1].strip(" _\n*")
                break

    md = []
    md.append(f"# {q.get('label', question)}\n")
    md.append(f"- **Mode:** {mode}")
    md.append(f"- **Lang:** {lang}")
    md.append(f"- **Question:** {question}")
    if q.get("work"):
        md.append(f"- **Work scope:** `{q['work']}`")
    if q.get("expected"):
        md.append(f"- **Expected source:** {q['expected']}")
    md.append(f"- **Retrieval time:** {retrieval_s:.1f}s")
    md.append(f"- **LLM time:** {llm_s:.1f}s  ·  in={stats['input']}  out={stats['output']}  cache_read={stats['cache_read']}  cache_creation={stats['cache_creation']}")
    md.append(f"- **Classification (LLM-emitted):** {classification or '—'}")
    if cos_scores:
        md.append(f"- **Cosine range:** {min(cos_scores):.3f} – {max(cos_scores):.3f}  ·  biography in top-{len(chunks)}: {bio_pct:.0f}%")
    md.append("")
    md.append("## Retrieved chunks")
    md.append("")
    md.append("| # | kind | lang | work | cos | mmr |")
    md.append("|---|------|------|------|-----|-----|")
    for i, c in enumerate(chunks, 1):
        m = c["meta"]
        title = (m.get("title") or m.get("work_id") or "?").replace("|", "\\|")
        md.append(f"| {i} | {m.get('kind','?')} | {m.get('language','?')} | {title} | {c['cos_score']:.3f} | {c['mmr_score']:.3f} |")
    md.append("")
    for i, c in enumerate(chunks, 1):
        m = c["meta"]
        md.append(f"### chunk {i} — {m.get('title') or m.get('work_id')}  ({m.get('kind')} · {m.get('language')})")
        md.append("")
        md.append("```")
        text = (c["text"] or "")[:1000]
        if len(c["text"] or "") > 1000:
            text += "\n..."
        md.append(text)
        md.append("```")
        md.append("")
    md.append("## LLM answer")
    md.append("")
    md.append(answer)
    md.append("")
    out_path.write_text("\n".join(md), encoding="utf-8")
    return {
        "mode": mode,
        "lang": lang,
        "question": question,
        "classification": classification,
        "cos_min": min(cos_scores) if cos_scores else None,
        "cos_max": max(cos_scores) if cos_scores else None,
        "biography_pct": bio_pct,
        "retrieval_s": retrieval_s,
        "llm_s": llm_s,
        "input_tokens": stats["input"],
        "output_tokens": stats["output"],
        "cache_read": stats["cache_read"],
    }


def write_summary(out_path: Path, summaries: list[dict]) -> None:
    md = []
    md.append("# Sweep summary\n")
    md.append("| # | mode | lang | classif. | cos min–max | bio % | retr s | llm s | in/out tok |")
    md.append("|---|------|------|----------|-------------|-------|--------|-------|------------|")
    for i, s in enumerate(summaries, 1):
        cos_range = f"{s['cos_min']:.3f}–{s['cos_max']:.3f}" if s["cos_min"] is not None else "—"
        md.append(
            f"| {i} | {s['mode']} | {s['lang']} | {s.get('classification') or '—'} | {cos_range} | "
            f"{s['biography_pct']:.0f}% | {s['retrieval_s']:.1f} | {s['llm_s']:.1f} | "
            f"{s['input_tokens']}/{s['output_tokens']} |"
        )
    md.append("")
    md.append("## Questions")
    md.append("")
    for i, s in enumerate(summaries, 1):
        md.append(f"{i}. ({s['mode']}·{s['lang']}) {s['question']}")
    md.append("")
    out_path.write_text("\n".join(md), encoding="utf-8")


def main() -> int:
    try:
        client = ChatClient()
    except MissingApiKeyError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    print("[load] corpus...", file=sys.stderr)
    embeddings, metas, manifest = retrieve.load_corpus()
    model_name = manifest.get("model", "BAAI/bge-m3")
    print(f"[load] {len(metas)} chunks, model={model_name}, dim={embeddings.shape[1]}", file=sys.stderr)

    model = load_model_once(model_name)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = REPO / "tuning" / "runs" / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[out] {out_dir.relative_to(REPO)}", file=sys.stderr)

    summaries: list[dict] = []
    for i, q in enumerate(QUESTIONS, 1):
        mode = q["mode"]
        top_k = {"qa": 8, "pravachan": 15, "reading": 5}[mode]
        metadata_filter = None
        if mode == "reading" and q.get("work"):
            metadata_filter = {"work_id": q["work"]}

        # Per-source cap is self-defeating when scoped to one work (reading).
        # Q&A caps at 1/work for citation breadth (matches server.py); pravachan keeps 2.
        if metadata_filter and "work_id" in metadata_filter:
            max_per_source = top_k
        elif mode == "qa":
            max_per_source = 1
        else:
            max_per_source = 2

        print(f"\n[q{i}/{len(QUESTIONS)}] ({mode}·{q['lang']}) {q['question'][:60]}...", file=sys.stderr)
        chunks, retrieval_s = retrieve_for(
            model=model,
            model_name=model_name,
            embeddings=embeddings,
            metas=metas,
            question=q["question"],
            top_k=top_k,
            candidates=30,
            mmr_lambda=0.7,
            max_per_source=max_per_source,
            metadata_filter=metadata_filter,
        )
        print(f"[q{i}] retrieval: {len(chunks)} chunks in {retrieval_s:.1f}s", file=sys.stderr)

        if not chunks:
            print(f"[q{i}] no chunks — skipping LLM", file=sys.stderr)
            continue

        user_msg = build_user_msg(mode, q["question"], chunks, q.get("work"))
        sys_prompt = get_system_prompt(mode)

        label_to_chunk = {_passage_label(j): c for j, c in enumerate(chunks)}
        t0 = time.time()
        parsed, response = client.ask_structured(
            mode=mode, system_prompt=sys_prompt, user_message=user_msg,
            label_to_chunk=label_to_chunk,
        )
        llm_s = time.time() - t0
        answer = render_markdown(parsed)
        stats = cache_stats(response)
        print(f"[q{i}] llm: {llm_s:.1f}s  model={pick_model(mode)}  in={stats['input']} out={stats['output']}  cache_read={stats['cache_read']}", file=sys.stderr)

        # Classification comes from the structured response when available
        # (QA only); reading and pravachan do not emit one.
        classification = parsed.classification if isinstance(parsed, QAResponse) else None
        report_path = out_dir / f"q{i}.md"
        s = write_question_report(
            report_path, q, chunks, answer, retrieval_s, llm_s, stats,
            classification=classification,
        )
        summaries.append(s)

    write_summary(out_dir / "summary.md", summaries)
    print(f"\n[done] reports in {out_dir.relative_to(REPO)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
