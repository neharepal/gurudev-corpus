// POST /api/ask
//
// Thin proxy to the Python backend (FastAPI, see tools/server.py).
//
// Two modes are negotiated via the `Accept` header on the incoming request:
//   - `application/json` (default): backend returns a single AskResponse JSON.
//     Used by tests, curl, any client that wants the whole thing at once.
//   - `text/event-stream`: backend returns SSE per RFC-010. We forward the
//     stream byte-for-byte to the caller. Used by the chat-app's React side.
//
// Per ADR-011 the structured response shape is the source of truth, and per
// RFC-010 the SSE event schema preserves that shape — we stream the *building*
// of the same JSON object, not free-text markdown.
//
// Backend URL: process.env.GURUDEV_BACKEND_URL || "http://localhost:8765".

import { NextResponse } from "next/server";

import type { ModeId } from "../../../data/mock-conversations";

export const runtime = "nodejs"; // SSE doesn't work cleanly on the edge runtime.

export type Lang = "en" | "mr";

type AskRequest = {
  mode: ModeId;
  question: string;
  lang?: Lang;
  work?: string;
  passage?: string;
  passage_title?: string;
  history?: unknown[];
};

const BACKEND_URL =
  process.env.GURUDEV_BACKEND_URL || "http://localhost:8765";

export async function POST(req: Request) {
  let body: AskRequest;
  try {
    body = (await req.json()) as AskRequest;
  } catch {
    return NextResponse.json(
      { error: "Invalid JSON body" },
      { status: 400 },
    );
  }

  const { mode, question } = body;
  if (!mode || !question?.trim()) {
    return NextResponse.json(
      { error: "Required: mode, question" },
      { status: 400 },
    );
  }

  // Honor the caller's content-type preference. Default to JSON; opt into
  // SSE only when explicitly requested.
  const accept = req.headers.get("accept") || "";
  const wantsStream = accept.includes("text/event-stream");

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND_URL}/ask`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: wantsStream ? "text/event-stream" : "application/json",
      },
      body: JSON.stringify({ ...body, question: question.trim() }),
    });
  } catch {
    return NextResponse.json(
      {
        error: `Backend unreachable at ${BACKEND_URL}. Start it with: ANTHROPIC_API_KEY=… python tools/server.py`,
      },
      { status: 502 },
    );
  }

  if (!upstream.ok) {
    let detail = `Backend returned ${upstream.status}`;
    try {
      const data = (await upstream.json()) as { detail?: string; error?: string };
      detail = data.detail || data.error || detail;
    } catch {
      // upstream body wasn't JSON; keep the status-line detail.
    }
    return NextResponse.json({ error: detail }, { status: 502 });
  }

  if (wantsStream) {
    // Pass the SSE body through unchanged. The Response constructor accepts
    // a ReadableStream<Uint8Array>, which is exactly what fetch returns.
    if (!upstream.body) {
      return NextResponse.json({ error: "Backend returned no stream body" }, { status: 502 });
    }
    return new Response(upstream.body, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
        // Hint for any proxy between us and the browser not to buffer.
        "X-Accel-Buffering": "no",
      },
    });
  }

  const data = await upstream.json();
  return NextResponse.json(data);
}
