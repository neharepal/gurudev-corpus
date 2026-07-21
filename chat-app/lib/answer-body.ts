// Deriving the paragraphs to render as the main body of a Q&A answer.
//
// The LLM has three fields that can carry paragraph-scale content:
//   - `framingParagraphs`: an array (preferred — structured, unambiguous)
//   - `framing`: a single string (may be one paragraph or wall-of-text)
//   - `synthesis`: intended as a 1-2 sentence closer
//
// Under normal operation, `framingParagraphs` (or a split of `framing`)
// carries the body and `synthesis` is a small closer. But on 2026-07-19
// the LLM put a full 4,800-char summary in `synthesis` — the meta layout
// doesn't render `synthesis`, so the reader saw an empty answer and asked
// "where is the summary?" for four turns before the LLM happened to hit
// the right shape.
//
// The prompt was tightened (case-b sub-modes prescribe the target field)
// but the model can still misbehave. This helper adds a rescue: in the
// meta layout, if the primary body slots are empty but `synthesis` is
// substantive AND there are no citations to render, promote `synthesis`
// to the body. Belt + suspenders on top of the prompt fix.

// Kept structurally-typed (no import from AskResponse) so the helper is
// trivially reusable and testable in isolation.
type AnswerLike = {
  framing?: string | null;
  framingParagraphs?: string[] | null;
  synthesis?: string | null;
  // Only used to know whether we're in the meta layout — the doctrinal
  // layout renders `synthesis` separately, so we must NOT promote it
  // to the body there (it'd render twice).
  citations?: Array<unknown> | null;
};

// The synthesis-promotion threshold. Below this, we treat a `synthesis`
// value as a small closer (its intended use) and don't promote it. Above
// this, it's almost certainly the body that got misplaced.
const SYNTHESIS_PROMOTION_MIN_CHARS = 400;

export function deriveBodyParagraphs(answer: AnswerLike): string[] {
  // Preferred: the structured array.
  if (answer.framingParagraphs && answer.framingParagraphs.length > 0) {
    return answer.framingParagraphs;
  }
  // Second choice: split the `framing` string on double newlines.
  const fromFraming = (answer.framing ?? "").split(/\n{2,}/).filter(Boolean);
  if (fromFraming.length > 0) {
    return fromFraming;
  }
  // Rescue case (Mukund #3): meta layout AND `synthesis` looks like it
  // was meant to be the body. Promote it.
  const synth = (answer.synthesis ?? "").trim();
  const isMetaLayout = !answer.citations || answer.citations.length === 0;
  if (isMetaLayout && synth.length >= SYNTHESIS_PROMOTION_MIN_CHARS) {
    // Split the synthesis into paragraphs too, so it renders the same way
    // structured `framingParagraphs` would.
    return synth.split(/\n{2,}/).filter(Boolean);
  }
  return [];
}

// True when `deriveBodyParagraphs` had to fall back to the synthesis
// rescue. Useful for dev-only telemetry (log "the safety net fired") so
// we can spot lingering LLM-shape misbehavior after the prompt fix.
export function bodyDerivationUsedSynthesisRescue(answer: AnswerLike): boolean {
  const hasFP = !!(answer.framingParagraphs && answer.framingParagraphs.length > 0);
  const framingSplits = (answer.framing ?? "").split(/\n{2,}/).filter(Boolean);
  const synth = (answer.synthesis ?? "").trim();
  const isMetaLayout = !answer.citations || answer.citations.length === 0;
  return (
    !hasFP
    && framingSplits.length === 0
    && isMetaLayout
    && synth.length >= SYNTHESIS_PROMOTION_MIN_CHARS
  );
}
