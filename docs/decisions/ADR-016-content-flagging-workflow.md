# ADR-016: Content-flagging workflow — flag queue, review dashboard, and apply CLI

**Status:** ACCEPTED
**Date:** 2026-06-27
**Author:** Neha (with Claude)

## Context

RFC-004 §"Content flagging mechanism" specified:

- A per-answer `[⚐]` report button opening a category-selector modal.
- Storage in `03_catalog/flag_queue.yaml` (append-only YAML).
- A `/admin/flags` review dashboard for the maintainer.
- A corpus-update workflow: fix the source `text.md`, re-embed, mark flag
  applied.

The initial F16 build (commit `6aa52fb`) wired the buttons but used a generic
free-text modal and wrote to `logs/issue_reports.jsonl`. F21 and the garble
Phase 2 work then completed the full RFC-004 specification:

- Added the category-radio modal ("Wrong attribution", "Quoted text doesn't
  match the source", etc.) and WhatsApp share menu.
- Migrated storage from `jsonl` to the RFC-004 YAML format
  (`03_catalog/flag_queue.yaml`).
- Built the `/admin/flags` review dashboard.
- Built `tools/apply_flags.py`, the maintainer CLI.
- Extended `/report` with an optional `correction` path for per-paragraph
  in-reader corrections (garble Phase 2).

## Decision

### Flag queue (`03_catalog/flag_queue.yaml`)

`POST /report` on `tools/server.py` appends a flag entry to
`03_catalog/flag_queue.yaml`. The YAML entry shape matches the RFC-004
specification:

```yaml
flags:
  - flag_id: <uuid>
    flagged_at: <ISO>
    category: <wrong-attribution|quoted-text-mismatch|not-in-corpus|
               translation-issue|missing-context|mislabeled-source|other>
    detail: "<optional free text>"
    conversation:
      mode: qa
      language: en
      question: "..."
      answer: "..."
      citations: [...]
    correction:          # present only for in-reader paragraph corrections
      slug: <work-slug>
      page: <int>
      paragraphN: <int>
      original: "..."
      corrected: "..."
    status: pending      # pending | approved | rejected | applied
    review_notes: ""
    resolved_at: null
```

The `correction` block is populated by the in-reader "suggest correction"
affordance (F18): the user highlights a paragraph, submits the corrected text,
and it arrives in the flag queue alongside the issue-report flags. Maintainer
review decides whether to apply it.

### Report modal (frontend)

`AnswerToolbar` opens a modal with:
- **Category radios** (per RFC-004): Wrong attribution / Quoted text doesn't
  match the source / Mentions something not actually in the corpus / Translation
  or paraphrase issue / Missing important context / Sources mislabeled or in
  wrong section / Other.
- **Optional detail textarea.**
- Auto-attached context: question, answer, all citations, conversation id,
  timestamp, language.
- Confirmation toast: "Thank you. Neha will review and correct if needed."
  (Marathi variant when interface language is Marathi.)

### WhatsApp share menu

`AnswerToolbar`'s share button now opens a share menu (per RFC-004 §WhatsApp
share):
- **WhatsApp**: `https://wa.me/?text=<encoded question + answer + citations>`
- **Copy link** (copy answer text to clipboard)
- **More…** (native Web Share API on mobile, if available)

### `/admin/flags` review dashboard (`tools/server.py`)

A `GET /admin/flags` endpoint returns all flag entries. The maintainer
dashboard (`chat-app/app/admin/flags/`) renders each flag with:
- Full flag context (category, detail, question, answer, citations, correction
  block if present).
- **Approve** (`POST /admin/flags/{flag_id}/approve`) — sets status
  `approved`; an approved correction is ready for `apply_flags.py`.
- **Reject** (`POST /admin/flags/{flag_id}/reject`) — sets status `rejected`.

The dashboard is not auth-gated in v1 (invite-only context); post-auth it
should be restricted to the maintainer account.

### `tools/apply_flags.py` maintenance CLI

The maintainer CLI for the corpus-correction half of the workflow:

1. **Review** (`apply_flags.py review`): lists all `approved` corrections in
   the queue (those with a `correction` block and `status=approved`).
2. **Apply** (`apply_flags.py apply <flag_id>`):
   - Reads the source `text.md` for the flagged work.
   - Creates a `.bak` backup of the original.
   - Applies the corrected text at the flagged paragraph position.
   - Prints a diff for the maintainer to inspect.
   - Marks the flag as `applied` in the queue.
3. **Re-embed**: after applying, the maintainer re-runs the chunker and
   embedder for that work; `POST /admin/reload` picks up the updated index
   live.

Flags without a `correction` block (general issue reports) are reviewed in the
dashboard but not auto-applied; those require a manual source fix.

## Alternatives considered

- **Postgres / Supabase for flag storage.** RFC-004 named Supabase as the
  post-demo target. For v1 demo (invite-only, low flag volume), a YAML file is
  simpler, readable with any text editor, and requires no external service. The
  YAML format matches the RFC-004 schema; migration to Supabase is an import
  step.
- **In-app admin UI only (no CLI).** The apply step involves file mutations,
  backup creation, and diffs — better expressed as a CLI than an API endpoint.
  The web dashboard handles the approve/reject decision; the CLI handles the
  application.
- **Auto-apply approved corrections without maintainer review.** Rejected:
  corrections touch source `text.md` files (the canonical corpus). Requiring
  explicit `apply_flags.py apply` keeps a human in the loop on every mutation.
- **Write corrections directly to `text.md` from the in-reader UI.** Rejected:
  that is direct user write access to the canonical corpus. The flag queue +
  maintainer approval is the required gate.

## Consequences

**Positive:**
- The complete RFC-004 flagging section is now implemented: report → queue →
  review → apply → re-embed.
- In-reader paragraph corrections (F18) flow through the same queue and review
  path as answer-level flags.
- The YAML queue is a plain file, auditable, and diff-able in git.
- `apply_flags.py` makes corpus corrections traceable: backup, diff, status
  update in one command.

**Negative:**
- The `/admin/flags` dashboard has no auth in v1. Anyone who can reach the
  backend URL can approve/reject flags. This is acceptable in the invite-only
  demo; post-launch auth is required.
- `apply_flags.py` applies corrections by paragraph index; if the `text.md`
  is re-paginated between flag creation and apply, the index may be stale.
  Mitigated by the diff display (maintainer sees what changed before confirming).

## References

- [RFC-004 Chat UI & UX](../rfc/RFC-004-chat-ui-and-ux.md) — §Content flagging
  mechanism; this ADR records the implementation (amended 2026-06-27)
- [ADR-011 Structured output contract](ADR-011-structured-output-contract.md)
  — `clean_quote_body` garble cleaner (Phase 1); flag queue is Phase 2
- QA findings F16, F18, F21 in [docs/qa-findings-2026-06-25.md](../qa-findings-2026-06-25.md)
- Commits: `6aa52fb` (F16 activate buttons), `4822335` (RFC-004 modal +
  WhatsApp), `804134d` (category field), `25ab503` (YAML migration),
  `077388b` (tests), `486f4a9` + `61ab359` (correction path),
  `de61c5b` (`apply_flags.py`), `d0fb2dd` (dashboard + approval gating)
