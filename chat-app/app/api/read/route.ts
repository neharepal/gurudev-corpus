// GET /api/read
//
// Thin proxy to GET /read/{slug} on the Python backend (tools/server.py).
// Query params: slug (required), lang (optional), page (optional, 1-based).
//
// Backend URL: process.env.GURUDEV_BACKEND_URL || "http://localhost:8765"
// — same constant as /api/ask/route.ts.

import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.GURUDEV_BACKEND_URL || "http://localhost:8765";

export async function GET(req: NextRequest) {
  const params = req.nextUrl.searchParams;
  const slug = params.get("slug");
  if (!slug) {
    return NextResponse.json({ error: "slug is required" }, { status: 400 });
  }

  const lang = params.get("lang");
  const page = params.get("page");

  const qs = new URLSearchParams();
  if (lang) qs.set("lang", lang);
  if (page) qs.set("page", page);

  const url = `${BACKEND_URL}/read/${encodeURIComponent(slug)}${qs.toString() ? "?" + qs.toString() : ""}`;

  let upstream: Response;
  try {
    upstream = await fetch(url, { cache: "no-store" });
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
