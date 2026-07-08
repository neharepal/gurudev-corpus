/** Short preview text for a saved thread. Pure. Mirrors buildAnswerText's field
 * priority (chat/page.tsx): QA → framing/synthesis/first citation; Pravachan →
 * thesis/first example. */
import type { QAAnswer, PravachanAnswer } from "../data/mock-conversations";

export function answerSnippet(
  answer: QAAnswer | PravachanAnswer,
  max = 140,
): string {
  let text = "";
  if (answer.kind === "qa") {
    text =
      answer.framing ||
      answer.synthesis ||
      answer.citations?.[0]?.quote?.body ||
      "";
  } else {
    text = answer.thesis || answer.examples?.[0]?.quote?.body || "";
  }
  text = text.replace(/\s+/g, " ").trim();
  return text.length > max ? `${text.slice(0, max).trimEnd()}…` : text;
}
