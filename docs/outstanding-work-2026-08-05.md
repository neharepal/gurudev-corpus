# Corpus outstanding-work audit — 2026-08-05

Owner: Neha Repal · Compiled from four parallel audit passes plus session-state notes.
Companion tracker (HTML, checkable): see the Artifact link in this session.
Sister audits still current (do not re-read from scratch): `docs/corpus-coverage-audit-2026-06-17.md`, `docs/authorship-audit-2026-07-11.md`, `docs/toc-readiness-audit-2026-08-01.md`, `docs/ocr-quality-audit-2026-07-14.md`. **Stale (do not trust):** `docs/missing-titles-checklist.md` still lists the five Vachanamruts as un-chunked — they are chunked, they're just missing from the catalog. See Area A.

## Snapshot

- **Devanagari OCR campaign** — nearly complete. 4 books remain (1 assembly-only, 1 unblocked, 2 blocked on source PDFs).
- **Catalog coverage** — 34 works on disk are missing from `03_catalog/catalog.yaml`, including MiM and the five Vachanamruts. All are indexed and citable via `/ask` but invisible in the reader's `/works` picker.
- **ToC restoration** — 12 books ready to add to the allow-list (have clean `##` headings); 7 books need normalization first; 18 main-source books still have zero hierarchy. Nityanemavali being finished in-session.
- **User-visible bugs** — two live regressions (markdown not rendering; reading-mode links not clickable) plus a design request (drop always-cite in Reading Mode).

---

## Urgent items (resolve this session or next)

### U1 — Markdown regression: `**bold**` shows literally
Root cause is HIGH confidence. Three JSX sites render text directly instead of through `renderInlineMd`:
- `chat-app/app/chat/page.tsx:1000` — doctrinal `framingParagraphs.map({para})` unwrapped.
- `chat-app/app/chat/page.tsx:1020` — per-citation `{c.whyChosen}` unwrapped.
- `chat-app/app/read/[slug]/page.tsx:1333` — same `whyChosen` unwrapped in Reading Mode.

**Why now:** Commit `4d170da` (2026-08-04, woven-prose Q&A) moved `whyChosen` from below-quote muted text to ABOVE the quote as connective prose — same raw render, now at the visual center. The earlier `43dde13` commit claimed to fix this class of bug but only patched one of three sites.

**Prompt contract:** `tools/prompts.py:61` explicitly tells the LLM these fields accept inline `**bold**`/`*italic*`, so the LLM emits them.

**Fix:** three one-line `renderInlineMd(...)` wraps + a `chat-app/lib/render-inline-md.test.ts` regression pin so the third-site variant doesn't recur.

### U2 — Reading Mode Q&A links not clickable
Being diagnosed in parallel. Suspects: (a) inline-variant attribution rendered as `<span>` instead of `<a>`; (b) href produced by `buildReadHref` is empty/invalid; (c) parent `onClick` capturing/preventDefault; (d) CSS `pointer-events: none` on `.gd-quote-inline`. Fix scoped to Reading Mode; Chat Mode citations still work.

### U3 — Reading Mode Q&A answer-format redesign
Neha's ask (2026-08-05): drop the always-cite constraint. Rationale: the reader is already on the page, so citation cards duplicate what's on-screen. New shape: plain answer text; add links only when the answer needs to jump the reader somewhere they aren't. This changes the LLM prompt, the response schema, the frontend renderer, and possibly the retrieval flow. **Deserves its own RFC** — do not design inline. Draft as `docs/rfc/RFC-023-reading-mode-answer-format.md`.

