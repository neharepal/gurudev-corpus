"use client";

// RFC-016 §3 light gate — one shared invite code the operator distributes to
// sadhaks via WhatsApp/email. The code lives in an HTTP-only cookie so it's
// forwarded on every backend proxy call as the `X-Invite-Code` header.
// Validation happens on the backend (`tools/gate.py`); on 401 the API proxies
// redirect back here.

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

export default function GatePage() {
  const router = useRouter();
  const search = useSearchParams();
  const returnTo = search.get("from") || "/";
  const flag = search.get("reason") || "";

  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(
    flag === "invalid" ? "The code you entered isn't recognised — try again."
      : flag === "expired" ? "Your access has expired. Enter your code to continue."
      : null
  );

  useEffect(() => setErr(null), [code]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const r = await fetch("/api/gate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: code.trim() }),
      });
      if (!r.ok) {
        setErr("Something went wrong. Please try again in a moment.");
        return;
      }
      router.replace(returnTo);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px",
      }}
    >
      <form
        onSubmit={submit}
        style={{
          width: "100%",
          maxWidth: 440,
          background: "var(--bg-surface)",
          border: "1px solid var(--border-soft)",
          borderRadius: 12,
          boxShadow: "0 6px 24px rgba(60, 30, 10, 0.16)",
          padding: "40px 32px",
        }}
      >
        <h1 style={{ fontSize: 28, lineHeight: 1.2, marginTop: 0, marginBottom: 8 }}>
          Gurudev Sangrah
        </h1>
        <p style={{ color: "var(--text-secondary)", marginTop: 0, marginBottom: 24 }}>
          Private preview — enter the invite code you were sent.
        </p>

        <label
          htmlFor="invite"
          className="gd-label"
          style={{ color: "var(--text-tertiary)", display: "block", marginBottom: 6 }}
        >
          Invite code
        </label>
        <input
          id="invite"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          autoFocus
          autoComplete="off"
          spellCheck={false}
          style={{
            width: "100%",
            fontSize: 18,
            padding: "10px 12px",
            borderRadius: 6,
            outline: "none",
            background: "var(--bg-page)",
            border: "1px solid var(--border-stronger)",
            boxSizing: "border-box",
          }}
        />

        {err ? (
          <p style={{ fontSize: 14, marginTop: 12, marginBottom: 0, color: "var(--accent-maroon)" }}>
            {err}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={busy || !code.trim()}
          style={{
            marginTop: 24,
            padding: "10px 20px",
            borderRadius: 6,
            fontSize: 16,
            background: "var(--accent-maroon)",
            color: "#F4EAC9",
            border: "none",
            cursor: busy || !code.trim() ? "not-allowed" : "pointer",
            opacity: busy || !code.trim() ? 0.6 : 1,
          }}
        >
          {busy ? "Verifying…" : "Continue"}
        </button>
      </form>
    </main>
  );
}
