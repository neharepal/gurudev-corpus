// Thin client for /api/ask. UI components call `askApi(...)` and get back
// the structured response shape that QAAnswerBody / PravachanAnswerBody /
// the Reading drawer already consume.
//
// The route at `app/api/ask/route.ts` proxies to the Python backend
// (tools/server.py) which runs BGE-M3 retrieval + Anthropic tool-use and
// returns this exact shape (see ADR-011). The mirroring pydantic models
// live in tools/schemas.py — keep these types in sync.

import type { ModeId } from "../data/mock-conversations";

export type Lang = "en" | "mr";

// Compact record of what was already cited in one prior conversation turn.
// Sent in history so the backend can instruct the model not to repeat them.
export type HistoryTurn = {
  question: string;
  cited_passages: Array<{
    workTitle: string;
    location: string;
  }>;
};

export type AskRequest = {
  mode: ModeId;
  question: string;
  lang?: Lang;
  // Scopes retrieval to a specific work. Used by Reading mode and by
  // work-scoped Q&A (drawer "Ask about this work"). Ignored by Pravachan.
  work?: string;
  // Conversational history for follow-up questions. Each entry carries the
  // prior question and a compact list of passages already cited, so the
  // backend can instruct the model to bring new material rather than repeat.
  // Empty / absent for the very first question in a thread.
  history?: HistoryTurn[];
};

// Lightweight reference used by meta-mode Q&A (ADR-010): a work the
// answer drew on without quoting verbatim.
export type Reference = {
  workTitle: string;
  location?: string;
  author?: string;
};

export type AskResponse =
  | {
      kind: "qa";
      // Emitted by the LLM (ADR-010) for audit; UI does not switch on this.
      // UI branches on `citations.length` instead.
      classification?: "doctrinal" | "meta";
      question: string;
      framing: string;
      // Optional paragraph array. LLMs reliably emit JSON arrays but
      // unreliably emit literal "\n\n" in JSON strings, so longer meta
      // answers come back here, one paragraph per element. The UI prefers
      // this array when present; otherwise it falls back to splitting
      // `framing` on \n{2,}.
      framingParagraphs?: string[];
      citations: Array<{
        quote: Quote;
        whyChosen: string;
      }>;
      // Meta-mode only — works the answer drew on but did not quote verbatim.
      references?: Reference[];
      synthesis?: string;
    }
  | {
      kind: "pravachan";
      question: string;
      thesis?: string;
      gurudevsWords?: Quote;
      examples: Array<{
        title: string;
        gloss?: string;
        quote: Quote;
        whyThisExample: string;
        readSlug?: string;
      }>;
    }
  | {
      kind: "reading";
      question: string;
      framing: string;
      passage: string;
      attribution: {
        workTitle: string;
        chapter: string;
        author: string;
      };
    };

type Quote = {
  body: string;
  workTitle: string;
  location: string;
  kind: "canonical" | "athvani" | "biography";
  author: string;
  // Optional short gloss in the user's language when the quote is in
  // a different language. Clearly a paraphrase, not the source.
  paraphrase?: string;
  // Server-filled: the work_id for the source work. Non-empty only for
  // canonical quotes that had a matching chunk. Used by QuoteBlock to render
  // a "Read in full" link to /read/{workId}. Empty string or absent for
  // athvani / biography / quotes without a chunk match.
  workId?: string;
  // Server-filled: 1-based page in the reading surface where the cited
  // passage appears. When present, the "Read in full" link opens the reader
  // directly at this page instead of page 1.
  readPage?: number;
};

// ────────────────────────────────────────────────────────────────────────────
// Report-issue API
// ────────────────────────────────────────────────────────────────────────────

export type ReportCitation = {
  workTitle: string;
  location: string;
  /** RFC-004: the verbatim quote body, so reviewers see what was cited. */
  body?: string;
};

export type ReportRequest = {
  question: string;
  mode: string;
  citations?: ReportCitation[];
  note?: string;
  /** RFC-004 flag category selected from the radio group. */
  category?: string;
  /**
   * RFC-004: the full answer text (framing/synthesis joined) so reviewers
   * can see exactly what the model said without re-running the query.
   */
  answer_text?: string;
};

/**
 * POST `/api/report` — flag a garbled or incorrect answer for the queue.
 * Resolves to `{ ok: true }` on success; throws on network or server error.
 */
export async function reportIssue(req: ReportRequest): Promise<{ ok: boolean }> {
  const res = await fetch("/api/report", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    let msg = `Report failed (${res.status})`;
    try {
      const body = (await res.json()) as { error?: string };
      if (body.error) msg = body.error;
    } catch {
      // Body wasn't JSON.
    }
    throw new Error(msg);
  }
  return (await res.json()) as { ok: boolean };
}

