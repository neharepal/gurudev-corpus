# Roadmap

**Status:** [ACTIVE]
**Last updated:** 2026-06-13
**Hard deadline:** **2026-07-12** (sampradaya demo, 10-min Zoom slot)

29 days from today. Backward-planned with explicit critical path.

## Where we are now (2026-06-13)

### Done
- **Design discipline:** PRD locked. RFCs 001/002/003 locked. RFCs 004/005 in drafting/review. 6 ADRs written.
- **Corpus structure:** Lineage-aware folders for `01_canonical/` and `02_aggregated/`. Bundle attribution model live.
- **Ingestion:** 222 raw files ingested into staging; 145 files moved to structured locations per dashboard decisions.
- **Athvani infrastructure:** story_index seeded. `tools/ingest_athvani.py` built. Multi-variant case tested on 3 Sonopant Dandekar files — surfaced tuning issues (logged as task #22).
- **Canonical extraction:** template validated on PGHL (146K-word `text.md` + `meta.yaml`).
- **Tools:** attribution dashboard, move plan, citation panel mockups, chat UI mockups.

### In flight
- RFC-004 (Chat UI) — drafted, mockups landed; awaiting user review.
- RFC-005 (Multilingual EN+MR) — not started; few user-input questions to ask.
- Task #22 (matcher tuning) — pending; blocks bulk athvani ingest.
- Task #11 (bulk canonical extraction) — pending; PGHL template ready to apply.

## Weekly milestones

### Week 1 (Jun 13 – Jun 19) — Finish design, prep corpus
- All RFCs locked (002 ✓, 003 ✓, 004 review, 005 draft).
- ADR-006 ✓; ADR-007 (deployment) deferred to post-demo.
- Matcher tuning (#22) complete and validated.
- Bulk canonical text extraction (#11) — all 25+ canonical works → `text.md` + `meta.yaml`.
- Bulk athvani ingest (#9) — all athvani folders processed through `ingest_athvani.py`, review queue triaged.
- **End-of-week state:** corpus extracted and indexed-ready; design phase closed.

### Week 2 (Jun 20 – Jun 26) — Build RAG + chat shell
- Embedding pipeline live: chunks + BGE-M3 embeddings → Chroma vector index.
- Anthropic API integration with prompt caching.
- Next.js project scaffolded with warm-devotional theme tokens.
- Q&A mode end-to-end: question → retrieve → answer → citation render.
- Pravachan mode prompt template + structured output rendering.
- Simple Reading mode shell with bookmark state.
- **End-of-week state:** all three modes work on the happy path with the demo corpus subset.

### Week 3 (Jun 27 – Jul 3) — Bilingual + polish
- Marathi end-to-end: input detection, retrieval mixing, answer language matching.
- Source preview + Reading-mode handoff.
- WhatsApp share working.
- Flag mechanism (button + YAML queue).
- Mobile responsive pass.
- Error states (timeout / empty retrieval / language mismatch).
- **End-of-week state:** feature-complete for the demo set; rough edges remain.

### Week 4 (Jul 4 – Jul 11) — Gold-tune + dress runs
- Gold-tune the 6 scripted questions: write reference answers, iterate prompts and retrieval until output matches reference quality.
- Latency optimization: prompt caching tuned, cold-start mitigations.
- Devanagari font loading + visual polish.
- **Day 21 (Jul 6):** first full dress rehearsal (record + review).
- **Day 24-25 (Jul 9-10):** second + third dress rehearsals.
- **Day 26 (Jul 11):** freeze. Only critical-bug fixes.
- **End-of-week state:** demo-ready.

### Day 29 — Jul 12 (Demo)
- Sampraday Zoom call, ~30 attendees, 10-min slot.
- Demo flow per RFC-001: 5 min scripted (6 questions) + 5 min audience Q&A.

## Critical path

The shortest sequence from now to a working demo:

```
matcher tuning (#22)  ──┐
                         ├──► bulk athvani (#9)  ──┐
bulk canonical (#11)  ──┴──► chunk + embed ────────┴──► RAG pipeline ──► chat UI ──► gold-tune ──► demo
```

Anything that slips on this path slips the demo. Off-path items (RFC-005, RFC-006 access control, audio, etc.) can slip without consequence.

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Marathi answer quality is poor relative to English | Medium-high | High — undermines one of three success-sentences | Polish-week gold-tuning specifically scrutinizes Marathi outputs; fallback: English answer with key Marathi terms preserved |
| Senior sadhaks ask questions outside the corpus | High | Medium — graceful "not in corpus" is acceptable, hallucination is not | Aggressive honesty prompt tuning + adversarial dry runs |
| Pravachan mode output quality on Sonnet 4.6 is weak | Medium | Medium | Pre-tune prompt; one-line code change to route Pravachan to Opus 4.7 if needed |
| Live demo network/latency surprise | Medium | High | All retrieval local; warm prompt cache before demo; streaming output so wait feels productive |
| Schedule slip on chat UI | Medium | High | Cut scope: Simple Reading mode goes stretch-goal-only; demo Q&A + Pravachan only |
| Matcher tuning doesn't actually fix the dedup issue | Medium | Medium — review queue grows | Acceptable; review queue is the safety net by design |
| Mockups don't translate to working UI in Week 2 | Low-medium | Medium | Mockups are visual reference; actual implementation may simplify |

## Scope cuts (in priority order if we slip)

If Week 3 ends and we're behind:
1. **Drop Simple Reading mode from live demo.** Build it; don't demo it. (RFC-001 already allows this.)
2. **Drop WhatsApp share.** Inconvenient but not core to the demo.
3. **Drop flag mechanism for the demo.** Add post-demo. (Replaceable with "we'll add this soon" comment in demo.)
4. **Lock Q&A mode to English at demo.** Marathi becomes a follow-up release. (Last resort — violates one of three success sentences.)

## What slipped already

- Audio transcription: out of scope per PRD §7 / ADR-005 follow-up.
- Hosting/deployment: deferred to post-demo (RFC-007).
- Admin flag review surface: deferred to post-demo.
- User accounts/auth: deferred to post-demo.

## What this roadmap explicitly does NOT promise

- A polished v1 product. The July 12 demo is a *live demo of feature shape*, not a launch.
- Cross-language answer generation in Hindi/Sanskrit/Kannada at demo.
- Voice input/output.
- A native mobile app.

These are aspirational; they remain post-demo work.

## How this doc gets used

- Updated weekly (Friday end-of-day) with progress + slips.
- Each implementation task should reference the week it's in.
- Cross-references back to PRD, RFCs, and ADRs for context.

## References

- [PRD.md](PRD.md)
- [rfc/RFC-001-demo-mvp.md](rfc/RFC-001-demo-mvp.md) — defines demo scope this roadmap is sized against
- [rfc/RFC-002-corpus-structure.md](rfc/RFC-002-corpus-structure.md)
- [rfc/RFC-003-retrieval-and-rag.md](rfc/RFC-003-retrieval-and-rag.md)
- [rfc/RFC-004-chat-ui-and-ux.md](rfc/RFC-004-chat-ui-and-ux.md)
