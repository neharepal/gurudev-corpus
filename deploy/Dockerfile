# RFC-016 backend image — FastAPI + BGE-M3 + in-RAM index.
#
# Layout intent: this image contains ONLY the code + Python deps + a pre-cached
# HuggingFace model. The corpus (04_processed/, 01_canonical/) is bind-mounted
# from the host at runtime — the image stays reusable, the ~1.8 GB data can be
# refreshed independently, and rolling out a new corpus is `rsync` + `docker
# compose restart`, no image rebuild required.

FROM python:3.12-slim AS base

# System deps: build tools for numpy/scipy wheels + curl (health checks).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user matches the "no root inside containers" hosting default.
RUN useradd --create-home --shell /bin/bash --uid 1000 gurudev

WORKDIR /app

# Install Python deps first — the layer cache survives corpus / code changes.
COPY --chown=gurudev:gurudev requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Pre-cache the BGE-M3 model weights into the image so cold-start doesn't
# depend on HuggingFace being reachable. This adds ~2 GB to the image but
# removes a 30-60 s startup network dependency (RFC-016 §2).
ENV HF_HOME=/home/gurudev/.cache/huggingface \
    TRANSFORMERS_OFFLINE=0
RUN mkdir -p ${HF_HOME} && chown -R gurudev:gurudev /home/gurudev
USER gurudev
RUN python -c "from sentence_transformers import SentenceTransformer; \
              SentenceTransformer('BAAI/bge-m3', trust_remote_code=True)"

# App code (the corpus lives on a bind-mount, NOT copied here — see compose).
USER root
COPY --chown=gurudev:gurudev tools/    ./tools/
COPY --chown=gurudev:gurudev 03_catalog/ ./03_catalog/
COPY --chown=gurudev:gurudev 02_aggregated/ ./02_aggregated/
# Named log volume mounts on top of /app/logs; Docker copies the image dir's
# ownership + content into a FRESH volume, so pre-creating the dir with the
# right owner is what stops the container's log writes from silently failing
# with EACCES. Existing volumes are unaffected — remove them (`docker volume
# rm <compose>_backend_logs`) before `docker compose up` to pick this up.
RUN mkdir -p /app/logs && chown gurudev:gurudev /app/logs
USER gurudev

# Runtime knobs (documented; overridden by docker-compose env).
#   ENABLE_SMALL_TO_BIG=1  default-on when 04_processed/parents.jsonl is present
#   GURUDEV_BACKEND_PORT=8765
#   ANTHROPIC_API_KEY, FRONTEND_ORIGIN, INVITE_CODE — required, set in .env
ENV GURUDEV_BACKEND_PORT=8765 \
    PYTHONUNBUFFERED=1

EXPOSE 8765

# Health probe hits GET /; server returns 404 for unknown routes but the
# request completes → connection working, model loaded (startup finished).
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8765/ >/dev/null || exit 1

CMD ["python", "tools/server.py"]
