// POST /api/gate — RFC-016 §3 invite-code cookie + sadhak name.
//
// Stores the invite code AND the sadhak's name entered on /gate as HTTP-only
// cookies. All backend proxies (/api/ask, /api/read, /api/works, /api/report)
// read both and forward as `X-Invite-Code` + `X-Sadhak-Name` headers on every
// call to the FastAPI backend, which validates the code and logs the name.

import { NextResponse } from "next/server";
import { COOKIE_NAME, NAME_COOKIE, COOKIE_MAX_AGE_SEC } from "../../../lib/gate-cookie";

export async function POST(req: Request) {
  let body: { code?: unknown; name?: unknown };
  try {
    body = (await req.json()) as { code?: unknown; name?: unknown };
  } catch {
    return NextResponse.json({ error: "invalid_body" }, { status: 400 });
  }
  const code = typeof body.code === "string" ? body.code.trim() : "";
  const name = typeof body.name === "string" ? body.name.trim() : "";
  if (!code) {
    return NextResponse.json({ error: "code_required" }, { status: 400 });
  }
  if (!name) {
    return NextResponse.json({ error: "name_required" }, { status: 400 });
  }
  const res = NextResponse.json({ ok: true });
  const cookieOpts = {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    maxAge: COOKIE_MAX_AGE_SEC,
  };
  res.cookies.set({ name: COOKIE_NAME, value: code, ...cookieOpts });
  // Cap name at 80 chars so a pasted essay doesn't blow up log lines.
  res.cookies.set({ name: NAME_COOKIE, value: name.slice(0, 80), ...cookieOpts });
  return res;
}
