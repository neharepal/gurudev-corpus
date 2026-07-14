# RUNBOOK — Phase 2 re-chunk + GPU re-embed (RFC-017)

The one-time rebuild that turns the section-chunk index into the small-to-big child index.
Run once when you're ready to cut over to Phase 2. Order matters: re-chunk locally →
embed the children on a GPU → bring the artifacts back → verify → then the retrieval wiring
(Task 6/7) and eval (Task 8) are built against the real child index.

**Precondition:** Phase-2 chunker changes are merged (Tasks 1–5). Confirm with:
`grep -c kind_level tools/chunker.py` (should be > 0).

---

## Step 1 — Re-chunk locally (produces children + parents)

```bash
cd /Users/neharepal/gurudev-corpus
export LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
/Users/neharepal/opt/anaconda3/bin/python tools/chunker.py
```

This rewrites:
- `04_processed/chunks.jsonl` — **children only** (sentence/verse units, each with `id`,
  `parent_id`, `text`, `embed_text`, `cite_text`).
- `04_processed/parents.jsonl` — the parent section rows (context lookup).

**Sanity-check the output:**
```bash
wc -l 04_processed/chunks.jsonl 04_processed/parents.jsonl   # children ~60-100k; parents ~17k
/Users/neharepal/opt/anaconda3/bin/python - <<'PY'
import json
kids=[json.loads(l) for l in open("04_processed/chunks.jsonl",encoding="utf-8")]
pids={json.loads(l)["id"] for l in open("04_processed/parents.jsonl",encoding="utf-8")}
print("children:",len(kids),"| parents:",len(pids))
print("all children have a real parent:", all(k["parent_id"] in pids for k in kids))
print("children with cite_text:", sum(1 for k in kids if "cite_text" in k))
print("arthasahit retrieval-only (no cite_text):",
      sum(1 for k in kids if k.get("work_id","").endswith("vachanamrut") and "cite_text" not in k))
PY
```
Expect: every child maps to a parent; most children citable; some arthasahit children retrieval-only.

Upload `04_processed/chunks.jsonl` somewhere the Colab notebook can fetch it (Google Drive,
or Colab's file-upload). Keep `parents.jsonl` local — it isn't embedded.

---

## Step 2 — Embed the children on a GPU (Colab)

BGE-M3 on ~60–100k short texts is ~30–90 min on a Colab T4 (free) / faster on Pro. The app
embeds with **sentence-transformers**, `normalize_embeddings=True`, `max_seq_length=1024`, no
prefix (bge-m3), and embeds each chunk's `embed_text` (falling back to `text`) — the notebook
below matches those settings exactly. Paste each block into a Colab cell (Runtime → change
runtime type → **GPU**).

**Cell 1 — install + upload:**
```python
!pip -q install "sentence-transformers>=2.7" numpy
from google.colab import files
up = files.upload()            # choose your chunks.jsonl
import io, json
CH = "chunks.jsonl"
chunks = [json.loads(l) for l in open(CH, encoding="utf-8") if l.strip()]
print(len(chunks), "children loaded")
```

**Cell 2 — embed (must match tools/embedder.py conventions):**
```python
import numpy as np, torch, time
from sentence_transformers import SentenceTransformer
assert torch.cuda.is_available(), "Runtime → change runtime type → GPU"

MODEL = "BAAI/bge-m3"
MAX_SEQ = 1024
def text_for_embedding(c):                      # RFC-017: embed embed_text, fallback text
    return c.get("embed_text") or c.get("text") or ""

m = SentenceTransformer(MODEL, device="cuda")
m.max_seq_length = MAX_SEQ
texts = [text_for_embedding(c) for c in chunks]
t0 = time.time()
emb = m.encode(texts, batch_size=64, normalize_embeddings=True,
               convert_to_numpy=True, show_progress_bar=True)
emb = emb.astype(np.float32)                    # match embeddings.npy dtype
print("shape", emb.shape, "| dtype", emb.dtype, "|", round(time.time()-t0), "s")
np.save("embeddings.npy", emb)                  # row-aligned to chunks.jsonl order
```

**Cell 3 — write chunks_meta.jsonl (each child minus `text`, same order) + download:**
```python
with open("chunks_meta.jsonl", "w", encoding="utf-8") as f:
    for c in chunks:
        f.write(json.dumps({k: v for k, v in c.items() if k != "text"}, ensure_ascii=False) + "\n")
from google.colab import files
files.download("embeddings.npy")
files.download("chunks_meta.jsonl")
```

> The row order of `embeddings.npy`, `chunks_meta.jsonl`, and `chunks.jsonl` MUST be identical
> — the notebook preserves it (single in-memory list, no shuffling). Do not sort anything.

---

## Step 3 — Bring artifacts back + verify (local)

```bash
cd /Users/neharepal/gurudev-corpus
# place the two downloaded files:
mv ~/Downloads/embeddings.npy 04_processed/embeddings/embeddings.npy
mv ~/Downloads/chunks_meta.jsonl 04_processed/embeddings/chunks_meta.jsonl
# quality scores (Step 7.5) — idempotent
/Users/neharepal/opt/anaconda3/bin/python tools/build_chunk_quality.py
# alignment check
/Users/neharepal/opt/anaconda3/bin/python - <<'PY'
import json, numpy as np
emb=np.load("04_processed/embeddings/embeddings.npy")
metas=[json.loads(l) for l in open("04_processed/embeddings/chunks_meta.jsonl",encoding="utf-8")]
chunks=[json.loads(l) for l in open("04_processed/chunks.jsonl",encoding="utf-8")]
print("rows:",emb.shape[0],"metas:",len(metas),"chunks:",len(chunks),"dim:",emb.shape[1])
assert emb.shape[0]==len(metas)==len(chunks), "COUNT MISMATCH"
assert all(metas[i]["id"]==chunks[i]["id"] for i in range(len(metas))), "ORDER MISMATCH"
assert all("parent_id" in m for m in metas), "children missing parent_id"
print("ALIGNED ✓  dim==1024:", emb.shape[1]==1024)
PY
```

If alignment fails, STOP — do not serve a misaligned index.

---

## Step 4 — Then: retrieval wiring + eval (post-re-embed tasks)

With the real child index in place (`parent_id` present), now build and VALIDATE:
- **Task 6/7 combined** — flag-gated (`ENABLE_SMALL_TO_BIG`) child→parent expansion in
  `_retrieve` (using `expand_children_to_parents`, already merged) + splice/Read-in-full on
  `cite_text`. Option B: the child stays the citation anchor (splice contract unchanged); the
  parent section is supplied as separate context to the answer model.
- **Task 8** — `eval_retrieval.py` gold cases: confirm the lightning child now surfaces; no
  doctrinal regression; arthasahit citations quote verses only.
- Smoke-test a few live queries with `ENABLE_SMALL_TO_BIG=1` before making it the default.

## Step 5 — Changelog + backup

- Back up the pre-Phase-2 index (`cp -r 04_processed/embeddings 04_processed/_bak-pre-phase2`).
- Append a `CORPUS_CHANGELOG.md` entry: children count, parents count, model, date, eval result.
- Commit the new index artifacts / update the manifest.
