# RFC-018: Cross-reference citation-alias index

**Status:** DRAFT 2026-07-18
**Author:** Neha (with Claude)
**Created:** 2026-07-18
**Related:** RFC-014 (retrieval/grounding), RFC-017 (small-to-big chunking + arthasahit)

## Summary

Build an ingestion-time index that, for every chunk in a **container work**
(compilation, anthology, biography, arthasahit edition), identifies whether
that chunk contains a verbatim (or near-verbatim) quotation of a passage in
one of Gurudev's **original works** in the corpus (Pathway to God series,
Parmartha Sopan, Constructive Survey, Vedanta, Mysticism in Maharashtra,
etc.). When a strong match is found, the container-chunk's meta gains a
`citation_alias` pointer to the original chunk. At citation time, splice
consults the alias and re-attributes the citation to the ORIGINAL work,
never the container — because attributing a Pathway-to-God passage to the
anthology that reproduces it would be misleading.

The compilation chunk's own text stays in the retrieval index unchanged (its
meanings and framing boost recall in RFC-017 `embed_text`); only the
citation surface swaps.

## Motivation

Right now, sadhaks asking "what did Gurudev say about bhakti?" can retrieve
matching passages from three overlapping places:

1. `pathway-to-god-in-hindi-literature` (original) — Gurudev's own writing.
2. `sadhak-bodh` (Kakasaheb's compilation) — reproduces the same paragraph
   as a section epigraph.
3. `charitra-tatvajnan-tulpule` (biography) — quotes the same paragraph
   verbatim inside a biographical section.

Under RFC-014 alone, all three surface in the top-k. RFC-017 dedupes to
distinct parents. Neither answers the citation question: **which one does
the reader see?** Currently:

- Prompt-side rule (from today's push): the answer LLM is told "prefer the
  original if it recognises one." Works when the model can spot the source
  in-context; misses when it can't (~20-40% of cases in eyeball tests).
- Human review flags the mis-attribution → Neha corrects it in
  `03_catalog/flag_queue.yaml` after the fact. Doesn't scale.

For the arthasahit works this is even sharper: their explanations are
"pulled from Gurudev's Pathway-to-God-series if available, otherwise from
reputed Marathi sources." A meaning that IS Gurudev's own — sitting inside
`tukaram-vachanamrut-arthasahit` — should cite `pathway-to-god` when
retrieved. The container's role is just to help discovery.

## Goals

- **Every citation resolves to the most authoritative source we hold.**
- **Zero LLM guessing** about which work is the original — the mapping is
  computed offline, from the text itself.
- **Precision-first**: false-positive alias (mis-attribution) is worse than
  false-negative (we miss the re-attribution and cite the container). A
  missed alias is recoverable via prompt + human flag; a wrong alias is a
  quiet integrity bug.
- **Additive to RFC-017**: compilation chunks stay in retrieval unchanged.
  Only the citation surface swaps.
- **Ingestion cost** measured in minutes-to-tens-of-minutes per full corpus
  pass, not hours — runs alongside the embedder.

## Non-goals

- Not a full plagiarism-detector: we only care about matches WHERE THE
  CONTAINER LEGITIMATELY EXCERPTS AN ORIGINAL Gurudev work in our corpus.
- Not cross-lingual: an English quote of a Marathi passage does NOT get
  aliased; different work IDs, different citations. Same-language matching
  only (future extension possible).
- Not chunk-level dedup at query time: retrieval still returns compilation
  chunks. Alias only affects the citation surface.

## Proposed design

### 1. Data model

Two new artifacts alongside `04_processed/chunks.jsonl`:

**`04_processed/citation_aliases.jsonl`** — one line per aliased chunk:

    {
      "chunk_id": "sadhak-bodh--mr--0042--003",
      "alias": {
        "work_id": "pathway-to-god-in-hindi-literature",
        "chunk_id": "pathway-to-god-in-hindi-literature--en--0087--001",
        "match": {
          "confidence": 0.94,
          "type": "lexical+semantic",
          "n_gram_overlap": 0.72,
          "semantic_cosine": 0.91,
          "match_span": [45, 320]
        }
      }
    }

The alias points to a specific ORIGINAL chunk, not just the work — so
splice can offer a precise `Read in full` link (page-accurate, via the
original chunk's `source_path` + `char_start`).

**`03_catalog/work_roles.yaml`** — declares which works are containers vs
originals for the purpose of alias resolution:

    originals:
      # Gurudev's own writings — targets of alias re-attribution.
      - pathway-to-god-in-hindi-literature
      - pathway-to-god-in-kannada-literature
      - pathway-to-god-in-the-vedas
      - parmartha-sopan
      - parmartha-mandir
      - vedant
      - constructive-survey-of-upanishadic-philosophy
      - mysticism-in-maharashtra
      # ... (populated from docs/authorship-audit-2026-07-11.md "verified OK")

    containers:
      # Works that may reproduce originals verbatim.
      # Alias resolution runs FROM these TO originals.
      - sadhak-bodh
      - charitra-tatvajnan-tulpule
      - gurudev-paramarthik-shikvan
      - amar-sandesh-sudha
      - dhyangita-anvayarth
      - kakanchi-pravachane
      - kakanchi-charcha
      # Arthasahit editions — bulk-added:
      - tukaram-vachanamrut
      - eknath-vachanamrut
      - ramdas-vachanamrut
      - sant-vachanamrut
      - jnaneshwar-vachanamrut
      - eknathi-bhagvat-vachanamrut
      - dhyanopakarani-gita

### 2. Detection pipeline

`tools/build_citation_aliases.py` runs after `tools/embedder.py`:

    1. Read work_roles.yaml → get {originals: [ids...], containers: [ids...]}.
    2. Build a per-language BM25 index over ONLY the originals' chunks.
    3. For each container chunk:
        a. LEXICAL PRE-FILTER: query the originals' BM25 with the chunk text.
           Take top-8 candidates.
        b. For each candidate, compute:
           - Character 5-gram Jaccard overlap between container chunk and
             candidate original chunk.
           - Cosine similarity of their pre-computed BGE-M3 embeddings.
        c. Score = 0.5 * jaccard + 0.5 * cosine.
        d. If score >= 0.82 AND jaccard >= 0.55 (both required — belt +
           suspenders) → alias declared.
        e. Emit one line to citation_aliases.jsonl with the metrics.
    4. Sanity report at end: N chunks scanned, N_alias declared, mean
       confidence, top-10 sampled aliases with their text pairs for manual
       spot-check.

Same-language only. Container chunk language must match original chunk
language (cross-lingual left for future work).

**Why both thresholds?**
- Cosine ~0.9 alone catches near-paraphrases; would over-match on topical
  similarity ("both talk about bhakti") without lexical overlap.
- Jaccard alone misses OCR-varied wording (a Devanagari OCR pass that hyphenated
  differently vs the same text elsewhere).
- Requiring both is precision-first: we'd rather miss an alias than
  mis-attribute.

### 3. Integration with splice (RFC-017 refinement)

`tools/schemas.py::splice_quote_dict` gains one new step, guarded by the
alias index:

    # Load once at process start via server.STATE.aliases (jsonl → dict).
    alias = STATE.aliases.get(meta["id"])
    if alias:
        original_work_id = alias["alias"]["work_id"]
        original_chunk_id = alias["alias"]["chunk_id"]
        # Swap the citation's attribution to the original work.
        # Body stays the container's spliced text (it's the passage that
        # was retrieved), but attribution now points to the source.
        original_meta = STATE.meta_by_chunk_id.get(original_chunk_id)
        if original_meta is not None:
            quote["workTitle"] = original_meta.get("title") or ""
            quote["workId"]    = original_work_id
            quote["author"]    = original_meta.get("author") or ""
            quote["location"]  = original_meta.get("location") or ""
            # readPage / Read-in-full still needs to land somewhere real —
            # prefer the original's source_path when the same body exists
            # there; fall back to container's source_path on failure.
            quote["_readpage_source_path"] = original_meta.get("source_path")

The container's own metadata is preserved on the chunk row (used for
`/admin/flags` correction workflows — the operator still needs to know
which physical page of `sadhak-bodh` a citation came from). Only the
sadhak-facing citation swaps.

### 4. Prompt refinement

The prompt-side rule added today ("cite the original, never the anthology")
remains — with the alias index, it becomes a belt-and-suspenders redundancy
for cases the matcher missed (short quotations, paraphrases, cross-lingual).

### 5. Ops

- **Runs once per full re-embed** (or manually via
  `python tools/build_citation_aliases.py --restart`).
- **Incremental mode**: `--work-id <container-id>` — recomputes aliases
  for a single container. Used after ingesting a new arthasahit or bio.
- **Updates on originals**: adding a new "original" work triggers a re-scan
  of ALL containers (since new original passages might now match old
  container chunks). Rare event; full pass is <30 min at expected corpus size.
- **Backup**: `citation_aliases.jsonl` is small enough (~1-2 MB expected)
  to check into git under `04_processed/` — same as `chunks_meta.jsonl`
  before Phase 2. Reviewable in git history.

### 6. Human-in-the-loop review

Every alias declaration is a public artifact. The maintainer dashboard
(`/admin/aliases`, new) lists all declared aliases with:

- Container work + chunk excerpt
- Aliased original work + chunk excerpt
- Jaccard + cosine + combined score
- **Approve / Reject / Move to different original** buttons

Rejected aliases go into a persistent block-list at
`03_catalog/citation_alias_overrides.yaml` so the next re-scan doesn't
re-declare them. Approved aliases stay in `citation_aliases.jsonl`.

This mirrors the RFC-004 flag-queue pattern — automated candidates,
maintainer review, immutable overrides.

## Alternatives considered

- **Runtime alias resolution** (query-time matcher): every /ask does a
  matcher pass over its top-k. Rejected — adds ~100ms per query and CPU
  cost, and 90% of the work is redundant across queries.
- **Exact-match hash** (SHA of chunk text): fast but misses everything
  except byte-identical duplicates. Real container quotations are almost
  never byte-identical due to OCR variation, punctuation cleanup, and
  slight editorial paraphrasing.
- **LLM-driven annotator**: pass every container chunk through Claude and
  ask "is this quoted from any of {list of originals}?". Precise but slow
  (~30 min per 1000 chunks) and expensive ($20-40 per full pass). Reject
  as the PRIMARY mechanism; may re-visit as a spot-check tool for the
  human-review dashboard (e.g., "explain this match").
- **Vector-DB dedup** (via faiss/annoy): use pure cosine over the existing
  embeddings, top-k, threshold. Simpler than lexical+semantic. Rejected
  because embeddings alone over-match on TOPICAL similarity — two
  passages "about namasmarana" score high without being the same
  passage. Jaccard is the check against that failure mode.
- **Automatic surfacing** — when a compilation chunk with alias would rank
  top-k, replace it with the ORIGINAL's chunk in the ranking. Rejected
  for now because the container's chunk may be MORE RELEVANT (its
  additional context / gloss aided the retrieval); we want to keep it as
  a retrieval signal while redirecting attribution.

## Tradeoffs & risks

1. **Precision beats recall.** We miss 5-10% of legitimate aliases (short
   quotations, cross-lingual reproductions) — but we don't wrongly
   attribute a Pathway-to-God passage. Missed aliases still get caught by
   the prompt-side rule for cases the model can identify.
2. **Ingestion complexity.** One more artifact to keep in sync
   (`citation_aliases.jsonl`). Documented and versioned in git; the
   `--restart` flag rebuilds from scratch.
3. **Cold-start on new originals.** Adding a new original work requires a
   full container re-scan. Cost bounded (<30 min); documented ops.
4. **Human-review burden.** Every alias needs approval to become
   authoritative. For the initial ~200 aliases we expect from the current
   corpus + the 7 arthasahit books, this is a one-time review effort
   (~1-2 hours). Steady-state should be low (new works land occasionally).
5. **False confidence on cross-work paraphrases.** Two authors describing
   the same lineage teaching in similar Marathi may cross the semantic
   threshold. Jaccard requirement stops most; the human-review dashboard
   catches the rest.

## Open questions

1. **Chunk-level vs work-level alias.** Chunk-level enables precise
   `Read in full` deep links; work-level is simpler and sufficient for
   attribution alone. Design above uses chunk-level; can be relaxed if
   splice code becomes hairy.
2. **Should the alias's "match_span" (character offsets into container
   chunk) drive body-splicing** — i.e. quote ONLY the matched portion, not
   the container chunk's full text? Cleaner citations but adds another
   layer of edge cases (matched span vs LLM's quoteStart/quoteEnd
   preference). Defer to v2.
3. **Cross-lingual alias** (a Marathi verse rendered in Kannada-language
   Pathway-to-God). Same core algorithm with a translation pass on the
   query side, but adds hallucination risk. Defer to a separate RFC.
4. **Threshold tuning.** The 0.82 combined / 0.55 jaccard cutoffs are
   priors from small-N eyeball tests on existing sadhak-bodh /
   charitra-tatvajnan cross-references. First run should include a
   confidence histogram + top-30 borderline aliases for manual
   threshold-tuning before we lock the numbers.

## References

- RFC-014 (retrieval/grounding re-arch): defines the citation contract
  this RFC modifies.
- RFC-017 (small-to-big + arthasahit): motivated the `restrict_to_cite`
  mechanism that this RFC generalises.
- `docs/authorship-audit-2026-07-11.md`: authoritative list of container
  vs. original works from the Intel-Mac preface-review pass.
- ADR-007 (quote-first curation): the "citations are the answer" principle
  this RFC serves.
- `03_catalog/flag_queue.yaml`: precedent for the maintainer-review
  pattern this RFC's `/admin/aliases` mirrors.
