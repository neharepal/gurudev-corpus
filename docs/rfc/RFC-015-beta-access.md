# RFC-015: Beta access for a trusted handful

**Status:** ACCEPTED 2026-07-11 (implementation deferred to post-demo)
**Author:** Neha (with Claude)
**Created:** 2026-07-11

## Summary

Open the Gurudev Sangrah app to ~5–15 trusted testers (family/devotees) for an
**asynchronous** beta over days/weeks, so we can (a) see what people actually query and
(b) collect per-answer feedback. Achieved with the smallest possible additions on top of
the existing local stack: a **Cloudflare Tunnel** exposing the Next.js frontend, a
**password + name** gate, **per-person + global daily caps** on Anthropic spend, and
**JSONL query/feedback logging** with a small viewer. No cloud migration, no database.

## Motivation

The app answers well (grounding, cross-language citations, canonical-first ordering), but
we've only seen it exercised by ourselves. Real testers will surface (1) the actual query
distribution — phrasings, topics, languages we didn't anticipate — and (2) quality gaps via
thumbs + comments. Both directly feed the retrieval/answer work. The constraint is cost:
every query is an enforce-mode Anthropic call (Sonnet answer + Haiku intent/translation +
possible grounding retry), so an uncontrolled async beta risks a surprise bill.

## Goals

- Trusted testers reach the app from their own phones, anytime, over days/weeks.
- Every query and every feedback event is logged with **who** asked it.
- **Hard, automatic ceiling** on daily API spend.
- Minimal build; reuse the index/model already loaded on the Mac; zero hosting cost.

## Non-goals (YAGNI)

Real user accounts, a database, an analytics dashboard, abuse/bot protection, auto-scaling,
public launch. It's a trusted handful behind an unguessable URL + a shared password.

## Proposed design

### Topology (all on the operator's Mac)

```
Testers ─► Cloudflare Tunnel ─► Next.js frontend (:3000) ─► FastAPI backend (:8765)
              public https URL       `next start`, local          localhost only, private
```

Only the frontend is exposed; the backend stays private behind the Next.js `/api/ask`
proxy. `caffeinate` keeps the Mac awake for the beta's duration. A `start_beta.sh`
launches all four pieces (caffeinate + backend + `next start` + `cloudflared tunnel`).

### 1. Access & identity

- **Password gate**: a gate page in the Next.js app. The password is verified in a Next
  API route (`/api/beta-auth`) against a `BETA_PASSWORD` env var — never shipped to the
  browser bundle. Success sets an httpOnly cookie; middleware redirects unauthenticated
  requests to the gate.
- **Name**: first visit after unlock prompts *"Welcome — your name?"*, stored in
  `localStorage`, and sent on every query via an `X-Beta-User` header. The `/api/ask`
  proxy forwards the header to the backend.

### 2. Cost caps (enforced in the backend)

- **15 queries/person/day** + **100 queries/day global backstop** (both tunable constants).
- Counters persist to `logs/beta_usage.json` (`{date, global, per_user: {name: n}}`),
  reloaded on start, reset when the local date rolls over.
- On exceed, `/ask` returns HTTP **429** with a friendly body; the frontend renders
  *"Beta limit reached for today 🙏 — please try tomorrow."* Per-person and global hits
  get distinct messages.
- The check runs **before** any Anthropic call, so a capped request costs nothing.

### 3. Logging

- **Queries** → append one JSON line to `logs/beta_queries.jsonl`:
  `{id, ts, user, question, mode, lang, latency_s, cited_works: [...], n_citations,
   grounded: bool, error?: str}`. `id` is a per-query uuid so feedback can reference it.
- **Feedback** → new `POST /feedback` appends to `logs/beta_feedback.jsonl`:
  `{ts, user, question_id, rating: "up"|"down", comment?: str}`.

### 4. Feedback UI

Under each rendered answer: **👍 / 👎** buttons + an optional one-line comment field,
posting to `/feedback` (through a Next proxy route) with the query's `id` and the user's
name. Non-blocking; a thank-you tick on submit.

### 5. Reviewing

`tools/beta_log_view.py` pretty-prints recent activity — per user: their questions,
latency, cited works, and 👍/👎 + comments — joining the two JSONL files on `id`. Plain
`tail -f logs/beta_queries.jsonl` also works for a live view.

### 6. Error handling

- **Mac sleep / tunnel drop**: `start_beta.sh` (idempotent) relaunches everything;
  `caffeinate -dimsu` prevents sleep. Testers see a generic "temporarily unavailable" if
  the backend is unreachable (the existing proxy already surfaces this).
- **Backend/model error**: friendly message to the tester, full error to
  `beta_queries.jsonl` `error` field.
- **Wrong password**: gate denies, no cookie set.

## Alternatives considered

- **Cloud-deploy the backend** (Vercel frontend + a 2–4 GB VM for the model+index):
  always-on and Mac-independent, but ~half-day setup, ~$10–40/mo, and shipping the index —
  overkill for a trusted handful. Rejected for the beta; revisit for a real launch.
- **Per-person access codes** instead of one shared password: firmer identity, but requires
  generating/distributing N codes. Shared-password + self-entered name gives enough
  attribution for a trusted group at far less friction.
- **Monitor-only, no caps**: simplest, but no automatic spend ceiling — unacceptable given
  cost sensitivity.

## Tradeoffs & risks

1. **Mac must stay awake and online** for the whole beta. Mitigated by `caffeinate` + the
   relaunch script; accepted as the price of zero hosting cost. If the beta needs to run
   unattended for weeks, escalate to the cloud alternative.
2. **Shared password can leak.** Low stakes (read-only devotional Q&A), unguessable URL,
   and the global daily cap bounds worst-case spend even if the link spreads.
3. **In-memory/file counters** reset if the file is deleted; the global cap is the backstop.
4. **Feedback is opt-in**, so absence of a 👎 isn't a signal of quality — only explicit
   ratings are.

## Open questions

1. Cap numbers (15/person, 100/day) are first guesses — tune against the observed spend
   after day one.
2. Whether to log the **full answer text** (not just cited works + counts) — deferred; add
   the field if reviewing feedback needs the answer inline.
3. Named Cloudflare domain vs. an ephemeral `trycloudflare.com` URL (the latter changes on
   each restart; a named tunnel needs a Cloudflare account + a domain).

## References

- `tools/server.py` (backend, `/ask`), `chat-app/app/api/ask/route.ts` (proxy)
- RFC-010 (streaming), RFC-014 (retrieval/grounding re-arch)
- ADR-003 (Anthropic API is the paid backend, separate from Claude.ai)
