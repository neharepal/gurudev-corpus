# ADR-006: Visual aesthetic — "warm devotional, old yellow pages, maroon paprika"

**Status:** ACCEPTED
**Date:** 2026-06-12
**Author:** Neha (with Claude)

## Context

The chat platform is a tool for sampradaya devotees engaging with sacred literature. Most existing chat UIs (ChatGPT, Claude.ai, Gemini, etc.) project a "modern technology product" aesthetic — clean whites or deep grays, sans-serif fonts, abundant horizontal lines, dense information density. This is great for productivity tools but tonally wrong for a tool whose primary content is Gurudev's spiritual writing, oral tradition, and devotional commentary.

When asked about visual direction, the user described: *"warm devotional. In my mind, I see old yellow pages with maroon paprika style font."*

This is a clear and unusual direction. It evokes an old book — perhaps a leather-bound volume from a devotee's shelf, with sepia-tinted pages and a maroon binding. Reverential, slow, contemplative, easy on the eyes during long reading.

## Decision

The chat platform adopts a **"warm devotional" visual aesthetic** with the following pillars:

### Color palette

| Role | Color | Note |
|---|---|---|
| Background (page) | `#F8F2E4` (warm cream / parchment) | Not white; evokes old paper |
| Surface (cards, inputs) | `#FCF8EC` (lighter parchment) | Slight elevation through tone, not shadow |
| Primary text | `#2D2924` (deep sepia) | Not pure black; warmer reading experience |
| Secondary text | `#6E665B` (muted bronze) | For metadata, citations, captions |
| Accent (primary) | `#7A2E2A` (maroon / deep paprika red) | Buttons, active states, highlights |
| Accent (secondary) | `#A88556` (muted gold) | Selected, hover states, subtle decoration |
| Border / divider | `#D8CDB5` (soft sepia line) | Like the margins in an old book |

### Typography

| Use | Family | Fallback chain |
|---|---|---|
| Body text (Latin) | **Lora** or **Crimson Pro** | Serif fallback: `Georgia, "Times New Roman", serif` |
| Body text (Devanagari) | **Noto Serif Devanagari** | The serif (not sans) variant — matches the book aesthetic |
| Headings | Same as body, but heavier weight / slight size step | Avoid display fonts; the content is the star |
| Monospace (if needed for slugs/ids) | **Iosevka Slab** or **IBM Plex Mono Slab** | A warm monospace, not a tech-y one |

Marathi and English text must visually harmonize — same x-height, same color, same weight. The reader should never feel a "switch" between scripts.

### Spacing & layout

- Generous line height (1.6–1.7) — slow, contemplative reading.
- Generous padding around content blocks.
- No heavy borders, no card shadows. Use subtle background-tone differences instead.
- Maximum reading width capped (~70 ch) for canonical text passages — like a book column.

### Iconography & ornamentation

- Subtle decorative elements OK in moderation — e.g., a small flourish (•) between question and answer, a small lotus/saffron-edge ornament at section breaks.
- No emoji in system-generated text. Emoji-laden modern UI feels off here.
- Devotional symbols (e.g., 🌸 — already used in source files as section markers) can appear when *in source quotes* but should not be UI-generated.

### Interaction feel

- Transitions are slow and gentle (200–300ms ease), not snappy. The tool's rhythm should match contemplative reading.
- Hover states are subtle tonal shifts, not color flashes.
- Selection highlights use the muted gold accent, not blue.

## Alternatives considered

- **Modern minimalist** (Claude.ai / ChatGPT style — white background, sans-serif, accent blue). Rejected as tonally wrong for the spiritual content domain.
- **Vibrant Indic-religious palette** (saffron/orange, bright red, gold leaf). Rejected as too visually loud for a contemplative tool. Saffron has strong cultural weight but reads as decorative-festive rather than studious-reverential.
- **Dark mode default** (a contemplative dark theme). Rejected because (a) older devotees prefer light backgrounds (per audience demographics, PRD §2), (b) "old yellow pages" doesn't translate to dark mode without losing its essence. A dark variant can be added later if requested.
- **Pure black-on-white "academic paper" look.** Closer to right than modern minimalist, but missing the warmth. Rejected as too austere.

## Consequences

**Positive:**
- The visual identity *is* a statement — devotees opening the app feel they've opened a book of the tradition, not a software product.
- Bilingual text (EN + MR) harmonizes naturally — both rendered in warm serifs of compatible weight.
- The aesthetic constrains future UI choices, preventing visual drift (no flashy notifications, no neon badges).
- Strong differentiation from generic AI chat tools — devotees won't say "oh, another ChatGPT." Instead: "this feels like our literature."

**Negative:**
- More opinionated than "let the framework defaults take over." Requires deliberate font choices, color hexes pinned in code, design QA during polish.
- Devanagari fonts must be loaded explicitly — Noto Serif Devanagari is ~200 KB woff2. Acceptable.
- Some standard UI patterns (e.g., flat material buttons, sharp drop shadows) don't fit and need to be reworked.
- A future designer joining the project must be briefed on the aesthetic; can't assume modern-product instincts.

## Implementation notes

- Capture the exact hex codes and font fallback chain in `RFC-004 (Chat UI & UX)` as CSS custom properties.
- Test rendering of Marathi headings + body across Safari, Chrome, Firefox before locking the font choice.
- The dashboard already built at `tools/attribution-dashboard.html` uses the modern light theme and is not bound by this ADR — it's an internal curator tool, not the user-facing chat. No retrofit needed.

## References

- [PRD.md §4 Phase 2 — Modes, §6 Constraints](../PRD.md)
- [RFC-001 §Demo UX requirements](../rfc/RFC-001-demo-mvp.md)
- RFC-004 (Chat UI & UX) — implementation surface for this ADR.
- ADR-004 (Bilingual from day 1) — bilingual harmony was a driver.
