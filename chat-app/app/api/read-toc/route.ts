// GET /api/read-toc
//
// Thin proxy to GET /read/{slug}/toc on the Python backend (tools/server.py).
// Returns the chapter index (grouped by ## भाग sections) so the reader UI can
// render an अनुक्रमणिका and jump-to-chapter drawer.
//
// Query params: slug (required), lang (optional).

import { NextRequest, NextResponse } from "next/server";
import { COOKIE_NAME as GATE_COOKIE, NAME_COOKIE } from "../../../lib/gate-cookie";

const BACKEND_URL =
  process.env.GURUDEV_BACKEND_URL || "http://localhost:8765";

export async function GET(req: NextRequest) {
  const params = req.nextUrl.searchParams;
  const slug = params.get("slug");
  if (!slug) {
    return NextResponse.json({ error: "slug is required" }, { status: 400 });
  }
  const lang = params.get("lang");
  const qs = new URLSearchParams();
  if (lang) qs.set("lang", lang);
  const url = `${BACKEND_URL}/read/${encodeURIComponent(slug)}/toc${qs.toString() ? "?" + qs.toString() : ""}`;

  const invite = req.cookies.get(GATE_COOKIE)?.value || "";
  const sadhak = req.cookies.get(NAME_COOKIE)?.value || "";

  let upstream: Response;
  try {
    upstream = await fetch(url, {
      cache: "no-store",
      headers: { "X-Invite-Code": invite, "X-Sadhak-Name": sadhak },
    });
  } catch {
    return NextResponse.json({ error: "Backend unreachable" }, { status: 502 });
  }
  const body = await upstream.text();
  return new NextResponse(body, {
    status: upstream.status,
    headers: { "content-type": "application/json" },
  });
}
