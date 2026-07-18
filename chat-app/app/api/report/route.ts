// POST /api/report
//
// Thin proxy to POST /report on the Python backend (tools/server.py).
// Accepts a JSON body: { question, mode, citations?, note? }
// and forwards it to the backend, returning { ok: true } on success.
//
// Backend URL: process.env.GURUDEV_BACKEND_URL || "http://localhost:8765"
// — same constant as the other proxy routes.

import { NextRequest, NextResponse } from "next/server";
import { COOKIE_NAME as GATE_COOKIE, NAME_COOKIE } from "../../../lib/gate-cookie";

const BACKEND_URL =
  process.env.GURUDEV_BACKEND_URL || "http://localhost:8765";

export async function POST(req: NextRequest) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const invite = req.cookies.get(GATE_COOKIE)?.value || "";
  const sadhak = req.cookies.get(NAME_COOKIE)?.value || "";

  // Auto-attach the sadhak's name from the gate cookie so the flag queue always
  // has attribution, even if the AnswerToolbar report modal doesn't ask again.
  const bodyObj = (body && typeof body === "object" ? body : {}) as Record<string, unknown>;
  if (sadhak && !bodyObj.name) bodyObj.name = sadhak;

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND_URL}/report`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Invite-Code": invite,
        "X-Sadhak-Name": sadhak,
      },
      body: JSON.stringify(bodyObj),
      cache: "no-store",
    });
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
