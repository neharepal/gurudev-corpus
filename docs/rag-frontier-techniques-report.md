# Frontier RAG Techniques vs. Our System — Research Report & Prioritized Gap List

**Date:** 2026-07-09
**Scope:** How production AI chatbots / RAG systems achieve high-quality retrieval + answers, and concrete, prioritized upgrades for the Gurudev Ranade / Nimbargi–Inchgeri corpus Q&A app.

---

## Executive summary

Our current pipeline (BGE-M3 dense + BM25 + Reciprocal Rank Fusion + intent reweighting + MMR, top_k=12, Claude synthesis) is a competent **single-shot** RAG stack, but it is missing the three things frontier systems rely on most: (1) a **cross-encoder reranking stage** over a **wide candidate set**, (2) **query understanding** (LLM rewriting / HyDE / retrieval-as-a-tool) so short queries are turned into good queries before they hit the index, and (3) **index-time data-quality filtering** so OCR garbage cannot crowd out real prose. Our two observed failures have precise, well-understood causes and fixes: the **bare 2-word entity query** fails because a 2-token vector lands in a sparse region of embedding space and MMR (a diversity objective) cannot rescue a buried-but-relevant passage — the fix is **query rewriting/HyDE + BM25 + a cross-encoder reranker over a top-50–100 candidate set**. The **OCR-junk-chunk pollution** is fixable with **cheap deterministic index-time heuristics** (script ratio, digit ratio, length gate, Marathi-stopword presence) that flag-and-downweight junk, plus a query-time length floor. The single highest impact-to-effort move is adding a **self-hosted multilingual cross-encoder reranker (`BAAI/bge-reranker-v2-m3`)** with widened retrieval; it directly targets the buried-passage failure and demotes OCR junk, with almost no infrastructure change.

This document assumes no prior context. It covers: how frontier systems work, a prioritized gap list (impact vs. effort), specific recommendations for the two named problems, Marathi/Devanagari+OCR-specific notes, and cited sources throughout.

---

## Our baseline (the thing being compared against)

- **Corpus:** ~16,400 chunks of Marathi/Hindi/English devotional literature about the saint-philosopher Gurudev R. D. Ranade and the Nimbargi/Inchgeri lineage. Much of it is OCR'd Devanagari scans, so there is real OCR noise (garbled text, page markers, tables-of-contents, village-name-list pages as separate chunks).
- **Embeddings:** BGE-M3 (dense, 1024-dim), cosine similarity.
- **Lexical:** BM25 with light Marathi stemming.
- **Fusion:** Reciprocal Rank Fusion (RRF) of dense + BM25.
- **Ranking add-ons:** intent-tier reweighting (doctrinal vs. narrative vs. navigational) added to cosine; MMR reranking; max 2 chunks per source; top_k=12 passages to the LLM.
- **Synthesis:** Claude, strict "quote verbatim, don't hallucinate" prompting.

### Observed weaknesses
1. **Bare/short entity queries fail** (e.g. "Carlyle Cottage"). The descriptive passage exists but its embedding cosine to the short query is only ~0.32 because the entity is one topic buried in a multi-topic chunk; it ranks ~#7 and gets crowded out of top-12 by OCR-junk and off-topic chunks. Full natural-language questions work much better (cosine rises to ~0.46).
2. **OCR/junk chunks pollute retrieval** — headings, page markers, garbled OCR, village-name-list pages spuriously match weak/short queries.
3. **Query expansion via max-combining a second embedding didn't help** — it kept the noisy short-query scores as a floor.

---

## Part 1 — How the frontier systems work (overview)

Modern answer engines (Perplexity, ChatGPT-with-search, Gemini, Claude-grounded systems) differ from a single-shot RAG pipeline along six axes:

