# TOC Readiness Audit — 2026-08-01

Audit of every `text.md` under `01_canonical/` and `02_aggregated/` to decide which
books can render a reader-side Table of Contents (as newly built for
`kakanchi-pravachane`) from `## <section>` / `### <chapter>` markdown headings, and
which need retrofit.

**Total books audited:** 74 (48 canonical + 26 aggregated)
**By category:** A: 14, B: 2, C: 4, D: 38, E: 16
**RAG-active:** 74 / 74 — every audited book has chunks in `04_processed/chunks.jsonl`,
so retrofit priority is driven by author + size only.

**Classification rule used:**
- **A** — TOC-ready: `##` ≥ 2 AND `###` ≥ 5 (grouped TOC will render cleanly).
- **B** — Flat TOC: exactly one heading level present (either only `##` or only `###`).
- **C** — Partial structure: some `##`/`###` but density < 1 heading per 1000 lines OR only 3–4 top-level headings across a large book.
- **D** — No structure: 0 usable `##`/`###` (leading `# Title` alone does not count).
- **E** — Short/atomic: < 500 lines. TOC not meaningful regardless of headings.

---

## Category A — TOC-ready (14 books)

| slug | lang | lines | ## | ### | notes |
|---|---|---:|---:|---:|---|
| parmartha-mandir | mr | 19,017 | 53 | 32 | 13 `#` sections too — largest structured Gurudev work |
| javak-patre-tipane | mr | 12,797 | 22 | 58 | letter-corpus (Bhausaheb outgoing) |
| kannad-parmarth-sopan | mr | 11,618 | 82 | 74 | dense hierarchy |
| kakanchi-pravachane | mr | 9,825 | 5 | 47 | RFC-020 assembly, reference baseline |
| jivandarshan-deshpande | mr | 4,793 | 18 | 44 | biography (about_gurudev_ranade) |
| acpr-silver-jubilee-vol1 | en | 4,704 | 96 | 172 | souvenir volume |
| gurudev-paramarthik-shikvan | mr | 4,270 | 25 | 8 | few `###` — flat-ish within sections but usable |
| sadhakbodh | mr | 3,711 | 24 | 21 | Kakasaheb letters |
| swanandacha-gabha | mr | 2,588 | 28 | 187 | very rich `###` grain |
| kushal-pradhyapak | mr | 2,517 | 20 | 49 | biography |
| sonari-pane-2000 | mr | 2,034 | 22 | 17 | Nimbargi lineage history |
| allahabad-days-mr | mr | 1,843 | 23 | 7 | 7 `###` across 23 `##` — borderline but usable |
| acpr-silver-jubilee-vol2 | en | 1,766 | 15 | 37 | 23 stray `#` (likely per-piece titles) |
| kannada-sahityatil-punyasmruti | mr | 1,084 | 12 | 40 | short but well structured |

---

## Category B — Flat TOC only (2 books)

| slug | lang | lines | ## | ### | notes |
|---|---|---:|---:|---:|---|
| bhagvadgeeta | mr | 9,029 | 19 | 0 | 19 chapter-level `##` — flat list is correct for a Gita |
| patankar-pravachan-3 | mr | 3,107 | 24 | 0 | 24 pravachan headings — flat list is natural |

Both will render as a clean flat clickable chapter list under the current reader
if the UI treats a top-level-only tree as ungrouped chapters. If it currently
requires `##` to always be a *group container*, the UI needs a tiny fallback:
"if no `###`, render `##` as leaf chapters." That is a UI-side fix, not a text
retrofit.

---

## Category C — Needs retrofit (partial structure) — 4 books

Density is too sparse: 3–4 `##` on 5k–8k lines means the reader-side TOC would
show a nearly-empty tree.

### Priority: HIGH (Gurudev Ranade, active in RAG)