export type CorrectionRequest = {
  /** Always "correction" — allows the queue consumer to distinguish from plain issues. */
  kind: "correction";
  /** Work slug, e.g. "pathway-to-god-in-hindi-literature". */
  slug: string;
  /** 1-based page number in the reader. */
  page: number;
  /** Paragraph n value as returned by the backend (1-based, sequential across the whole work). */
  paragraph: number;
  /** The paragraph text as rendered to the user before editing. */
  original: string;
  /** The user's corrected text. */
  corrected: string;
  /** UI language at submission time. */
  lang: Lang;
  /** Required by pydantic ReportRequest — empty string for corrections. */
  question: string;
  /** Required by pydantic ReportRequest. */
  mode: string;
  /** Contributor name (required) — surfaced in the flag queue so reviewers
   * know who suggested the change (there is no login). */
  name: string;
};

/**
 * POST `/api/report` with a correction payload.
 * Resolves to `{ ok: true }` on success; throws on network or server error.
 */
export async function reportCorrection(
  req: CorrectionRequest,
): Promise<{ ok: boolean }> {
  const res = await fetch("/api/report", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    let msg = `Report failed (${res.status})`;
    try {
      const body = (await res.json()) as { error?: string };
      if (body.error) msg = body.error;
    } catch {
      // Body wasn't JSON.
    }
    throw new Error(msg);
  }
  return (await res.json()) as { ok: boolean };
}

export class AskError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function askApi(
  req: AskRequest,
  signal?: AbortSignal,
): Promise<AskResponse> {
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    signal,
  });
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const body = (await res.json()) as { error?: string };
      if (body.error) msg = body.error;
    } catch {
      // Body wasn't JSON. Use the status-line fallback.
    }
    throw new AskError(msg, res.status);
  }
  return (await res.json()) as AskResponse;
}

// ────────────────────────────────────────────────────────────────────────────
// Streaming client (RFC-010)
// ────────────────────────────────────────────────────────────────────────────

// Minimal shape for the retrieval-event chunk metadata. The full chunk text
// stays on the server; the chat surface only needs labels + scores to render
// a "found N passages in Xs" affordance.
export type ChunkSummary = {
  workTitle: string;
  kind: "canonical" | "athvani" | "biography";
  language: string;
  cos: number;
  mmr: number;
};

// SSE event types emitted by the Python service per RFC-010.
export type StreamEvent =
  | {
      type: "retrieval";
      chunks: ChunkSummary[];
      elapsed_s: number;
    }
  | {
      // A top-level field has fully decoded.
      type: "field";
      name: string;
      value: unknown;
    }
  | {
      // An array field has closed (sentinel; the array's elements arrived as
      // `array_item` events).
      type: "field_close";
      name: string;
    }
  | {
      // One element of a top-level array (citations, examples, references).
      type: "array_item";
      array: string;
      index: number;
      value: unknown;
    }
  | {
      // Token-level delta for a top-level string field (framing, thesis,
      // question echo, etc.). Phase 1 deltas only fire for top-level strings.
      type: "delta";
      path: string;
      text: string;
    }
  | {
      // The full validated response. Use this to reconcile against the
      // progressively-built state.
      type: "done";
      response: AskResponse;
      usage: { input: number; output: number; cache_read: number; cache_creation: number };
    }
  | {
      type: "error";
      message: string;
    };

/**
 * Stream `/api/ask` as a sequence of typed events.
 *
 * The caller passes an `onEvent` handler that's invoked for each event as it
 * arrives off the wire. Order is the order the server emits — usually:
 *   retrieval → (delta | field | array_item)+ → done.
 * Heartbeats (SSE comment frames) are silently dropped.
 *
 * `done` is the final reconciled response. If you only need the full answer
 * (no progressive UI), use `askApi(...)` instead — the streaming path costs
 * the same tokens but adds parsing surface.
 */
export async function askApiStream(
  req: AskRequest,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(req),
    signal,
  });
  if (!res.ok || !res.body) {
    let msg = `Request failed (${res.status})`;
    try {
      const body = (await res.json()) as { error?: string };
      if (body.error) msg = body.error;
    } catch {
      // Body wasn't JSON. Use the status-line fallback.
    }
    throw new AskError(msg, res.status);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  // SSE frames are separated by a blank line ("\n\n"). Inside a frame,
  // `data:` lines carry our JSON payload; comment lines (starting with ":")
  // are heartbeats and ignored.
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const frame = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      for (const rawLine of frame.split("\n")) {
        const line = rawLine.replace(/\r$/, "");
        if (line.startsWith(":")) continue; // heartbeat
        if (!line.startsWith("data:")) continue;
        const payload = line.slice(5).trim();
        if (!payload) continue;
        try {
          onEvent(JSON.parse(payload) as StreamEvent);
        } catch {
          // Malformed event; skip rather than tearing down the whole stream.
        }
      }
    }
  }
}
