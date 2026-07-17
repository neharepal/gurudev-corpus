# Gurudev Sangrah — deploy runbook (RFC-016)

Ships the FastAPI backend to an AWS Lightsail box and the Next.js chat-app to
Vercel. Designed for a trusted-handful preview (single-instance, invite gate,
daily-cap spend backstop). Every stateful boundary is env-driven so migrating
to ECS Fargate + EFS + ElastiCache later is `terraform apply`, not a rewrite.

## What's here

    Dockerfile           Python 3.12 + BGE-M3 pre-cached; corpus bind-mounted.
    docker-compose.yml   backend + Caddy reverse proxy on the same host.
    Caddyfile            Automatic Let's Encrypt TLS for {$DOMAIN}.
    .env.example         Copy → `.env`, fill in secrets. GITIGNORED.

## Prerequisites (one-time, off-box)

    ☐ AWS account — https://aws.amazon.com/  (12-mo free tier eligible)
    ☐ Vercel account — https://vercel.com/  (free tier)
    ☐ Domain registered — Namecheap / Route 53 (~$12/yr for `.com`)
    ☐ Anthropic API key — https://console.anthropic.com/settings/keys

## Provision the Lightsail box

1. Lightsail console (region **ap-south-1** for India-based sadhaks, lowest
   latency) → **Create instance** → Ubuntu 24.04 LTS → **$20/mo plan** (4 GB
   RAM / 2 vCPU / 80 GB SSD).
2. **Networking** → attach a **static IP** (free while attached).
3. **Firewall** → open ports 22 (SSH), 80, 443.
4. DNS: at your registrar, create an **A record** `api.<yourdomain>` → the
   Lightsail static IP. Propagation 5-30 min.

## Ship the corpus

The corpus is gitignored (~1.85 GB). Rsync from your local machine to the box:

    # On your local machine, from the repo root:
    rsync -avz --progress \
        04_processed/ 01_canonical/ \
        ubuntu@<lightsail-static-ip>:/home/ubuntu/data/

Same command re-runs when you refresh the corpus later.

## First deploy

SSH via the Lightsail browser console (no key setup needed):

    # Install Docker + compose plugin
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker ubuntu
    # Log out + back in for group membership to apply.

    # Clone the code
    git clone https://github.com/neharepal/gurudev-corpus.git
    cd gurudev-corpus/deploy

    # Fill in secrets
    cp .env.example .env
    nano .env   # set ANTHROPIC_API_KEY, DOMAIN, LETSENCRYPT_EMAIL,
                # FRONTEND_ORIGIN, INVITE_CODE, DAILY_ANSWER_CAP

    # Bring it up
    docker compose up -d --build   # first build takes ~10 min (BGE-M3 layer)

    # Verify
    curl https://api.<yourdomain>/health   # expect status: "ready"

## Ship the chat-app to Vercel

1. Push your repo to GitHub (already there for this repo).
2. Vercel → **Add New Project** → import the repo → set **Root Directory** to
   `chat-app`.
3. **Environment Variables**:

        GURUDEV_BACKEND_URL=https://api.<yourdomain>
        NODE_ENV=production

   Vercel injects `NODE_ENV=production` automatically in prod builds; adding
   it here is safe.
4. Click **Deploy**. Vercel returns a `.vercel.app` URL — copy it.
5. On the Lightsail box, **update** `.env` so `FRONTEND_ORIGIN` matches your
   Vercel URL exactly. Then:

        docker compose restart backend

6. Share `https://<your-vercel-domain>.vercel.app` + the invite code with
   sadhaks.

## Day-to-day ops

### Rotate the invite code
On the Lightsail box:

    nano deploy/.env             # edit INVITE_CODE
    docker compose restart backend

All prior cookies are instantly invalidated — sadhaks land back on `/gate`.

### Refresh the corpus (Phase 3 re-OCR, arthasahit ingest, etc.)
On your local machine:

    rsync -avz --progress 04_processed/ 01_canonical/ \
        ubuntu@<lightsail-ip>:/home/ubuntu/data/

Then either restart or hit the in-memory reload endpoint:

    ssh ubuntu@<lightsail-ip> 'curl -X POST http://localhost:8765/admin/reload \
        -H "X-Invite-Code: $(grep INVITE_CODE deploy/.env | cut -d= -f2)"'

### Deploy a code update
On the Lightsail box:

    cd ~/gurudev-corpus
    git pull
    cd deploy
    docker compose build backend      # ~1-2 min (Python layer cached)
    docker compose up -d               # zero-downtime restart

### Logs
Live tail:                `docker compose logs -f backend`
JSON structured mode:     add `LOG_JSON=1` to `deploy/.env`, restart backend.
Historical (persisted):   `~/gurudev-corpus/deploy/volumes/backend_logs/`

### Health probe
    curl https://api.<yourdomain>/health

Returns `status: warming | ready | degraded` plus chunk count, invite gate
state, and today's answered-query count.

## When you outgrow Lightsail

The scale-ready seams — see `docs/rfc/RFC-016-cloud-hosting.md`:

    Rate-limit / daily-cap store       tools/gate.py::_DailyCounter (in-memory)
                                        → swap for a Redis-backed impl.
    Log sink                            stdout JSON (LOG_JSON=1)
                                        → Docker → CloudWatch is a flag on ECS.
    Corpus data                         bind-mount from $DATA_ROOT
                                        → EFS mount at the same path on ECS.
    Model weights                       baked into Dockerfile
                                        → same image works on ECS unchanged.
    Config                              env vars only (`.env`)
                                        → ECS task-definition env, same names.

Migration path: `terraform` an ECS Fargate service, an EFS volume, and an
ElastiCache Redis. Point the same Docker image at them. ~3-5 days end-to-end.

## Cost ceilings

| Layer | Monthly | Notes |
|---|---|---|
| Lightsail 4GB VPS | $20 | Fixed. |
| Vercel (Hobby) | $0 | Free until 100GB/mo bandwidth. |
| Anthropic Sonnet 4.6 | $30-80 realistic | Hard-capped by `DAILY_ANSWER_CAP`. |
| Domain | $1 amortised | ~$12/yr. |
| **Total** | **~$50-100** | Worst case with cap firing: ~$300/mo. |
