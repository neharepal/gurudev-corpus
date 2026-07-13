# RFC-016: Cloud hosting for public access

**Status:** ACCEPTED 2026-07-13 (implementation deferred — build AFTER the Phase 2
re-chunk, before public launch)
**Author:** Neha (with Claude)
**Created:** 2026-07-13
**Supersedes:** RFC-015 (Mac + Cloudflare tunnel beta)

## Summary

Move the Gurudev Sangrah app off the operator's Mac onto cloud hosting so it can serve a
public audience without the machine staying awake. The **frontend goes to Vercel** (native
Next.js, HTTPS, CDN) with `GURUDEV_BACKEND_URL` pointed at the hosted backend. The
**backend — FastAPI + BGE-M3 + the in-RAM embeddings/BM25 index — goes to an always-on
container or VM** (Fly.io / Railway / Render, or a Hetzner/DigitalOcean VM) sized at
~3–4 GB RAM (model ~2 GB + embeddings + headroom) with steady CPU. CORS locks to the
Vercel domain, `ANTHROPIC_API_KEY` becomes a host secret, and RFC-015's spend-cap logic
ports over keyed on IP/session rather than a shared password.

## Motivation

RFC-015 stood up a **trusted-handful** beta: a Cloudflare Tunnel off the Mac behind a
shared password, deliberately not a cloud migration. After the demo, public interest now
warrants real hosting. The tunnel model does not scale — it requires the Mac to stay awake
and online indefinitely, ties availability to one laptop, and its shared-password gate was
sized for ~5–15 known people, not an open audience. To let anyone reach the app reliably,
the backend needs a long-lived home independent of the operator's machine, and the frontend
needs real HTTPS/CDN hosting. This RFC records that decision (agreed with the operator) and
the shape of the migration; it does **not** schedule the build, which is deferred until
after the Phase 2 re-chunk lands.

## Goals

- The app is reachable by the public over HTTPS without the operator's Mac running.
- The backend runs as a warm, long-lived process (model + index already in RAM) so query
  latency is dominated by the Anthropic call, not model load.
- API spend and abuse are bounded automatically, without a shared password.
- A clear, incremental path from "tens of users on one instance" to more capacity.
- Query/feedback logs survive restarts.

## Non-goals

- Full user accounts / auth system (a light gate is enough to start).
- Auto-scaling, multi-region, or load-balanced fleets on day one.
- Choosing the specific platform or committing a budget — left as open questions.
- Any change to retrieval, grounding, or corpus content (those live in RFC-014 / RFC-009).

## Proposed design

### 1. Topology

```
Public ─► Vercel (Next.js frontend, HTTPS + CDN) ─► hosted backend (FastAPI :8765)
             GURUDEV_BACKEND_URL ────────────────────►  always-on container / VM
                                                         BGE-M3 + embeddings + BM25 in RAM
```

The frontend deploys to Vercel unchanged — it is a standard Next.js app, and the `/api/ask`
route already proxies to `process.env.GURUDEV_BACKEND_URL` (default `http://localhost:8765`).
The only wiring change is setting `GURUDEV_BACKEND_URL` on Vercel to the backend's public
URL. The backend is **stateless per request** — each `/ask` reads the in-RAM index and calls
Anthropic; nothing is persisted between requests except append-only logs — which makes it
hosting-friendly: no session affinity is required, and instances are interchangeable. The
backend stays a single origin behind the Next proxy, so browsers still talk only to the
Vercel domain.

### 2. Shipping the model + index

The corpus and index are gitignored data, so the backend image cannot simply `git clone`
them. The backend needs, at runtime:

- `embeddings.npy` (~66 MB) — the dense vectors loaded into RAM at startup.
- `chunks.jsonl` (~55 MB) — chunk text + metadata for retrieval and citation.
- the `text.md` tree — required for the Read-in-full path (whole-passage retrieval).

Two viable ways to get these onto the host: **bake them into the container image** (simple,
immutable, larger image) or **mount a persistent volume** and populate it once (smaller
image, data survives redeploys). Either is acceptable; the volume approach also doubles as
the log store (see §4).

BGE-M3 itself downloads from HuggingFace on first startup (~2 GB). To avoid a slow, network-
dependent cold start, **pre-cache the model weights into the image** (or into the mounted
volume) at build time. On process start the existing **~20 s warmup** — loading the model
and building the BM25 index — runs once; on an always-on instance this is paid only on cold
start (deploy / restart), not per request.

### 3. Config & security

- **`ANTHROPIC_API_KEY` as a host secret** — set via the platform's secret store (Fly
  secrets / Railway/Render env vars / systemd `EnvironmentFile` on a VM), never baked into
  the image or committed.
- **CORS locked to the Vercel domain** — the backend's CORS middleware is currently
  permissive (open for local dev); in production it must allow only the Vercel frontend
  origin(s), so the public backend URL can't be driven from arbitrary sites.
