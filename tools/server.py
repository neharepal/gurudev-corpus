#!/usr/bin/env python3
"""
FastAPI backend for Gurudev Sangrah.

Loads the BGE-M3 embedding model + corpus embeddings once at startup, then
handles POST /ask requests by:
  1. embedding the question,
  2. running MMR retrieval (per ADR-008, ADR-009),
  3. calling the Anthropic API via structured tool-use (per ADR-011), and
  4. returning the validated pydantic response as JSON.

Run:
    ANTHROPIC_API_KEY=... /Users/neharepal/opt/anaconda3/bin/python tools/server.py

Env vars:
    ANTHROPIC_API_KEY   required; per ADR-003 the v1 API key gate
    GURUDEV_BACKEND_PORT optional; default 8765

The chat-app Next.js route (`/api/ask`) calls this backend over HTTP; see
`tools/SERVER_README.md` for the dev workflow.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import intent
import retrieve
from llm_client import ChatClient, MissingApiKeyError, pick_model
from prompts import (
    _passage_label,
    build_pravachan_user_message,
    build_reading_user_message,
    build_user_message,
    get_system_prompt,
)
from streaming import sse, sse_heartbeat


PORT = int(os.environ.get("GURUDEV_BACKEND_PORT", "8765"))


# ---------------------------------------------------------------------------
# Request shape
# ---------------------------------------------------------------------------


class AskRequest(BaseModel):
    mode: str  # "qa" | "pravachan" | "reading"
    question: str
    lang: Optional[str] = None  # "en" | "mr"; informational, not used for routing
    # Reading-mode scoping.
    work: Optional[str] = None
    passage: Optional[str] = None
    passage_title: Optional[str] = None
    # Reserved for the threaded-follow-up refactor; not used by the single-turn
    # pipeline today. Included so the wire shape doesn't need to change later.
    history: Optional[List[Dict[str, Any]]] = None


# ---------------------------------------------------------------------------
# Lifespan state (loaded once at startup)
# ---------------------------------------------------------------------------


class _State:
    embeddings: np.ndarray
    metas: List[dict]
    manifest: Dict[str, Any]
    model: Any  # sentence_transformers.SentenceTransformer
    model_name: str
    client: ChatClient


STATE = _State()


def _embed_query(question: str) -> np.ndarray:
    """Match the embed convention from tune_sweep.embed_with()."""
    name = STATE.model_name
    q = question
    if "e5" in name.lower():
        q = "query: " + q
    vec = STATE.model.encode([q], normalize_embeddings=True, convert_to_numpy=True)
    return vec[0].astype(np.float32)


def _retrieve(
    question: str,
    *,
    top_k: int,
    candidates: int,
    mmr_lambda: float,
    max_per_source: int,
    metadata_filter: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    if metadata_filter:
        mask = np.ones(len(STATE.metas), dtype=bool)
        for k, v in metadata_filter.items():
            mask &= np.array([m.get(k) == v for m in STATE.metas], dtype=bool)
        if not mask.any():
            return []
        keep_idx = np.where(mask)[0]
        sub_emb = STATE.embeddings[keep_idx]
        sub_metas = [STATE.metas[i] for i in keep_idx]
    else:
        keep_idx = None
        sub_emb = STATE.embeddings
        sub_metas = STATE.metas

    qvec = _embed_query(question)
    scores = sub_emb @ qvec
    query_intent = intent.classify_intent(question)
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
    out: List[Dict[str, Any]] = []
    for idx, mmr_score in reranked:
        meta = sub_metas[idx]
        original_idx = int(keep_idx[idx]) if keep_idx is not None else int(idx)
        text = retrieve.load_chunk_text(meta, original_idx)
        out.append({
            "meta": meta,
            "text": text,
            "cos_score": float(scores[idx]),
            "mmr_score": float(mmr_score),
        })
    return out


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


app = FastAPI(title="Gurudev Sangrah backend", version="0.1.0")

# Allow the local Next.js dev server to call us cross-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _load_everything() -> None:
    # Fail fast if the API key is missing — the server has nothing to do without it.
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise MissingApiKeyError(
            "ANTHROPIC_API_KEY is not set. Per ADR-003, the chat backend uses "
            "the Anthropic API. Export ANTHROPIC_API_KEY before starting the server."
        )

    print("[startup] loading corpus...", file=sys.stderr)
    t = time.time()
    embeddings, metas, manifest = retrieve.load_corpus()
    STATE.embeddings = embeddings
    STATE.metas = metas
    STATE.manifest = manifest
    STATE.model_name = manifest.get("model", "BAAI/bge-m3")
    print(
        f"[startup] {len(metas)} chunks (dim={embeddings.shape[1]}) "
        f"in {time.time() - t:.1f}s",
        file=sys.stderr,
    )

    print(f"[startup] loading embedding model: {STATE.model_name}", file=sys.stderr)
    t = time.time()
    from sentence_transformers import SentenceTransformer
    STATE.model = SentenceTransformer(STATE.model_name, trust_remote_code=True)
    print(f"[startup] model ready in {time.time() - t:.1f}s", file=sys.stderr)

    # Warm-up embed: the first encode() call does lazy tokenizer/forward-pass
    # init that otherwise lands on the first real user query (~10s of cold
    # latency). Pay it here at startup instead.
    t = time.time()
    _embed_query("warm up the embedding model")
    print(f"[startup] embed warm-up in {time.time() - t:.1f}s", file=sys.stderr)

    STATE.client = ChatClient()
    print("[startup] ready", file=sys.stderr)


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "model": STATE.model_name,
        "chunks": len(STATE.metas),
    }


def _prepare_request(req: AskRequest):
    """Validate the request and run retrieval. Returns (mode, user_msg, system_prompt,
    chunks, mode_retrieval_meta) or raises HTTPException."""
    mode = req.mode
    if mode not in ("qa", "pravachan", "reading"):
        raise HTTPException(status_code=400, detail=f"Unknown mode: {mode!r}")
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="`question` is required")

    top_k = {"qa": 8, "pravachan": 15, "reading": 5}[mode]
    candidates = 30
    mmr_lambda = 0.7

    metadata_filter: Optional[Dict[str, Any]] = None
    if mode == "reading" and req.work:
        metadata_filter = {"work_id": req.work}
    max_per_source = top_k if (metadata_filter and "work_id" in metadata_filter) else 2

    t0 = time.time()
    chunks = _retrieve(
        question,
        top_k=top_k,
        candidates=candidates,
        mmr_lambda=mmr_lambda,
        max_per_source=max_per_source,
        metadata_filter=metadata_filter,
    )
    retrieval_s = time.time() - t0
    if not chunks:
        raise HTTPException(
            status_code=404,
            detail="No matching chunks for this query (corpus may be silent on the topic, or filter is too narrow)",
        )

    if mode == "pravachan":
        user_msg = build_pravachan_user_message(chunks, question)
    elif mode == "reading":
        title = req.passage_title or (req.work or "(current passage)")
        user_msg = build_reading_user_message(req.passage or "", chunks, question, title)
    else:
        user_msg = build_user_message(chunks, question)

    system_prompt = get_system_prompt(mode)
    return mode, user_msg, system_prompt, chunks, retrieval_s


def _retrieval_event_payload(chunks: List[Dict[str, Any]], retrieval_s: float) -> Dict[str, Any]:
    """Shape for the `retrieval` SSE event (RFC-010): chunk metadata + elapsed time.
    Strips the chunk text body (too large for an SSE event) — that's only needed server-side.
    """
    return {
        "chunks": [
            {
                "workTitle": c["meta"].get("title") or c["meta"].get("work_id"),
                "kind": c["meta"].get("kind"),
                "language": c["meta"].get("language"),
                "cos": c["cos_score"],
                "mmr": c["mmr_score"],
            }
            for c in chunks
        ],
        "elapsed_s": round(retrieval_s, 3),
    }


@app.post("/ask")
def ask(req: AskRequest, request: Request):
    """Main entry point.

    Accept: application/json  → single JSON body (existing behavior, CLI clients)
    Accept: text/event-stream → progressive SSE stream (RFC-010, chat-app)
    """
    accept = (request.headers.get("accept") or "").lower()
    wants_stream = "text/event-stream" in accept

    mode, user_msg, system_prompt, chunks, retrieval_s = _prepare_request(req)

    # Map the passage labels the model sees (A, B, C, ...) back to their chunks,
    # so Q&A citations emitted by reference can be spliced to verbatim text.
    # Same enumeration order as prompts.format_chunks_for_prompt.
    label_to_chunk = {_passage_label(i): c for i, c in enumerate(chunks)}

    if not wants_stream:
        # ── Non-streaming JSON path (CLI, tune_sweep.py, anything sending Accept: application/json)
        try:
            parsed, _response = STATE.client.ask_structured(
                mode=mode,
                system_prompt=system_prompt,
                user_message=user_msg,
                label_to_chunk=label_to_chunk,
            )
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=str(e))
        return parsed.model_dump(exclude_none=True)

    # ── Streaming SSE path (chat-app)
    def event_stream():
        # First: retrieval event so the UI can show "Found N passages in Xs"
        # while the LLM is still warming up.
        yield sse("retrieval", **_retrieval_event_payload(chunks, retrieval_s))

        last_event_ts = time.time()
        for kind, payload in STATE.client.ask_structured_stream(
            mode=mode,
            system_prompt=system_prompt,
            user_message=user_msg,
            label_to_chunk=label_to_chunk,
        ):
            now = time.time()
            if now - last_event_ts > 15:
                yield sse_heartbeat()
            yield sse(kind, **payload)
            last_event_ts = now

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # nginx hint: don't buffer SSE in production.
            "X-Accel-Buffering": "no",
        },
    )


def main() -> int:
    import uvicorn
    print(f"[server] starting on http://0.0.0.0:{PORT}", file=sys.stderr)
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