### U4 — Nityanemavali ToC finish
**Applied (awaiting Neha's review + commit).** All 27 headings inserted (21 `##` + 6 `###`) at verified anchors. `nityanemavali` added to `TOC_ALLOWED_SLUGS`. `tsc --noEmit` passes. No source content modified. File grew 3927→3973 lines. Three known anomalies preserved (no source edits): section 9 body has OCR-corrupt `खी.` for `रवी.` (L1354); body spells `भारुडे` where TOC/heading uses `भारूडे`; body spells `पालणे` where TOC/heading uses `पाळणे`. Neha reviews and commits.

### U5 — "Back to answer" recomputes instead of loading saved answer
Recent regression per Neha (2026-08-05). Clicking the "back to answer" affordance should restore the previously-computed answer from local state; instead it re-hits `/api/ask` and re-runs the LLM. Wastes tokens + user time. Under investigation. Likely tied to a router/state refactor after the last answer-shape change; suspects: (a) answer cache eviction on navigation, (b) `router.push` vs `router.back` behavior, (c) session-storage key mismatch after schema tweaks.

### U6 — Marathi-tagged books display roman titles in the picker
Per Neha (2026-08-05). Books whose `language` (or `languages: [mr]`) marks them as Marathi are still showing English/roman titles in the reader picker. Yesterday's title unification pass fixed 19 books (17 catalog + bodhsudha + nityanemavali) — but there are ~24 more Marathi works whose `meta.yaml title:` is still roman (many of them not yet in `catalog.yaml` — see A2). Fix: extend yesterday's pattern (`title: <Devanagari>`, `title_en: <roman>`) to every Marathi work in the corpus, whether cataloged or not. Since `/works` reads from `meta.yaml` first, updating meta.yaml alone flips the picker display. Do it as one systematic pass; propose the mapping to Neha before applying (transliterations need her eyes — see [[maharajanchi-sutre]]).

---

## Area A — Missing / incomplete corpus items

### A1 — MiM is half-shipped
- Canonical: `01_canonical/gurudev_ranade/books/mysticism-in-maharashtra/en/text.md` — 1,100 KB, 3,093 lines (rebuilt 2026-08-03 from digital reprint; backups `.pre-mim-full-2026-08-03.bak` and `.pre-reprint-2026-08-03.bak` on disk).
- Chunks in `04_processed/chunks.jsonl`: **14,389**.
- Catalog: **not present** in `03_catalog/catalog.yaml` as a top-level `- id:`. The string appears only as a theme tag on two smruti stories.
- Metadata drift: `01_canonical/gurudev_ranade/books/mysticism-in-maharashtra/meta.yaml` still reads `status: extracted`, `text_extraction_method: pandoc`, `raw_path: …Copy of Preface Mysticism In Maharashtra.docx` — the pre-reprint values. The text.md frontmatter correctly identifies the reprint source; the sibling meta.yaml was never updated after the swap.

**To ship fully:** update `meta.yaml`; add the catalog entry (`title: Mysticism in Maharashtra`, author: `gurudev_ranade`, path: `01_canonical/gurudev_ranade/books/mysticism-in-maharashtra/`, languages: `[en]`).

### A2 — 34 works missing from `catalog.yaml`
Excluding bodhsudha, nityanemavali, maharajachi-sutre (added 2026-08-04). All are already indexed — citation works, but they don't show in the picker.

**Highest-value candidates for the next catalog pass (by chunk count):**

| slug | path | langs | size KB | chunks |
|---|---|---|---:|---:|
| pathway-to-god-in-kannada-literature | `01_canonical/gurudev_ranade/books/pathway-to-god-in-kannada-literature` | en | 1366 | 14,638 |
| mysticism-in-maharashtra | `01_canonical/gurudev_ranade/books/mysticism-in-maharashtra` | en | 1101 | 14,389 |
| contemporary-indian-philosophy | `01_canonical/gurudev_ranade/books/contemporary-indian-philosophy` | en | 1397 | 11,374 |
| pathway-to-god-in-hindi-literature | `01_canonical/gurudev_ranade/books/pathway-to-god-in-hindi-literature` | en | 909 | 8,701 |
| bhagvadgeeta | `01_canonical/kakasaheb_tulpule/books/bhagvadgeeta` | mr | 1362 | 8,058 |
| patankar-pravachan-3 | `01_canonical/other_authors/lectures/patankar-pravachan-3` | mr | 1770 | 6,945 |
| gurusamarpit-jivan | `02_aggregated/biography/about_other_devotees/gurusamarpit-jivan` | mr | 920 | 5,600 |
| eknath-vachanamrut | `01_canonical/gurudev_ranade/books/eknath-vachanamrut` | mr | 2358 | 4,528 |
| glimpses-of-sri-gurudev | `02_aggregated/biography/about_other_devotees/glimpses-of-sri-gurudev` | en | 317 | 4,640 |
| sant-vachanamrut | `01_canonical/gurudev_ranade/books/sant-vachanamrut` | mr | 1848 | 4,368 |
| ramdas-vachanamrut | `01_canonical/gurudev_ranade/books/ramdas-vachanamrut` | mr | 2157 | 3,808 |
| eknathi-bhagvat-vachanamrut | `01_canonical/gurudev_ranade/books/eknathi-bhagvat-vachanamrut` | mr | 2345 | 3,738 |
| jnaneshwar-vachanamrut | `01_canonical/gurudev_ranade/books/jnaneshwar-vachanamrut` | mr | 1750 | 3,428 |
| tukaram-vachanamrut | `01_canonical/gurudev_ranade/books/tukaram-vachanamrut` | mr | 1178 | 3,281 |
| punyasmruti | `02_aggregated/biography/about_gurudev_ranade/punyasmruti` | mr | 737 | 2,959 |
| dhyanopakarani-gita | `01_canonical/gurudev_ranade/books/dhyanopakarani-gita` | mr | 521 | 2,724 |
| shri-gurudevanchya-athvani-pustak | `02_aggregated/biography/about_gurudev_ranade/shri-gurudevanchya-athvani-pustak` | mr | 418 | 1,961 |
| matoshri-sharakka | `02_aggregated/biography/about_other_devotees/matoshri-sharakka` | en | 108 | 1,383 |
| devotee (Nimbargi bio) | `02_aggregated/biography/about_nimbargi_maharaj/devotee` | mr | 242 | 1,246 |
| reflections | `01_canonical/gurudev_ranade/books/reflections` | en | 103 | 1,015 |

**Long tail (14 more):** `sevenfold-stream-of-spiritual-life`, `amar-sandesh-sudha`, `kakanchi-charcha`, `gurudeos-abhang`, `essays-and-reflections`, `sukhasahita-dukharahita`, `opportunities-of-college-life`, `lachyan-sandesh`, `n-g-damle-pravachan`, `devotees`, `radhabai-limaye-charitra`, `shri-gurudevanchya-athvani-2024`, `how-nimbal-was-chosen`.

**Do NOT auto-add.** Two blockers:
1. Attribution drift — `docs/authorship-audit-2026-07-11.md` corrects authors for 20+ works, several of which are in this list. Applying corrections must happen alongside the catalog add or the drift ships to prod.
2. Neha's per-book judgement — some of the long tail may be intentionally kept out.

### A3 — 5 stub canonicals (meta.yaml only, no text.md)
- `bhajanamrut`, `daily-thoughts`, `dhyangita` — Ranade books never extracted.
- `introduction-to-karnataka-mysticism` — likely intentional (subsumed by `pathway-to-god-in-kannada-literature`; verify with Neha).
- `santanchya-sahavasat` — Kakasaheb book; `missing-titles-checklist.md` §5 item 16 wrongly says "text present but not yet chunked" — text.md is absent.

### A4 — Index-drift and duplicates
- **`the-old-house-at-nimbal`** — catalog entry has zero chunks; content is indexed under Devanagari-slug variants (`निंबाळचे जुने घर` with a space, `निंबाळचे-जुने-घर` with a hyphen — two copies of the same story).
- **`guru-ha-parabrahma-kewal`** — 6,600 chunks (in catalog) PLUS three Devanagari-slug copies totaling 6,606 duplicate chunks (`copy-गुरू-हा-परब्रह्म-केवळ-भाग-१/२/३`).
- **`punyasmruti`** — 2,959 chunks (roman) + 2,835 duplicate chunks under Devanagari slug `पुण्यस्मृती`.

Duplicates overweight retrieval. Cleanup requires: pick canonical slug per book, run `tools/surya_ocr/force_reembed.py --apply <old_slug>` on the losers, re-run chunker. Design decision (which slug wins) is Neha's.

### A5 — Orphan slugs in the index
Not in catalog, not on disk under that slug — but chunks exist:
- `allahabad-days` (97 chunks) — distinct from `allahabad-days-en` and `allahabad-days-mr`.
- `ranade-bibliography` (94), `kanada-saints-bio` (612), `v-h-date` (5), `nimbal-ashram-info` (49).
- `आठवणी-to-review` (177) — literally draft content that shipped into the index.

These pollute retrieval with untraceable citations. Investigation needed before deleting.

### A6 — `parmartha-sopan` lang directory quirk
Text lives at `01_canonical/gurudev_ranade/books/parmartha-sopan/mixed/text.md` (not `en/`/`mr/`). Indexed as `parmartha-sopan` with 3,486 chunks. Not in catalog. Any tooling that assumes ISO lang codes will trip.

---

## Area B — Devanagari Surya OCR campaign

The campaign is nearly complete. 4 books remain. Ranked in the order Neha should tackle:

### B1 — `bhagvadgeeta` (assembly-only) ★ next up
Kakasaheb Tulpule's main gita commentary. 1,364 KB of garbled pdftotext output currently on disk. **Surya OCR has already been run** — 18 clean adhyaya `.md` files sit in `_surya_ocr_job/out/bhagvadgeeta-adhyaya-*.md` (~1.2 MB total, conjuncts intact, Sanskrit shlokas cleanly rendered). Source PDFs both in the canonical dir (`.../mr/Geeta*.pdf`) and in `_surya_ocr_job/staging/bhagvadgeeta/`.

**Next steps:** run assembly (`tools/multivolume/…`-style — probably need to author `assemble_bhagvadgeeta.py` following the BGPGR pattern), swap canonical, force-reembed, re-chunk. This is Neha's stated #1 per `project_next_big_work.md`.

### B2 — `kakanchi-charcha` (unblocked, small)
Kakasaheb's "conversations". 68 KB, source PDF in-tree (`.../mr/काकांची चर्चा.pdf`). Not yet queued to Surya. Moderate garbling. Fast run once Neha queues it.

### B3 — `punyasmruti` (BLOCKED)
740 KB of heavy pdftotext damage. `meta.yaml sources[].raw_path: ''` — no PDF on file. Unblock options: (a) locate original in Neha's Drive dump batches; (b) ACPR publisher's clean PDF; (c) physical scan.

### B4 — `gurusamarpit-jivan` (BLOCKED)
924 KB. Same failure mode as B3 — empty `raw_path`. Lower priority per Neha's main-source-first rule ("about other devotees" tier).

### B5 — Metadata-only drift
`maharajachi-sutre` text.md was Surya-swapped 2026-08-05, but sibling `meta.yaml text_extraction_method:` still says `pdftotext`. Cosmetic — one-line fix.

Nothing else in the Devanagari corpus is a candidate. All the pandoc/docx-xml books (17 of them) are clean.

---

## Area C — ToC restoration

The reader's TOC drawer requires two conditions: (a) slug in `TOC_ALLOWED_SLUGS` at `chat-app/app/read/[slug]/page.tsx:78` AND (b) text.md has `##`/`###` markdown headings. Adding to allow-list without hierarchy is a safe no-op (button just hides). Neha's policy: eyeball each book's rendered TOC before adding.

### C1 — Currently allow-listed
`kakanchi-pravachane`, `mysticism-in-maharashtra`, `bhagavadgita-as-pathway-to-god-realization` (3). Nityanemavali being added in-session (subagent finishing).

### C2 — Ready to consider for allow-list (12 books)
Have ≥2 clean `##` headings, no normalization needed. Add one at a time after eyeball.

| slug | path | `##` | `###` | notes |
|---|---|---:|---:|---|
| parmartha-mandir | `01_canonical/gurudev_ranade/books/parmartha-mandir/mr/text.md` | 53 | 32 | Largest structured Gurudev work |
| kannad-parmarth-sopan | `01_canonical/gurudev_ranade/books/kannad-parmarth-sopan/mr/text.md` | 82 | 74 | Dense two-level hierarchy |
| swanandacha-gabha | `02_aggregated/biography/about_other_devotees/swanandacha-gabha/mr/text.md` | 28 | 187 | Very rich `###` grain |
| javak-patre-tipane | `01_canonical/bhausaheb_maharaj/letters/javak-patre-tipane/mr/text.md` | 22 | 58 | Some `###` are repeated salutations |
| kushal-pradhyapak | `02_aggregated/biography/about_gurudev_ranade/kushal-pradhyapak/mr/text.md` | 20 | 49 | Clean |
| jivandarshan-deshpande | `02_aggregated/biography/about_gurudev_ranade/jivandarshan-deshpande/mr/text.md` | 18 | 44 | Trailing hyphens on some titles |
| sonari-pane-2000 | `02_aggregated/biography/about_other_devotees/sonari-pane-2000/mr/text.md` | 22 | 17 | Clean |
| acpr-silver-jubilee-vol1 | `02_aggregated/biography/about_other_devotees/acpr-silver-jubilee-vol1/en/text.md` | 96 | 172 | Heavy — some tribute-titles want `###` |
| allahabad-days-mr | `02_aggregated/biography/about_gurudev_ranade/allahabad-days-mr/mr/text.md` | 23 | 7 | Clean, mostly flat |
| sadhakbodh | `01_canonical/kakasaheb_tulpule/letters/sadhakbodh/mr/text.md` | 24 | 21 | Duplicate `## साधक-बोध` — normalize first |
| gurudev-paramarthik-shikvan | `01_canonical/kakasaheb_tulpule/books/gurudev-paramarthik-shikvan/mr/text.md` | 25 | 8 | OCR slip: `## माग पहिला` should be `भाग` |
| kannada-sahityatil-punyasmruti | `02_aggregated/biography/about_gurudev_ranade/kannada-sahityatil-punyasmruti/mr/text.md` | 12 | 40 | Clean |

**Recommended add order (highest-value first):** `parmartha-mandir` → `kannad-parmarth-sopan` → `swanandacha-gabha` → `kushal-pradhyapak` → `allahabad-days-mr` → `jivandarshan-deshpande`.

### C3 — Have hierarchy but noisy (normalize first)
Five books share the `## Part N` pandoc-splitter symptom (headings are `## Part 1` ... `## Part N` instead of real chapter names). One normalization pass upgrades all:
- `patankar-pravachan-3` (24 Parts), `bhagvadgeeta` (19 Parts — matches 18 adhyayas + intro), `parmartha-sopan` (3 Parts on 5,061 lines), `pathway-to-god-in-hindi-literature` (3 Parts), `pathway-to-god-in-kannada-literature` (3 Parts).

Two other noisy books:
- `pawanbhumi-jamkhandi` — 7 `##` are all photo captions. 310-line photo book; leave gated.
- `acpr-silver-jubilee-vol2` — 15 `##` mixed with `## (viii)`, `## (I)`, `## **Philosophy…**`. Cleanup pass before add.

### C4 — 18 main-source books with 0 hierarchy (highest restoration value)
Per `project_next_big_work.md`. Vachanamrut cluster (Eknath / Sant / Ramdas / Jnaneshwar / Tukaram / Eknathi-Bhagvat) share a source shape — doing one as template makes the others cheap.

Ranade's own English works needing hierarchy: `contemporary-indian-philosophy` (24,446 lines), `creative-period` (22,583), `constructive-survey-of-upanishadic-philosophy` (14,848), `hindi-parmarth-sopan` (12,947), `philosophical-and-other-essays` (7,797), `gandhi-and-other-indian-saints` (7,126), `evolution-of-my-own-thought` (1,446), `herakleitos` (767).

Devanagari: 5 Vachanamruts + `dhyanopakarani-gita`, `dhyangita-anvayarth`, `sadhakachi-atmakatha`, `bodhsudha`.

### C5 — 29 secondary-priority (0 hierarchy)
14 are short/atomic (aphorism collections, single lectures) where a TOC would be semantically wrong: `amar-sandesh-sudha`, `devotees`, `essays-and-reflections`, `gurudeos-abhang`, `how-nimbal-was-chosen`, `kakanchi-charcha`, `lachyan-sandesh`, `maharajachi-sutre`, `n-g-damle-pravachan`, `opportunities-of-college-life`, `shri-gurudevanchya-athvani-2024`, `sukhasahita-dukharahita`, `vedant`, `vindication-of-indian-philosophy`.

Remaining 15 are biographies + `other_authors` books where hierarchy would help but priority is lower than C4.

---

## Adjacent threads

### T1 — RFC-018 Phase 2 (splice-time citation aliases)
Phase 1 shipped 2026-08-04 (`rfc(018) Phase 1 — work_roles.yaml + citation-alias builder + sample report`). Phase 2 wires the aliases into the citation-splice pipeline so `(A)` letters correctly resolve to their canonical citation across the answer. See RFC-018.

### T2 — RFC-018 Phase 3 (/admin/aliases dashboard)
UI for Neha to review + curate aliases. Depends on Phase 2.

### T3 — RFC-021 Changes 3-5 (citation-fidelity fixes)
Changes 1-2 shipped. Remaining 3-5 in the RFC — retrieval/quality/verify-pass improvements. Neha to decide when to prioritize.

### T4 — RFC-022 candidate (retrieval-diversity + cross-lingual)
Not yet drafted. Purpose: improve top-K diversity + Marathi/English cross-lingual matching. Scope needed.

### T5 — Mobile chat drawer keyboard-shift + scroll-stuck bug
User-visible bug (task #61). Symptom: when the mobile keyboard opens, the chat drawer shifts and gets stuck; scroll doesn't recover. Needs iOS Safari reproduction.

### T6 — Contemporary Indian Philosophy essay-boundary split
Task #45. Anthology of essays currently ingested as a single work; retrieval should scope per-essay for correct attribution. Data fix, not code.

### T7 — Kakasaheb 1945 attribution bug
Ninad's feedback — grounding-fidelity issue where a 1945 quote was mis-attributed. Details in prior session notes; needs a repro case before fix.

### T8 — Wrong-invite-code UX polish
Task #39. Low priority.

---

## Cross-cutting quality gates (Neha's standing rules)

- Never commit / push / deploy without Neha's explicit approval on the specific change.
- Never push without pytest + vitest + tsc all green locally (`cd chat-app && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/vitest run` and `env -u ANTHROPIC_API_KEY ./.venv/bin/pytest tools/tests/ -q`).
- Prefer modern digital reprints over Surya OCR for Ranade books where reprints exist (`project_ranade_reprints_preferred.md`).
- Test before push: fixed a JSX bug on prod once; that must not recur.

---

## What just landed (this session, 2026-08-04 → 2026-08-05)

- 17 Marathi books now have Devanagari `title` + roman `title_en` (search + display unified).
- Sutre Surya OCR canonical shipped to prod; chunks + embeddings refreshed.
- `bodhsudha` and `nityanemavali` added to catalog with Devanagari titles.
- `/works` endpoint returns `title_en` separately; frontend picker filters on either script.
- Broken `build:check` script removed; replaced with `check` (`tsc --noEmit && vitest run`) that doesn't clobber the running dev cache.

## Cross-refs

- Memories: `MEMORY.md`, `project_marathi_titles_state.md`, `project_mim_reprint_ingest_state.md`, `project_next_big_work.md`, `project_toc_allowlist.md`, `feedback_ranade_reprints_preferred.md`, `feedback_test_before_push.md`, `feedback_ship_only_with_approval.md`, `feedback_delegate_isolated_tasks.md`, `feedback_queue_dont_interrupt.md`.
- Prior audits: `corpus-coverage-audit-2026-06-17.md`, `authorship-audit-2026-07-11.md`, `toc-readiness-audit-2026-08-01.md`, `ocr-quality-audit-2026-07-14.md`.
- RFCs: RFC-018 (citation aliases), RFC-019 (secondary instructions), RFC-020 (multi-volume assembly), RFC-021 (retrieval quality + citation fidelity), RFC-023 (reading-mode answer format — to be drafted per U3).
