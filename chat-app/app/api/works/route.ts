// GET /api/works
//
// Thin proxy to GET /works on the Python backend (tools/server.py).
// Returns the list of canonical works that have at least one readable text.md.
//
// Response shape (from backend):
//   { "works": [ { "slug": string, "title": string, "author": string, "languages": string[] } ] }
//
// Backend URL: process.env.GURUDEV_BACKEND_URL || "http://localhost:8765"
// — same constant used by /api/ask and /api/read.

import { NextResponse } from "next/server";

const BACKEND_URL =
  process.env.GURUDEV_BACKEND_URL || "http://localhost:8765";

export async function GET() {
  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND_URL}/works`, { cache: "no-store" });
  } catch {
    return NextResponse.json(
      {
        error: `Backend unreachable at ${BACKEND_URL}. Start it with: ANTHROPIC_API_KEY=… python tools/server.py`,
      },
      { status: 502 },
    );
  }

  const data = await upstream.json();
  return NextResponse.json(data, { status: upstream.status });
}
