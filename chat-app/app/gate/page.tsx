"use client";

// RFC-016 §3 light gate — one shared invite code the operator distributes to
// sadhaks via WhatsApp/email + the sadhak's name for usage attribution. Both
// values live in HTTP-only cookies and are forwarded on every backend proxy
// call as `X-Invite-Code` + `X-Sadhak-Name` headers. Backend validates the
// code (tools/gate.py) and logs each request against the name.

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

export default function GatePage() {
  return (
    <Suspense fallback={<GateFallback />}>
      <GateForm />
    </Suspense>
  );
}

function GateFallback() {
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
      <div
        style={{
          width: "100%",
          maxWidth: 440,
          background: "var(--bg-surface)",
          border: "1px solid var(--border-soft)",
          borderRadius: 12,
          padding: "40px 32px",
          opacity: 0.7,
        }}
      >
        <h1 style={{ fontSize: 28, lineHeight: 1.2, marginTop: 0, marginBottom: 8 }}>
          Gurudev Sangrah
        </h1>
        <p style={{ color: "var(--text-secondary)" }}>Loading…</p>
      </div>
    </main>
  );
}

function GateForm() {
  const router = useRouter();
  const search = useSearchParams();
  const returnTo = search.get("from") || "/";
  const flag = search.get("reason") || "";

  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(
    flag === "invalid" ? "The code you entered isn't recognised — try again."
      : flag === "expired" ? "Your access has expired. Enter your details to continue."
      : null
  );

  useEffect(() => setErr(null), [code, name]);

  const canSubmit = !!name.trim() && !!code.trim() && !busy;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setErr(null);
    try {
      const r = await fetch("/api/gate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: code.trim(), name: name.trim() }),
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

  const fieldLabelStyle = {
    color: "var(--text-tertiary)",
    display: "block",
    marginBottom: 6,
  } as const;
  const inputStyle = {
    width: "100%",
    fontSize: 18,
    padding: "10px 12px",
    borderRadius: 6,
    outline: "none",
    background: "var(--bg-page)",
    border: "1px solid var(--border-stronger)",
    boxSizing: "border-box" as const,
  };

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
          Private preview — enter your name and the invite code you were sent.
        </p>

        <label htmlFor="sadhak-name" className="gd-label" style={fieldLabelStyle}>
          Your name
        </label>
        <input
          id="sadhak-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          autoFocus
          autoComplete="name"
          maxLength={80}
          style={inputStyle}
        />

        <div style={{ height: 16 }} />

        <label htmlFor="invite" className="gd-label" style={fieldLabelStyle}>
          Invite code
        </label>
        <input
          id="invite"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          autoComplete="off"
          spellCheck={false}
          style={inputStyle}
        />

        {err ? (
          <p style={{ fontSize: 14, marginTop: 12, marginBottom: 0, color: "var(--accent-maroon)" }}>
            {err}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={!canSubmit}
          style={{
            marginTop: 24,
            padding: "10px 20px",
            borderRadius: 6,
            fontSize: 16,
            background: "var(--accent-maroon)",
            color: "#F4EAC9",
            border: "none",
            cursor: canSubmit ? "pointer" : "not-allowed",
            opacity: canSubmit ? 1 : 0.6,
          }}
        >
          {busy ? "Verifying…" : "Continue"}
        </button>
      </form>
    </main>
  );
}