1. **Query understanding runs on essentially every query.** A rewrite/reformulation stage sits *before* retrieval — intent classification, entity/synonym expansion, decomposition. The reformulated query often shares <40% of the user's original words. Gemini uses aggressive **query fan-out** (one query → 5–20 independent sub-queries; Gemini 3 averages ~10.7). Perplexity runs a multi-stage retrieve-rank "cascade" with query reformulation. OpenAI's `file_search` "rewrites user queries, breaks complex queries into multiple parallel searches, and runs both keyword and semantic searches." ([Perplexity](https://research.perplexity.ai/articles/architecting-and-evaluating-an-ai-first-search-api), [Gemini fan-out](https://www.seerinteractive.com/insights/gemini-3-query-fan-outs-research), [OpenAI file_search](https://developers.openai.com/api/docs/guides/tools-file-search))

2. **Retrieve wide, then rerank narrow.** Virtually every serious search/RAG system is a two-stage "retrieve-then-rerank": a fast bi-encoder/hybrid retriever pulls top 50–150 candidates, then a **cross-encoder reranker** re-scores down to a tight final set (5–20). The reranker "accounts for most of the pipeline's quality." ([Pinecone rerankers](https://www.pinecone.io/learn/series/rag/rerankers/), [Vespa RAG](https://blog.vespa.ai/rag-perspectives/))

3. **Retrieval is iterative/agentic, not one-shot.** The LLM decides *when* and *what* to search, reads results, reformulates, and searches again (ReAct loop). Anthropic frames retrieval as just a tool call and explicitly advises agents to "start with short, broad queries, evaluate, then progressively narrow." ([Anthropic — Building Effective Agents](https://www.anthropic.com/research/building-effective-agents), [Multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system))

4. **Index-time enrichment.** Anthropic's **Contextual Retrieval** prepends an LLM-generated 50–100 token context blurb to each chunk before embedding and BM25 indexing; reported top-20 retrieval-failure reduction: 35% (contextual embeddings) → 49% (+ contextual BM25) → 67% (+ reranking). ([Anthropic — Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval))

5. **Grounding / citation verification.** Beyond "please cite [1]," production systems extract citations *by construction* (Anthropic Citations API returns `cited_text` spans by index range from the source) or verify claim-level entailment (Google Vertex Check Grounding). ([Claude Citations](https://platform.claude.com/docs/en/build-with-claude/citations), [Vertex Check Grounding](https://docs.cloud.google.com/generative-ai-app-builder/docs/check-grounding))

6. **Data quality is a first-class stage.** Large-scale LLM pipelines apply heuristic quality filters (Gopher/C4/RefinedWeb), language-ID filtering, and layout-aware parsing so headers/TOCs/tables become structure rather than junk text. For Indic/OCR data specifically, AI4Bharat's **Setu/IndicLLMSuite** pipeline is a published template. ([RefinedWeb](https://arxiv.org/abs/2306.01116), [IndicLLMSuite](https://arxiv.org/abs/2403.06350))

---

## Part 2 — Prioritized gap list (highest impact-to-effort first)

Effort key: **S** = hours–days, drop-in; **M** = days–weeks, some new infra/re-index; **L** = weeks+, expensive per-item LLM pass or re-OCR.

| # | Gap in our system | Technique that closes it | Effort | Expected impact |
|---|---|---|---|---|
| **1** | No relevance reranking; MMR optimizes *diversity*, not query-relevance, so a buried-but-relevant passage stays buried. Also top_k=12 is both the retrieval width *and* the final width. | **Cross-encoder reranker** (`BAAI/bge-reranker-v2-m3`, multilingual, ~0.6B, self-hostable). **Widen retrieval to top 50–100 per retriever → RRF → rerank → keep 8–12.** | S→M | **Very high.** The single biggest quality lever in production; directly rescues the #7 buried passage and demotes OCR junk. |
| **2** | No query understanding: the raw 2-token query hits the index unchanged. | **LLM query rewriting** and/or **HyDE**; retrieve with original + rewrite and fuse. Ideally expose retrieval as a **tool** Claude calls with a rewritten query + metadata filters. | S | **Very high** for short/entity queries — reproduces the 0.32→~0.46 behavior we already see with full questions. |
| **3** | OCR junk chunks (headings, page markers, garble, village lists) pollute the candidate pool and win on weak queries. | **Deterministic index-time quality heuristics** (script ratio, digit ratio, length gate, Marathi-stopword presence) → `junk_flag`/`quality_score` in metadata; **query-time length floor + quality-weighted scoring**. | S | **High.** Removes most "junk in top-12" cases with cheap, auditable rules. |
| **4** | No metadata pre-filtering; a Marathi query can dredge English chunks and flagged garble. | **Metadata filters** on `language` / `book` / `author` / `flag_queue` status in the retrieval call. | S | **High**, low cost. Scopes canonical texts, excludes flagged garble. |
| **5** | We embed dense-only from BGE-M3, but BGE-M3 *also* emits learned-sparse and ColBERT multi-vector in the same forward pass — unused. | Use **BGE-M3 learned-sparse** (multilingual, unlike English-only SPLADE/ELSER) alongside/into BM25, and optionally **BGE-M3 ColBERT multi-vector as a reranker** — no new model dependency. | M | **Medium–high**; consolidates 3 techniques into one already-present model. |
| **6** | Multi-topic chunks dilute the entity's embedding (root cause of failure #1). | **Small-to-big / parent-document retrieval**: embed small semantically-split children (undiluted), return the larger parent to Claude. Safest re-chunking option (no LLM, incremental). | M | **Medium–high** for entity recall; complements the reranker. |
| **7** | RRF discards score magnitude, limiting the intent/canonical weighting (RFC-011). | **Normalized convex combination** `α·norm(dense) + (1−α)·norm(sparse)`; a single learned α needs only ~40 labeled queries (Bruch et al.). Keep RRF as fallback. | S→M | **Medium.** Better fusion + a natural home for canonical-priority weighting. |
| **8** | Single-shot retrieval — no recourse when the first search is weak. | **Capped ReAct loop** (2–5 searches): Claude rewrites, re-searches on gaps, self-grades passages (Self-RAG idea, prompt-based, no training). | S→M | **Medium–high** for hard/multi-hop queries; adds latency/cost. |
| **9** | "Quote verbatim" is prompt-only; no verification, and OCR-garbled quotes can slip through. | **Claude Citations API** (spans extracted by index, valid by construction) + a **deterministic quote-substring verifier** (Devanagari-normalize, then exact + `rapidfuzz` fuzzy match against stored source; below threshold → FLAG). Completes the pending citation-garble Phase 2. | S→M | **Medium–high** for trust/faithfulness; near-zero inference cost. |
| **10** | Contextual gaps in chunks (pronouns, "the saint" without naming Ranade). | **Anthropic Contextual Retrieval** (LLM context blurb per chunk, with prompt caching, ~$1/M doc tokens). Its **contextual-BM25** half especially helps OCR'd proper nouns. | M→L | **Medium**; best done incrementally per-book. |
| **11** | Worst scans produce structurally-flattened junk (Tesseract Devanagari is weak). | **Re-OCR with Surya/Marker** (self-hosted, Devanagari-capable, layout-aware) so headings/TOCs/tables emerge as typed structure you can filter, not prose chunks. | L | **Medium–high** at the source; large effort. |
| **12** | Do **not** just raise top_k to "let long context sort it out." | "Lost in the middle" (U-shaped positional bias) means loosely-ranked extra chunks make answers *worse*, not just costlier. Keep the final set tight (8–12); use the reranker as the bridge. | — | Avoids a regression. |

**Skip / traps:** English-only learned-sparse (SPLADE/ELSER); FLARE's logprob mechanism (Claude API doesn't expose token logprobs); trained Self-RAG critic and multi-agent orchestration (overkill at this corpus size); English-only Propositionizer for proposition-indexing (poor fit for multilingual OCR). Step-back prompting is the *wrong direction* for terse entity lookups (it abstracts up, making retrieval less targeted).

---

## Part 3 — Deep dives by topic

### 3.1 Query understanding / rewriting

**Why the bare entity fails (mechanism).** A 2-token query ("Carlyle Cottage") produces a diffuse, under-determined vector roughly equidistant from many chunks; the target multi-topic chunk's *pooled* embedding is dominated by its other topics, so cosine lands at ~0.32. A full question supplies surrounding semantic context that pulls the query vector into the descriptive-prose neighborhood where the passage actually lives (~0.46). **This is a representation problem, not a scoring problem** — which is exactly why max-combining a second embedding's *score* failed: it keeps the noisy 0.32 as a floor and never moves the search *anchor*. Fusion-of-scores ≠ fusion-of-representations.

- **LLM query rewriting** (Effort **S**): rewrite "Carlyle Cottage" → "What was Carlyle Cottage, where was it located, and its significance in Gurudev Ranade's life?", embed the *rewrite*. Moves the anchor into the prose region; also normalizes OCR/transliteration spelling variants (Ranade/Rānaḍe). Risk: drift — keep conservative, retrieve with original + rewrite and fuse. ([Query rewrite in RAG](https://dev.to/yaruyng/query-rewrite-in-rag-systems-why-it-matters-and-how-it-works-3mmd))
- **HyDE — Hypothetical Document Embeddings** (Gao et al., 2022; Effort **S–M**): instruct the LLM to *write a hypothetical answer paragraph*, embed **that**, and search with it. Works because retrieval quality depends on **document-to-document** similarity — a hypothetical answer is prose, like the target, so it matches like-with-like instead of a 2-token fragment against a paragraph. The encoder bottleneck grounds hallucinated specifics. Purpose-built for zero-label/hard-query settings like ours. **Caveat:** for an obscure entity that exists *only* in our OCR text (the LLM has never heard of it), the hypothetical is vague — here BM25 is more reliable. Generate the hypothetical in the corpus language/script. ([HyDE paper, arXiv 2212.10496](https://arxiv.org/abs/2212.10496))
- **Multi-query / RAG-Fusion** (Effort **M**): generate 3–5 query variants, retrieve each, fuse with RRF. Great for complex questions; less useful for a bare entity (all short paraphrases land in the same bad region). ([RAG-Fusion](https://github.com/Raudaschl/rag-fusion))
- **Step-back prompting** (Zheng et al., 2023; Effort **S**): abstracts the query *upward*. Good for over-specific *doctrinal* questions, **wrong direction** for terse entity lookups. ([arXiv 2310.06117](https://arxiv.org/abs/2310.06117))

**For the bare-entity problem specifically:** the winning combination is **BM25 (exact match on the verbatim entity) as the backbone + LLM rewrite and/or HyDE on the dense side + a reranker**. BM25 does not depend on the LLM knowing the entity, which matters for corpus-only obscure names.

Other sources: [Jason Liu — Systematically Improving RAG](https://jxnl.co/writing/2025/01/24/systematically-improving-rag-applications/), [Survey of Query Optimization in LLMs, arXiv 2412.17558](https://arxiv.org/pdf/2412.17558), [freeCodeCamp — contextual embeddings & hybrid search fix retrieval failures](https://www.freecodecamp.org/news/how-contextual-embeddings-and-hybrid-search-fix-retrieval-failures/).

### 3.2 Reranking

**Bi-encoder vs. cross-encoder.** Dense embeddings are *bi-encoders*: query and document are encoded independently and ahead of time, so the document is embedded before the query exists and relevance is never judged against the actual query. A **cross-encoder** concatenates (query, document) and runs them through a transformer together (full cross-attention), outputting one query-conditioned relevance score. Far more accurate, but no caching — one forward pass per pair at query time, so it's a reranker over ~50–150 candidates, not a retriever. ([Pinecone — Rerankers & Two-Stage Retrieval](https://www.pinecone.io/learn/series/rag/rerankers/), [ZeroEntropy — bi- vs cross-encoder](https://zeroentropy.dev/articles/biencoder-vs-crossencoder/))

**Would a cross-encoder rescue the buried #7 passage better than MMR? Yes — and MMR is structurally the wrong tool.** MMR selects each next item to maximize `λ·relevance(q,dᵢ) − (1−λ)·max_sim(dᵢ, already-selected)`. Two problems: (1) its `relevance` term is *still our existing weak RRF score* — MMR adds no new relevance signal; (2) if the buried passage resembles higher-ranked chunks (common — the answer often looks like its neighbors), MMR's diversity penalty pushes it *down*. A cross-encoder throws away the weak first-stage score and **recomputes relevance from scratch** with full attention, with no penalty for resembling neighbors — exactly the "elevate a low-ranked chunk to the top" behavior. **Essential caveat: a reranker can only reorder what it's given.** At #7 the passage is inside 12, so a reranker sees it; but similar failures could leave it at #30. Therefore **decouple retrieval width from final width: retrieve top 50–100, RRF-fuse, rerank down to 12.** Keep MMR only for genuine redundancy (near-duplicate OCR chunks), placed *after* the reranker.

**Model recommendation (self-hosted, multilingual):** `BAAI/bge-reranker-v2-m3` — built on BGE-M3, ~0.6B params (2.27 GB), multilingual (Marathi/Hindi/English), CPU-viable for small batches, GPU-fast otherwise; run via FlagEmbedding (`FlagReranker(..., use_fp16=True)`) or serve via HF Text Embeddings Inference (TEI). Step up to `bge-reranker-v2-gemma` only if the hardest cross-lingual cases need it. `mxbai-rerank-v2` (Apache-2.0, 8k context) is an alternative. Cohere Rerank v3.5 (multilingual, 100+ langs, ~$2/M tokens) is a good *quality ceiling* to benchmark against but is a commercial dependency. ([bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3), [self-host with TEI](https://www.spheron.network/blog/self-host-embedding-reranker-tei-gpu-cloud/), [Cohere Rerank](https://docs.cohere.com/docs/rerank-overview), [mxbai-rerank](https://github.com/mixedbread-ai/mxbai-rerank))

**Late interaction (ColBERT):** a third architecture — one vector per token, pre-computed on the document side; score = sum over query tokens of the max similarity to any document token (MaxSim). Cheaper per candidate than a cross-encoder, more accurate than a bi-encoder. ColBERTv2 + PLAID + RAGatouille make it practical. At our small scale its scalability edge doesn't matter; a cross-encoder gives higher precision with less complexity. Note: **BGE-M3 already emits ColBERT multi-vectors**, so we could use them as a reranker with no new model. ([ColBERTv2, arXiv 2112.01488](https://arxiv.org/pdf/2112.01488), [Weaviate — Late Interaction](https://weaviate.io/blog/late-interaction-overview), [BGE-M3 hybrid+ColBERT sample](https://github.com/yuniko-software/bge-m3-qdrant-sample))

**How much do production systems rely on reranking?** It is now a default stage. Quantified claims: Databricks up to 48% retrieval-quality improvement; Pinecone up to 60% NDCG@10 on FEVER; removing the reranker in one study collapsed NDCG@10 and dropped answer F1 ~30 points. ([Pinecone — Refine with Rerank](https://www.pinecone.io/learn/refine-with-rerank/), [Unstructured — Reranking](https://unstructured.io/blog/improving-retrieval-in-rag-with-reranking), [arXiv 2606.28367](https://arxiv.org/html/2606.28367v1))

### 3.3 Chunking

Root cause of failure #1 is **embedding dilution**: a single vector averages all topics in a multi-topic chunk, drowning the "Carlyle Cottage" signal. Options, ranked by fit:

- **Small-to-big / parent-document retrieval** (Effort **M**, **recommended primary chunking fix**): embed small semantically-split children (tight, undiluted, high cosine to focused queries); the retriever follows a reference and returns the larger *parent* chunk to Claude for context. Attacks dilution exactly at the retrieval vector, keeps synthesis context, needs **no LLM and no English-only tooling** — safest on noisy multilingual OCR. Incremental-friendly: parents = existing chunks, just add a child index + parent docstore. ([Small-to-big retrieval](https://medium.com/data-science/advanced-rag-01-small-to-big-retrieval-172181b396d4))
- **Semantic chunking** (Effort **M**): split on embedding-similarity breakpoints so each chunk is one coherent topic. Directly reduces dilution, but the default sentence splitter is English-centric — **must supply a Devanagari-aware splitter** (danda `।`/`॥`; indic-nlp-library) first, or OCR noise creates spurious boundaries. ([LlamaIndex semantic chunking](https://developers.llamaindex.ai/python/examples/node_parsers/semantic_chunking/), [Kamradt — 5 Levels of Text Splitting](https://github.com/FullStackRetrieval-com/RetrievalTutorials))
- **Sentence-window** (Effort **M**): embed single sentences, expand to a ±k window at synthesis. Max precision but most vectors and most dependent on correct Devanagari sentence segmentation.
- **Propositions / proposition-indexing** (Dense X Retrieval; Effort **L**, **defer**): decompose into atomic self-contained facts, index those. Best theoretical fit — the paper shows a large advantage for **long-tail entities** (our exact case) — but the Propositionizer is **English-only** and running LLM decomposition over noisy multilingual OCR is expensive and error-prone. ([Dense X Retrieval, arXiv 2312.06648](https://arxiv.org/abs/2312.06648))
- **Contextual Retrieval** (Effort **M–L**): note it does **not** primarily fix dilution — prepending a doc-level blurb adds more text to an already-crowded multi-topic vector. Its value here is the **contextual-BM25** half (rare exact terms like "Carlyle Cottage") plus reranking, not de-diluting the dense vector. ([Anthropic — Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval))

**Re-index cost note (16,400 chunks):** small-to-big is incremental (no LLM; add a child index). Semantic re-chunking is a one-time full re-index, gated on fixing Devanagari sentence segmentation. Contextual/propositions require a per-chunk LLM pass — do those per-book, not big-bang. Build the new index alongside the old one, evaluate on held-out entity queries (Recall@20 on queries like "Carlyle Cottage"), then cut over.

### 3.4 Data quality / OCR

**Closest published analog: AI4Bharat's Setu / IndicLLMSuite** — a Devanagari-script pipeline that cleans web + PDF/OCR data, with a ready-made filter stack: mean-line-length filter (removes index/TOC pages), non-Indic character-ratio filter (catches Latin mojibake), symbol-heavy filter, n-gram repetition filters, PDF/OCR page filters (script-confidence, bounding-box overlap, sparse coverage), and a per-language KenLM **perplexity** filter at the 80th percentile. ([IndicLLMSuite, arXiv 2403.06350](https://arxiv.org/abs/2403.06350), [Setu code](https://github.com/AI4Bharat/IndicLLMSuite))

**Heuristic filters (Gopher/RefinedWeb), cheap and deterministic — the mechanisms transfer but thresholds must be adapted for Devanagari:** word count in [50,100000]; symbol-to-word ratio < 0.1; reject if >90% of lines are bullets or >30% end with ellipsis; ≥80% of words contain an alphabetic char; **require ≥2 stopwords** (the highest-signal "is this real prose" check); repetition rejection (duplicate-line fraction 0.30, etc.). RefinedWeb adds line-wise correction: if stripping boilerplate lines removes >5% of a doc, drop it. ([Gopher thresholds](https://mbrenndoerfer.com/writing/quality-filtering-heuristic-perplexity-classifier-thresholds), [RefinedWeb, arXiv 2306.01116](https://arxiv.org/abs/2306.01116))

**Language ID:** fastText `lid.176` to drop *clearly non-Indic* garble (keep if top-1 confidence ≥ ~0.5–0.65). Caveats: unreliable on very short text (length-gate first), and **Marathi vs. Hindi are frequently confused** (same script) — use LID to drop non-Indic garble, not to enforce mr-vs-hi. ([fastText LID](https://huggingface.co/facebook/fasttext-language-identification), [NeMo Curator language filter](https://docs.nvidia.com/nemo/curator/latest/curate-text/process-data/language-management/language.html))

**Layout-aware parsing (fixes junk at the source):** re-OCR the worst scans with **Surya** (90+ langs incl. Devanagari; detection + recognition + layout + reading order + tables) / **Marker** (PDF→markdown preserving headings/tables; ~95.7% benchmark). Then TOCs/headers/page-numbers come out as *typed structure to filter*, not prose chunks. Google Document AI (cloud, Devanagari-capable) is highest raw accuracy; Unstructured.io partitions into typed elements (Title/Header/Footer/PageNumber/ListItem/Table/NarrativeText) you can drop structurally. Tesseract (likely current) is weak on poor Devanagari scans — the documented source of our garble. ([Surya](https://github.com/datalab-to/surya), [Marker](https://github.com/datalab-to/marker), [parser benchmark](https://www.firecrawl.dev/blog/best-pdf-parsers), [Tesseract Devanagari limits](https://github.com/tesseract-ocr/tessdata/issues/67))

**OCR post-correction with an LLM is mixed** — some report >54–60% CER reduction, but "No Free Lunches" (arXiv 2502.01205) finds LLMs often *degrade* quality and hallucinate on lower-resource scripts. Recommendation: run **offline, batched, gated by a garble score**, only on salvageable-but-dirty pages, always keep the original, and spot-check. Not a query-time operation. ([No Free Lunches, arXiv 2502.01205](https://arxiv.org/html/2502.01205v1))

**"OCR Hinders RAG" (arXiv 2412.02592):** both BM25 *and* dense BGE-M3 degrade substantially on OCR noise, and **named-entity corruption (deity/place/author names) causes outsized failures**. Implication: **cleaning OCR'd proper nouns before indexing likely beats any retriever swap.** ([arXiv 2412.02592](https://arxiv.org/html/2412.02592v2))

### 3.5 Overall architecture gaps

- **Agentic / iterative retrieval** (ReAct, arXiv 2210.03629; Self-RAG idea, arXiv 2310.11511): put Claude in a capped search→read→reformulate→search loop, self-grading passages and re-searching on gaps. Native to Claude via tool use; no training. Cost: 2–6× latency. Add agency only where it helps. ([ReAct](https://arxiv.org/abs/2210.03629), [Self-RAG](https://arxiv.org/abs/2310.11511))
- **Retrieval as a tool / function calling:** a single `search_corpus(query, book, author, language)` tool lets Claude write a rewritten query + metadata filters and issue parallel searches. Low effort, high leverage.
- **Multi-hop** (IRCoT arXiv 2212.10509; self-ask arXiv 2210.03350): later hops retrieve documents the original query couldn't surface (teacher → lineage → doctrine). Native to Claude in a ReAct loop.
- **Long context is not a substitute for ranking:** "lost in the middle" (Liu et al., arXiv 2307.03172) — U-shaped positional bias; at 20–30 loosely-ranked docs, accuracy can fall below closed-book. RULER (arXiv 2404.06654): effective context is ~50–65% of the marketed window. **Widen retrieval, narrow what reaches Claude.** Enable prompt caching on the stable system prefix. ([Lost in the Middle](https://arxiv.org/abs/2307.03172), [Databricks long-context RAG](https://www.databricks.com/blog/long-context-rag-performance-llms))
- **Grounding / citation verification:** **Claude Citations API** returns `cited_text` spans extracted by index range from the source (valid substrings by construction; don't count as output tokens; work with caching). A factual sentence returned *without* a citation flags a likely hallucination; a garbled quote can only enter if the *stored source* is OCR-corrupt — reframing detection to our existing `flag_queue`. Add a **deterministic quote-substring verifier** (Devanagari-normalize → exact + `rapidfuzz partial_ratio` fuzzy match against stored source; below threshold → FLAG → source repair) — this is the detection half of the pending citation-garble Phase 2. Note: image-only scanned PDFs aren't citable; feed the OCR'd text. Offline eval: RAGAS faithfulness, TruLens RAG Triad, DeepEval. ([Claude Citations](https://platform.claude.com/docs/en/build-with-claude/citations), [RAGAS, arXiv 2309.15217](https://arxiv.org/abs/2309.15217))
- **Fusion beyond RRF:** RRF fuses on rank only, discarding magnitude. Normalized convex combination `α·norm(dense)+(1−α)·norm(sparse)` beats RRF and a learned α needs only ~40 labeled queries (Bruch et al., arXiv 2210.11934) — a natural home for RFC-011 intent/canonical weighting. Avoid English-only learned-sparse (SPLADE/ELSER); use BGE-M3's multilingual sparse head instead. ([Bruch et al., arXiv 2210.11934](https://arxiv.org/abs/2210.11934))

---

## Part 4 — Specific recommendations for the two named problems

### Problem A — "bare 2-word entity query" (e.g. "Carlyle Cottage")

Root cause: a 2-token vector lands in a sparse embedding region; the target is diluted inside a multi-topic chunk; MMR (diversity) cannot rescue it; max-combining scores keeps the bad 0.32 as a floor. Fix by **changing the search representation and adding a relevance reranker**, in this order:

1. **BM25 as the backbone for exact entity match** — "Carlyle Cottage" appears verbatim; lexical match nails it regardless of embedding geometry. (Already present; ensure it's weighted enough and not diluted by the length-normalization for short queries.)
2. **LLM query rewriting and/or HyDE** on the dense side — turn the 2 words into a full-prose query/hypothetical-passage so the anchor lands in the descriptive-prose neighborhood (the 0.32→~0.46 effect we already observe). Retrieve with original + rewrite and fuse.
3. **Widen retrieval to top 50–100, then cross-encoder rerank (`bge-reranker-v2-m3`) down to 12** — guarantees the buried passage is *present* and promotes it on true query-passage relevance.
4. **Small-to-big chunking** (medium-term) so the entity gets its own undiluted child vector.
5. Expose all of the above as a **retrieval tool** so Claude can reformulate and re-search if the first pass is thin.

This is categorically different from the failed max-combine: it moves *where* we search (rewrite/HyDE) and *re-scores* candidates (cross-encoder), rather than adjusting scores derived from the same bad vector.

### Problem B — "OCR junk chunks crowd out real passages on weak queries"

Two layers — filter at index time, guard at query time. Flag-and-downweight (do **not** hard-delete) to limit false positives.

**Index-time metadata (`junk_flag` + `quality_score`), cheap deterministic rules (tune on ~100 hand-labeled chunks):**
1. **Devanagari script ratio** = Devanagari chars / non-space-non-digit chars → flag if **< 0.5** (Latin mojibake, symbol garble).
2. **Digit ratio** > **0.2** → flag (page numbers, TOCs, census/village-population lists).
3. **Length gate** — flag chunks **< ~30 words / < ~200 chars** (the biggest single lever; these spuriously match short queries).
4. **Marathi stopword presence** — require **≥2** of आणि/आहे/या/तो/हे/मध्ये/पण/व/की/नाही (best "coherent prose vs. list/heading" discriminator).
5. Symbol-to-word ratio > 0.1 or alphabetic-char ratio < 0.7 → flag (Gopher).
6. Line-level boilerplate strip (pure digits/punctuation, lone `॥`/`।`); if >30% removed → flag.
7. Corpus **dedup** of near-identical chunks (repeated running headers) at similarity > ~0.9.
8. Mojibake validity: U+FFFD, orphaned combining marks, high rare-codepoint ratio → flag.

A chunk failing ≥2 of {1,2,4,5} is almost certainly junk; failing only the length gate is "suspect" (down-weight, don't drop).

**Query-time guards:**
- **Hard length floor** on the candidate pool (or a small quota for short chunks).
- **Quality-weighted scoring:** multiply similarity by `quality_score` (×0.4–0.6 for flagged), so junk surfaces only when nothing better exists.
- **Cross-encoder rerank** naturally demotes junk in the top-k.

**False-positive danger zone:** legitimate *short* content — aphorisms, Sanskrit shlokas/verse (low Marathi-stopword count, unusual word lengths), definitions. Mitigate: flag-and-downweight (never delete); exempt verse/quote regions (via Sanskrit LID label or verse layout tag) from the stopword/word-length checks; audit which flags fire.

**Root-cause option (larger effort):** re-OCR the worst scans with Surya/Marker so headers/TOCs/tables never become prose chunks; optional gated LLM post-correction on salvageable pages. And per "OCR Hinders RAG," **prioritize cleaning OCR'd proper nouns** — that likely beats any retriever change.

---

## Part 5 — What specifically helps Marathi/Devanagari + OCR-noisy corpora

- **Multilingual models over English-only ones:** `bge-reranker-v2-m3` (reranker) and BGE-M3 (embeddings + multilingual sparse + ColBERT) genuinely support Marathi/Hindi; **avoid SPLADE/ELSER and the English-only Propositionizer.** Benchmark against L3Cube [MahaSBERT/HindSBERT](https://huggingface.co/l3cube-pune/marathi-sentence-similarity-sbert).
- **Devanagari-aware sentence segmentation** (danda `।`/`॥`, indic-nlp-library) is a prerequisite for semantic/sentence-window chunking; naive English splitters mis-segment.
- **Devanagari-tuned quality heuristics:** script-ratio, digit-ratio, Marathi-stopword presence; do **not** reuse English mean-word-length thresholds (Unicode base+matra+halant behaves differently; OCR without space recovery makes very long "words").
- **Language ID for garble removal only** — fastText drops non-Indic mojibake, but don't use it to separate Marathi from Hindi (frequently confused).
- **Layout-aware Devanagari OCR:** Surya/Marker (self-hosted) and Google Document AI (cloud) support Devanagari and emit structure; Tesseract is the weak link.
- **HyDE/query rewriting in-script** normalizes transliteration/spelling variants of Devanagari names — a real OCR problem.
- **Grounding for OCR text:** the deterministic quote verifier must **Devanagari-normalize (NFC, handle nukta/matra) before fuzzy-matching**; the Citations API needs the OCR'd text (image-only scans aren't citable).
- **Empirical warning:** both BM25 and dense BGE-M3 degrade on OCR noise, and **named-entity (deity/place/author-name) corruption causes outsized failures** — cleaning proper nouns is high-leverage. ([OCR Hinders RAG, arXiv 2412.02592](https://arxiv.org/html/2412.02592v2))

---

## Consolidated source list

**Query understanding:** [HyDE 2212.10496](https://arxiv.org/abs/2212.10496) · [Step-back 2310.06117](https://arxiv.org/abs/2310.06117) · [RAG-Fusion](https://github.com/Raudaschl/rag-fusion) · [Query rewrite in RAG](https://dev.to/yaruyng/query-rewrite-in-rag-systems-why-it-matters-and-how-it-works-3mmd) · [Query Optimization survey 2412.17558](https://arxiv.org/pdf/2412.17558) · [Jason Liu — Systematically Improving RAG](https://jxnl.co/writing/2025/01/24/systematically-improving-rag-applications/) · [Perplexity architecture](https://research.perplexity.ai/articles/architecting-and-evaluating-an-ai-first-search-api) · [Gemini query fan-out](https://www.seerinteractive.com/insights/gemini-3-query-fan-outs-research) · [OpenAI file_search](https://developers.openai.com/api/docs/guides/tools-file-search)

**Reranking:** [Pinecone rerankers](https://www.pinecone.io/learn/series/rag/rerankers/) · [ZeroEntropy bi- vs cross-encoder](https://zeroentropy.dev/articles/biencoder-vs-crossencoder/) · [bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3) · [self-host with TEI](https://www.spheron.network/blog/self-host-embedding-reranker-tei-gpu-cloud/) · [Cohere Rerank](https://docs.cohere.com/docs/rerank-overview) · [mxbai-rerank](https://github.com/mixedbread-ai/mxbai-rerank) · [ColBERTv2 2112.01488](https://arxiv.org/pdf/2112.01488) · [PLAID 2205.09707](https://arxiv.org/pdf/2205.09707) · [Weaviate late interaction](https://weaviate.io/blog/late-interaction-overview) · [Unstructured reranking](https://unstructured.io/blog/improving-retrieval-in-rag-with-reranking) · [arXiv 2606.28367](https://arxiv.org/html/2606.28367v1)

**Chunking:** [Anthropic Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval) · [Contextual embeddings cookbook](https://platform.claude.com/cookbook/capabilities-contextual-embeddings-guide) · [Dense X Retrieval 2312.06648](https://arxiv.org/abs/2312.06648) · [LlamaIndex semantic chunking](https://developers.llamaindex.ai/python/examples/node_parsers/semantic_chunking/) · [Kamradt 5 Levels](https://github.com/FullStackRetrieval-com/RetrievalTutorials) · [Small-to-big retrieval](https://medium.com/data-science/advanced-rag-01-small-to-big-retrieval-172181b396d4) · [Sentence-window](https://developers.llamaindex.ai/python/framework-api-reference/node_parsers/sentence_window/) · [Simon Willison on Contextual Retrieval](https://simonwillison.net/2024/Sep/20/introducing-contextual-retrieval/)

**Data quality / OCR:** [RefinedWeb 2306.01116](https://arxiv.org/abs/2306.01116) · [Gopher thresholds](https://mbrenndoerfer.com/writing/quality-filtering-heuristic-perplexity-classifier-thresholds) · [Gopher explainer](https://medium.com/dair-ai/papers-explained-47-gopher-2e71bbef9e87) · [CCNet 1911.00359](https://ar5iv.labs.arxiv.org/html/1911.00359) · [fastText LID](https://huggingface.co/facebook/fasttext-language-identification) · [NeMo Curator language filter](https://docs.nvidia.com/nemo/curator/latest/curate-text/process-data/language-management/language.html) · [OCR post-correction: No Free Lunches 2502.01205](https://arxiv.org/html/2502.01205v1) · [Post-OCR with Llama](https://aclanthology.org/2024.lt4hala-1.14/) · [Surya OCR](https://github.com/datalab-to/surya) · [Marker](https://github.com/datalab-to/marker) · [Google Document AI](https://cloud.google.com/document-ai) · [PDF parser benchmark](https://www.firecrawl.dev/blog/best-pdf-parsers) · [Tesseract Devanagari limits](https://github.com/tesseract-ocr/tessdata/issues/67) · [IndicLLMSuite 2403.06350](https://arxiv.org/abs/2403.06350) · [Setu code](https://github.com/AI4Bharat/IndicLLMSuite) · [ChunkRAG 2410.19572](https://arxiv.org/html/2410.19572v5) · [Chunking best practices](https://airbyte.com/agentic-data/ag-document-chunking-best-practices)

**Architecture:** [ReAct 2210.03629](https://arxiv.org/abs/2210.03629) · [Self-RAG 2310.11511](https://arxiv.org/abs/2310.11511) · [FLARE 2305.06983](https://arxiv.org/abs/2305.06983) · [IRCoT 2212.10509](https://arxiv.org/html/2212.10509v2) · [self-ask 2210.03350](https://arxiv.org/abs/2210.03350) · [Anthropic Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) · [Anthropic Multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) · [Lost in the Middle 2307.03172](https://arxiv.org/abs/2307.03172) · [Databricks long-context RAG](https://www.databricks.com/blog/long-context-rag-performance-llms) · [RULER 2404.06654](https://arxiv.org/abs/2404.06654) · [Claude Citations API](https://platform.claude.com/docs/en/build-with-claude/citations) · [Vertex Check Grounding](https://docs.cloud.google.com/generative-ai-app-builder/docs/check-grounding) · [RAGAS 2309.15217](https://arxiv.org/abs/2309.15217) · [TruLens RAG Triad](https://www.trulens.org/getting_started/core_concepts/rag_triad/) · [Normalized fusion, Bruch et al. 2210.11934](https://arxiv.org/abs/2210.11934) · [BGE-M3 2402.03216](https://arxiv.org/abs/2402.03216) · [BGE-M3 hybrid+ColBERT sample](https://github.com/yuniko-software/bge-m3-qdrant-sample) · [OCR Hinders RAG 2412.02592](https://arxiv.org/html/2412.02592v2) · [L3Cube Marathi/Hindi SBERT](https://huggingface.co/l3cube-pune/marathi-sentence-similarity-sbert) · [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