- **Access + abuse control** — RFC-015's cap logic ports over, but **keyed on IP/session
  instead of a shared password**:
  - **Per-IP / per-session rate limits** — a short-window request cap to stop a single
    client hammering the (paid) Anthropic path.
  - **Global daily cap** — the RFC-015 backstop, unchanged in spirit: a hard ceiling on
    total answered queries/day, checked **before** any Anthropic call so a capped request
    costs nothing. On exceed, return HTTP 429 with a friendly body.
  - **A light gate to start** — an invite code or a simple challenge in front of the app,
    so "public" launches as "anyone with the link/code" rather than fully wide-open on day
    one. Cheap to add, easy to remove or upgrade to accounts later.

### 4. Persistence & ops

- **Logs to durable storage** — the container filesystem is ephemeral (wiped on redeploy),
  so RFC-015's JSONL query/feedback logs must write to a **mounted volume** or a **small
  database**. Same store can hold the daily-cap counters so they survive restarts.
- **Process supervision + health checks** — run under the platform's supervisor (Fly
  machines / Railway / Render process management, or systemd on a VM) with an HTTP health
  endpoint so the platform restarts a crashed or unresponsive backend.
- **HTTPS** — terminated by the platform (Vercel for the frontend, the backend platform's
  built-in TLS / managed certs for the API origin). No manual cert management.

### 5. Concurrency & scale

Each answer holds a **slow Anthropic call** (Sonnet answer + Haiku intent/translation +
possible grounding retry) open for its duration. For **tens of concurrent users a single
instance is fine** — the box is mostly idle waiting on the API, not CPU-bound on the model.
Beyond that, the scale path is straightforward because the backend is stateless: **add
worker processes / instances** behind the platform's routing. Two latency levers to weigh
before or during launch:

- **Server-side caching of common questions** — many public users will ask overlapping
  questions; caching answers (or at least retrieval results) for frequent queries cuts both
  latency and API spend. Considered a likely pre-launch add (see open questions).
- **Revisit enforce-mode latency** — the "Level-2 stream-and-verify" grounding buffers the
  answer for verification before release. Under many concurrent users, each waiting on a
  buffered answer, this compounds; worth revisiting so the enforce path doesn't make the
  shared instance feel slow.

## Alternatives considered

- **Keep the Mac + Cloudflare tunnel (RFC-015).** Zero hosting cost and already built, but
  it doesn't scale and the Mac must stay awake and online continuously — unacceptable for a
  public, unattended audience. This is exactly what this RFC supersedes.
- **Fully serverless backend** (e.g. Lambda / serverless functions per request). Attractive
  for cost-at-idle, but the ~2 GB BGE-M3 model plus the in-RAM embeddings/BM25 index need a
  **warm, long-lived process** — cold-starting the model on each invocation is too slow and
  too costly, and serverless RAM/duration limits fight a 2 GB model. Rejected in favour of
  an always-on container/VM.

## Tradeoffs & risks

1. **Real, recurring cost.** Unlike the tunnel beta, an always-on instance plus API spend is
   a monthly bill. Bounded on the API side by the daily cap; the hosting floor is the price
   of Mac-independence. Budget is an open question below.
2. **Data shipping is a manual step.** The gitignored index/model must be baked or volume-
   loaded out of band; a stale image can serve an old index. Tie index updates to the
   deploy/volume-refresh procedure.
3. **Single instance is a single point of failure** until the scale path is exercised. Health
   checks + auto-restart mitigate; multi-instance is deferred, not designed away.
4. **IP/session keying is weaker identity** than named users — shared NATs, rotating IPs. The
   global daily cap remains the hard backstop on worst-case spend regardless.

## Open questions

Left for the operator to decide at build time:

1. **Platform choice** — a managed PaaS (Fly.io / Railway / Render) for less ops, vs. a raw
   VM (Hetzner / DigitalOcean) for more control and often lower cost.
2. **Public access model** — fully open + rate-limited, vs. invite/gated, vs. real accounts.
3. **Budget** — the acceptable monthly hosting + Anthropic API spend, which in turn bounds
   the daily cap and instance size.
4. **Server-side answer caching** — add it before launch (to cut latency/spend on common
   questions), or ship without and add reactively.

## References

- RFC-015: Beta access for a trusted handful (superseded — Mac + Cloudflare tunnel)
- RFC-014: Retrieval / grounding re-architecture (enforce-mode, Level-2 stream-and-verify)
- ADR-003: Anthropic API is the paid answer backend (separate from Claude.ai)
- ADR-017: Dual-retrieval (dense BGE-M3 + BM25)
- `tools/server.py` (FastAPI backend, `/ask`, CORS, model + BM25 warmup)
- `chat-app/app/api/ask/route.ts` (Next.js proxy, `GURUDEV_BACKEND_URL`)
