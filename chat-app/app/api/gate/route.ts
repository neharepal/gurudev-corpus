// POST /api/gate — RFC-016 §3 invite-code cookie.
//
// Stores the code entered on /gate as an HTTP-only cookie. All backend proxies
// (/api/ask, /api/read) read it and forward as `X-Invite-Code` on every call
// to the FastAPI backend, which validates against INVITE_CODE. Validation
// happens server-side (backend) so we don't leak the expected value here.

import { NextResponse } from "next/server";

// 30-day session — sadhaks shouldn't have to re-enter the code every visit.
// Rotating the code (host-side INVITE_CODE change + restart) invalidates all
// prior cookies automatically on the next request → they land back on /gate.
const COOKIE_MAX_AGE_SEC = 60 * 60 * 24 * 30;
export const COOKIE_NAME = "gurudev-invite";

export async function POST(req: Request) {
  let body: { code?: unknown };
  try {
    body = (await req.json()) as { code?: unknown };
  } catch {
    return NextResponse.json({ error: "invalid_body" }, { status: 400 });
  }
  const code = typeof body.code === "string" ? body.code.trim() : "";
  if (!code) {
    return NextResponse.json({ error: "code_required" }, { status: 400 });
  }
  const res = NextResponse.json({ ok: true });
  res.cookies.set({
    name: COOKIE_NAME,
    value: code,
    httpOnly: true,
    // Secure only in production; `false` locally lets `http://localhost:3000`
    // still work in dev.
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: COOKIE_MAX_AGE_SEC,
  });
  return res;
}
