# Dev workflow — Gurudev Sangrah backend + chat-app

Two processes, one terminal each. The Python backend serves retrieval +
LLM (`tools/server.py`); the Next.js chat-app calls into it via
`/api/ask`.

## Env vars

| Var | Where | Default | Notes |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Python server | — | Required. Per ADR-003 the chat backend uses the Anthropic API, separate from any Claude.ai subscription. |
| `GURUDEV_BACKEND_PORT` | Python server | `8765` | Port the FastAPI app binds to. |
| `GURUDEV_BACKEND_URL` | chat-app | `http://localhost:8765` | URL the Next.js route forwards to. |
| `TOKENIZERS_PARALLELISM` | Python server | `false` | Set by the server; silences HuggingFace fork warning. |

## Start the backend

```sh
ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  /Users/neharepal/opt/anaconda3/bin/python tools/server.py
```

First start takes ~30 seconds — BGE-M3 (~2 GB) and the 6924-row
embedding matrix load once and stay resident. Subsequent calls are
instant.

Watch for these startup lines:

```
[startup] loading corpus...
[startup] N chunks (dim=1024) in M.Ms
[startup] loading embedding model: BAAI/bge-m3
[startup] model ready in M.Ms
[startup] ready
```

## Start the chat-app

In a separate terminal:

```sh
cd chat-app
npm run dev
```

Default URL: <http://localhost:3000>.

If the backend is on a non-default port, set `GURUDEV_BACKEND_URL`
before starting Next.js:

```sh
cd chat-app
GURUDEV_BACKEND_URL=http://localhost:8765 npm run dev
```

## Healthcheck

```sh
curl -s http://localhost:8765/health | jq
# -> {"ok": true, "model": "BAAI/bge-m3", "chunks": 6924}
```

If `chunks` is `0` or `ok` is missing, the embeddings did not load.
Re-run `tools/embedder.py` per `tools/SERVER_README.md`-adjacent
documentation in `docs/POST_DEMO_TODO.md`.

## One-shot smoke tests

```sh
curl -s -X POST http://localhost:8765/ask \
  -H "Content-Type: application/json" \
  -d '{"mode":"qa","question":"What are Gurudevs views on bhakti?","lang":"en"}'

curl -s -X POST http://localhost:8765/ask \
  -H "Content-Type: application/json" \
  -d '{"mode":"pravachan","question":"गीतेच्या बाराव्या अध्यायाचा सार काय?","lang":"mr"}'

curl -s -X POST http://localhost:8765/ask \
  -H "Content-Type: application/json" \
  -d '{"mode":"reading","question":"What is the General Introduction about?","lang":"en","work":"pathway-to-god-in-hindi-literature"}'
```

Each returns a JSON object whose `kind` field is `qa`, `pravachan`,
or `reading`. The full shape lives in `tools/schemas.py` and is
mirrored in `chat-app/lib/api.ts`.

## Restart

The server is single-process and stateful (model + corpus in RAM).
To pick up a prompt/schema change:

1. `Ctrl-C` the running server.
2. Re-run the start command. ~30 s cold start.

The chat-app picks up `route.ts` changes via Next.js HMR — no restart
needed unless you change `process.env.*` reads.

## Where things live

| File | Purpose |
|---|---|
| `tools/server.py` | FastAPI app — startup loader + `POST /ask`. |
| `tools/schemas.py` | pydantic models + JSON Schema (source of truth for response shape). |
| `tools/prompts.py` | Three system prompts (content rules only; format lives in schemas). |
| `tools/llm_client.py` | `ChatClient.ask_structured(...)` — tool-use call. |
| `tools/render.py` | Markdown renderer for CLI/sweep only — NOT on the request path. |
| `chat-app/app/api/ask/route.ts` | Thin proxy to `tools/server.py`. |
| `chat-app/lib/api.ts` | TS mirror of `tools/schemas.py`. |
| `docs/decisions/ADR-011-structured-output-contract.md` | Rationale + migration plan. |