| slug | lang | lines | ## | ### | detected pattern | retrofit effort |
|---|---|---:|---:|---:|---|---|
| pathway-to-god-in-kannada-literature | en | 8,415 | 3 | 0 | 561 bold-only lines (`**...**`) look like real section labels; also 89 numbered items | MEDIUM — script the bold-line → `## ` conversion, filter noise |
| bhagavadgita-as-pathway-to-god-realization | en | 6,462 | 4 | 0 | 296 bold-only lines + "CHAPTER I..V" markers embedded; 12 ALL-CAPS section titles | MEDIUM — CHAPTER pattern is line-anchored, viable regex |
| pathway-to-god-in-hindi-literature | en | 6,272 | 3 | 0 | 88 bold-only + 18 `CHAPTER I..X` + 83 ALL-CAPS titles | MEDIUM — same shape as sibling pathway books |
| parmartha-sopan | mixed | 5,061 | 3 | 0 | 1,970 bold-only lines (many are inline emphasis, not headers); 10 `CHAPTER I..X` lines; 23 ALL-CAPS | HIGH — bold-line noise means CHAPTER pattern is the only safe anchor; needs sub-section curation |

---

## Category D — Needs retrofit (no structure) — 38 books

Subgrouped by author priority.

### Priority: HIGH — Gurudev Ranade's own works, RAG-active

