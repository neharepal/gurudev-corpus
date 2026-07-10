# Retrieval Investigation Log

A running, evidence-based journal of retrieval / answer-quality debugging. The
point is **institutional memory**: every hypothesis we tried, the evidence, and
whether it worked — so we never silently repeat a dead end. Newest entries on
top. Pair this with [DEBUGGING-PROTOCOL.md](./DEBUGGING-PROTOCOL.md).

When you finish an investigation, add an entry. When you're *about* to try
something, grep this file first — it may already be ruled out.

---

## 2026-07-09 — "कारलाईल कॉटेज" (Carlyle Cottage) bare-query thin answer

**Symptom.** The bare 2-word Marathi query `कारलाईल कॉटेज` returned a thin,
framing-only answer with **zero citations**, even though the corpus contains a
rich descriptive passage about the cottage.

### ✅ Shipped — WORKS (commit `86bfeda`)
**Intent-tier weight fix.** On `unknown`-intent queries the tier table applied
`{canonical:+0.05, recollections:0.00}`, silently demoting biography/athvani
("recollections") works. Entity/place content lives *in* the biographies, so
this buried the right book (charitra dropped from dense-rank 2 to 35–67).
Changed `unknown` to `{canonical:+0.02, recollections:+0.02}` — no
canonical-vs-biography prior when intent is genuinely unknown.
- Validated on `tools/eval_retrieval.py` gold set: **10 → 11 / 12 PASS**, zero
  doctrinal regressions (canonical works still surface via dense+BM25).
- 16 retrieval unit tests pass. Added a GAP3 gold case (verbose Carlyle query).

### ❌ Ruled out — DO NOT retry without a genuinely new insight
1. **BM25 stopword filtering** (strip Marathi filler so distinctive terms
   dominate). *Wrong channel.* Diagnostics showed dense already ranked the
   target #2; the demotion came from the tier prior, not lexical dilution.
   Never shipped.
2. **Query expansion via embedding max-combine.** Built a full module +
   11 passing tests, then **reverted**. *Disproven:* the rich passage was
   already retrieved (rank ~7), not missing. `np.maximum(bare_vec, expanded_vec)`
   **keeps the bare query's noisy scores as a per-passage floor** — 74 → only 55
   chunks still outrank the target, so junk that spuriously matched the 2 words
   stays high. A *generic* expansion ("…साधना, अध्ययन, महत्त्व…") also pulls in
   unrelated doctrinal works. **Key lesson: max-combine ADDS signal but cannot
   REMOVE the weak-query noise floor.**
3. **Junk-chunk filter (min-length + letter-density).** *Partial only.* Safely
   flags ~209 chunks (1.3%: titles, `## Part N` headings, `<!-- page -->`
   markers, very-low-letter-density garble) with near-zero false-positive risk —
   worth doing as a general cleanup — but it does **not** surface the target,
   because the remaining crowders (village-name lists, raga-notated songs) are
   *legitimate content of their own works*, merely mismatched by a weak query.

### 🔎 Root cause — CONFIRMED
Bare 1–2 word entity queries are a **fundamental weak-signal case**:
- The rich passage exists — `charitra-tatvajnan-tulpule`, chunk **10524**:
  Fergusson College, the ~₹300–400 from editing Carlyle's book, ~1917. It is
  **grounded, not hallucinated** (an earlier claim of hallucination was wrong —
  verified in the source).
- Its cosine to the bare query is only **0.32**, because the cottage is one
  topic buried in a multi-topic chunk (also about illness and family deaths).
  It ranks **#7**.
- Running the real pipeline (MMR, top_k=12, max-2-per-source) offline: **10 of
  the 12 chunks sent to the LLM are OCR-junk or off-topic.** The model honestly
  declines to quote weak passages → thin framing-only answer. This is neither a
  synthesis bug nor a missing passage.
- A **full natural-language question** ("श्री गुरुदेवांनी कार्लाईल कॉटेज का व
  कुठे बांधली, तिचा इतिहास काय?") raises the cosine to **~0.46** and pulls the
  passage into the top-12.

### 💡 Governing mechanism — REPLACE vs. ADD
- **Full question works** — it *replaces* the weak query; the whole ranking is
  recomputed, junk falls, the target rises.
- **Max-combine expansion fails** — it *adds* a vector but retains the bare
  query's noise floor.
- This is why naive expansion ≠ what frontier systems do: they **rewrite/replace**
  the query (and rerank), they don't max-combine a second embedding.

### ➡️ Next directions — from the frontier-techniques research (2026-07-09)
Full write-up: [`rag-frontier-techniques-report.md`](./rag-frontier-techniques-report.md).
Top 3 by impact-to-effort (each independently shippable + gold-validatable):

1. **Cross-encoder reranker over a widened candidate set** (S→M, very high
   impact). Retrieve top 50–100 → RRF → rerank with `BAAI/bge-reranker-v2-m3`
   (multilingual, self-hostable, M3-native) → keep 8–12. MMR optimizes
   *diversity* and structurally cannot rescue a buried-but-relevant passage; a
   cross-encoder re-scores query↔passage relevance from scratch. Decoupling
   retrieval width from final width ensures the buried passage is even present
   to rescue — directly targets the #7-buried-10524 case.
2. **Query understanding — LLM rewriting and/or HyDE, as a retrieval tool**
   (S, very high impact for short queries). The bare-entity failure is a
   *representation* problem (a 2-token vector in a sparse region). Rewriting/HyDE
   moves the search *anchor* into the descriptive-prose neighborhood
   (reproduces the 0.32→~0.46 effect). Categorically different from the failed
   max-combine, which reused the same bad vector. Keep BM25 for exact entity
   match.
3. **OCR junk filtering at index time + query-time length floor** (S, high
   impact). Store a `quality_score`/`junk_flag` from Devanagari-script-ratio
   (<0.5), digit-ratio (>0.2), length gate (<~30 words), Marathi-stopword count.
   Flag-and-downweight, never hard-delete (protects shlokas/aphorisms).

Cross-cutting: per the "OCR Hinders RAG" study, both BM25 and dense BGE-M3
degrade on OCR noise, with corrupted named entities (deity/place/author names)
causing outsized failures — cleaning OCR'd proper nouns before indexing may beat
any retriever swap, and connects to the citation-garble Phase 2 task.

**When we act on this, run it through brainstorming → spec → phased plan.** Do
not big-bang; ship + gold-validate one lever at a time.

### 🧪 How to reproduce (offline, no API)
```
python tools/eval_retrieval.py --top-k 8          # gold baseline
```
Per-query channel diagnosis (dense vs BM25 vs fused rank of a target work/chunk),
and "does the real pipeline send chunk X to the LLM?" — see the recipe in
DEBUGGING-PROTOCOL.md.