| slug | lang | lines | detected pattern | retrofit effort |
|---|---|---:|---|---|
| contemporary-indian-philosophy | en | 24,446 | 84 Roman-numeral headings (`V. SUBRAHMANYA IYER`); 47 numbered `N.`; 19 ALL-CAPS | MEDIUM — Roman-numeral pattern is a real section anchor |
| creative-period | en | 22,583 | 13 embedded `CHAPTER I..N` (inline, OCR-noisy) + 324 numbered; only 3 anchored Roman | HIGH — CHAPTER markers not line-anchored; will need OCR cleanup pass first |
| constructive-survey-of-upanishadic-philosophy | en | 14,848 | 11 `CHAPTER IT/IIT` (OCR-garbled Roman); 18 Roman `IV. Roots...` (TOC lines); 344 numbered | HIGH — CHAPTER markers are OCR-mangled |
| hindi-parmarth-sopan | hi | 12,947 | 24 `CHAPTER I..N`; 69 ALL-CAPS; 460 `N.` items | MEDIUM — CHAPTER anchor + ALL-CAPS section titles look consistent |
| eknath-vachanamrut | mr | 9,937 | **41 `भाग/प्रकरण` markers line-anchored** (`भाग २ : स्फुट...`, `प्रकरण : १..८`, `अध्याय क्र.`) | LOW — clean regex retrofit; two-level hierarchy already implicit |
| sant-vachanamrut | mr | 9,584 | **19 `भाग` markers line-anchored** (`भाग पहिला: ज्ञानदेवादि संत`, ...); 2,310 `N.` numbered aphorisms | LOW-MEDIUM — भाग → `##`, but `###` chapter grain may need decision (aphorisms don't map naturally) |
| jnaneshwar-vachanamrut | mr | 7,909 | 65 `कांडां/पर्वतीं` markers but these are inline verse text, not headings; 251 numbered | HIGH — no clear line-anchored chapter marker; likely needs manual chapter extraction |
| philosophical-and-other-essays | en | 7,797 | 287 `N. Name` (looks like list-of-donors + essays); 8 Roman | MEDIUM — Roman-numeral essay titles (`II. PARMENIDES 32-42`) usable |
| eknathi-bhagvat-vachanamrut | mr | 7,556 | **36 `अध्याय N` line-anchored**; 593 numbered `N.` items | LOW — clean `अध्याय` pattern |
| ramdas-vachanamrut | mr | 7,291 | **9 `भाग पहिला/दुसरा` line-anchored**; 1,168 numbered `N.` items | LOW — clean top-level `भाग`, but only 9 sections for 7k lines suggests need for `###` sub-grain |
| gandhi-and-other-indian-saints | en | 7,126 | 5 line-anchored `Chapter 1..N`; 89 `N.` | LOW-MEDIUM — Chapter pattern is clean, just 5 chapters |
| dhyanopakarani-gita | mr | 6,586 | 19 mixed `पुष्प/अध्याय` inline; 137 numbered | MEDIUM — anchor uncertain, may need per-chapter check |
| tukaram-vachanamrut | mr | 5,685 | Roman-numeral top-level (`I. Historical Events...` line 1) + 1,410 numbered | MEDIUM — Roman `I..V` sections + numbered sub-items |
| dhyangita-anvayarth | mr | 5,550 | 916 bold-only lines (`**श्रीमद्ध्य़ानगीता**`, `**प्रथमोऽध्यायः**`); very verse-heavy | HIGH — bold-line noise (verse markers, not headings) |
| sadhakachi-atmakatha | mr | 4,811 | **17 `भाग/भाग्य` markers** + 30 numbered chapter-index lines | LOW — likely a clean `भाग N` retrofit |
| nityanemavali | mr | 3,919 | 25 numbered `१. निवेदन`, `२. प्रस्तावना`, ... | LOW — numbered TOC-style list |
| reflections | en | 1,683 | 0 headings — aphorism collection | HIGH or SKIP — treat like `bodhsudha` if truly atomic; else needs manual thematic grouping |
| evolution-of-my-own-thought | en | 1,446 | 0 headings | MEDIUM — Gurudev's autobiographical essay; check for section breaks manually |
| herakleitos | en | 767 | 0 headings | MEDIUM — short book, likely has clear parts |
| maharajachi-sutre | mr | 617 | 0 headings — Kakasaheb aphorism book | LOW-priority (short) |
| bodhsudha | mr | 515 | 0 headings — Nimbargi aphorism book | LOW-priority (short atomic) |

### Priority: MEDIUM — direct-lineage disciples (Kakasaheb, Bhausaheb, Nimbargi)

No Cat D books remain in this bucket (Kakasaheb `sadhakachi-atmakatha` listed under
HIGH by size; his other Cat D pieces are all short → included above or in E).

### Priority: LOW — biographies, `other_authors`, aggregated

| slug | lang | lines | detected pattern | retrofit effort |
|---|---|---:|---|---|
| pathway-to-god-in-the-vedas | en | 16,086 | 20 `Chapter I..N`; 797 numbered `N.` items; 36 Roman | LOW-MEDIUM — Chapter/Roman anchors clean |
| ranade-and-his-spiritual-lineage | en | 12,710 | 7 `Chapter 1..N`; 278 numbered | LOW — clean `Chapter N` |
| allahabad-days-en | en | 7,618 | 24 `N.` items look like essay titles; 16 Roman | MEDIUM |
| critical-constructive-aspects | en | 7,587 | 8 `Chapter II..X`; 131 numbered footnotes | LOW-MEDIUM |
| gurusamarpit-jivan | mr | 7,291 | 160 numbered TOC-style; OCR noise heavy | HIGH — OCR quality poor |
| studies-in-indian-philosophy | en | 6,797 | 23 `Chapter V..XV`; 148 Roman `I. Introduction ...` | LOW — clean Chapter + Roman anchors |
| guru-ha-parabrahma-kewal | mr | 6,619 | 375 bold-only; 67 devanagari numbered TOC lines | MEDIUM |
| glimpses-of-sri-gurudev | en | 5,374 | 288 `N. Title : Author, City - page` TOC lines | LOW — one-line-per-tribute retrofit |
| punyasmruti | mr | 4,466 | few `भाग` markers (11); mostly flat | MEDIUM |
| amrutavalli | mr | 4,039 | 19 `प्रकरण पहिले/दुसरे...` line-anchored | LOW — clean |
| charitra-tatvajnan-tulpule | mr | 3,634 | 106 bold-only; 129 devanagari numbered | MEDIUM |
| nimbargi-maharaj-charitra-athavani-mr | mr | 2,036 | few `अध्याय/प्रकरण` mentions (4); 8 numbered | MEDIUM |
| nimbargi-maharaj-biography-en | en | 1,533 | 0 headings | MEDIUM |
| sevenfold-stream-of-spiritual-life | en | 1,170 | 0 headings | LOW-priority |
| shri-gurudevanchya-athvani-pustak | mr | 960 | 0 headings | LOW-priority |
| devotee | mr | 810 | 0 headings | LOW-priority |
| matoshri-sharakka | en | 694 | 0 headings | LOW-priority |

---

## Category E — Short/atomic, TOC not applicable (16 books)

Books under 500 lines. Reader UI should keep TOC hidden regardless of headings.

- `pawanbhumi-jamkhandi` (en, 310) — **has structure (7 ##, 6 ###); Cat-A shape but too short to matter**
- `kakanchi-charcha` (mr, 424)
- `essays-and-reflections` (en, 393)
- `gurudeos-abhang` (en, 384)
- `amar-sandesh-sudha` (mr, 369)
- `devotees` (mr, 218)
- `sukhasahita-dukharahita` (mr, 179) — single lecture
- `opportunities-of-college-life` (en, 172) — single address
- `mysticism-in-maharashtra` (en, 146; has 16 `###`) — essentially an abstract; leave hidden
- `vedant` (en, 137) — single essay
- `radhabai-limaye-charitra` (mr, 116)
- `vindication-of-indian-philosophy` (en, 91) — single essay
- `n-g-damle-pravachan` (mr, 43)
- `lachyan-sandesh` (mr, 33)
- `shri-gurudevanchya-athvani-2024` (mr, 26) — probably a stub
- `how-nimbal-was-chosen` (mr, 12) — stub

---

## Recommendations

**Immediate (0 code changes needed):** Ship the reader TOC as-is for the 14 Cat-A
books. `kakanchi-pravachane`-style grouped TOC will render on all of them.

**One-line UI fix (unlocks 2 more books):** teach the reader to render a flat
list of `##` when there are no `###` beneath. That converts `bhagvadgeeta` and
`patankar-pravachan-3` (both currently Cat B) into full TOC coverage with zero
text changes. Combined with A, that reaches 16 / 74 books.

**Batch-1 retrofit (LOW-effort, HIGH-yield, ~7 books, ~1 day):** books with a
line-anchored `भाग / प्रकरण / अध्याय / Chapter N` pattern already in the text —
a small script converts them to `## भाग N …` (and `### प्रकरण N …` where a
second level exists). Recommended order (Gurudev's own works first):

1. `eknath-vachanamrut` (`अध्याय` + numbered)
2. `eknathi-bhagvat-vachanamrut` (`अध्याय N`)
3. `ramdas-vachanamrut` (`भाग पहिला/दुसरा`)
4. `sant-vachanamrut` (`भाग` × 3)
5. `sadhakachi-atmakatha` (`भाग`)
6. `amrutavalli` (`प्रकरण पहिले/दुसरे`)
7. `gandhi-and-other-indian-saints` (`Chapter 1..N`)

**Batch-2 retrofit (MEDIUM-effort, ~10 books):** English works with `CHAPTER I..N`
or Roman-numeral section anchors that survived OCR — needs a per-book regex pass
plus a quick manual audit of missing/duplicated chapter numbers:
`contemporary-indian-philosophy`, `hindi-parmarth-sopan`,
`pathway-to-god-in-the-vedas`, `studies-in-indian-philosophy`,
`critical-constructive-aspects`, `ranade-and-his-spiritual-lineage`,
`bhagavadgita-as-pathway-to-god-realization`,
`pathway-to-god-in-hindi-literature`, `pathway-to-god-in-kannada-literature`,
`glimpses-of-sri-gurudev`.

**Batch-3 retrofit (HIGH-effort / lower ROI):** OCR-noisy or structurally-ambiguous
long works. Consider deferring until an OCR-quality pass or manual TOC extraction
is scheduled: `creative-period` (22k lines, OCR-mangled CHAPTER),
`constructive-survey-of-upanishadic-philosophy`, `jnaneshwar-vachanamrut`,
`dhyangita-anvayarth`, `parmartha-sopan`, `gurusamarpit-jivan`,
`charitra-tatvajnan-tulpule`.

**Skip / mark "atomic":** all 16 Cat-E books, plus `reflections`, `bodhsudha`,
`maharajachi-sutre` — aphorism / single-piece works where a TOC is semantically
wrong. Reader UI already handles this (empty TOC hidden).

**Tooling suggestion.** A single `tools/retrofit_headings.py` that accepts
`--pattern` and `--level` arguments (e.g. `--pattern '^भाग\s+\S+' --level 2`)
would cover Batches 1 and much of Batch 2. Combined with a preview mode showing
before/after line counts and a per-book YAML in `tools/heading-rules/*.yaml`,
this scales cleanly to the whole retrofit list.

**Coverage math after each batch.**

| stage | Cat-A equiv / total | % TOC-ready |
|---|---:|---:|
| today | 14 / 74 | 19% |
| + UI fallback for Cat-B | 16 / 74 | 22% |
| + Batch 1 (7 books) | 23 / 74 | 31% |
| + Batch 2 (10 books) | 33 / 74 | 45% |
| + Batch 3 (7 books) | 40 / 74 | 54% |
| remainder are Cat-E (16) and small Cat-D (~18) | up to 58 / 74 | 78% ceiling |

The Cat-E floor of 16 books is intrinsic — those are aphorisms, single essays,
and stubs where a TOC has no meaning.
