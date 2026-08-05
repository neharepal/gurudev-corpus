// Regression pin for the "**bold** shows literally" bug — Neha caught this
// on prod 2026-08-05 after commit 4d170da promoted whyChosen to prime real
// estate above each quote. The fix (three renderInlineMd wraps at
// chat/page.tsx:1000+1020 and read/[slug]/page.tsx:1333) is invisible unless
// something like these tests keeps the renderer honest.
//
// These tests target the renderer directly. They pin the shape of the React
// nodes it produces so any future edit to render-inline-md.ts that fails to
// wrap `**bold**` in <strong> or `*italic*` in <em> will fail here first —
// before it reaches the browser and a user notices.
import { describe, it, expect } from "vitest";
import { isValidElement, type ReactNode } from "react";
import { renderInlineMd } from "./render-inline-md";

/** Walk the ReactNode tree returned by renderInlineMd and return the
 *  concatenated visible text (`**bold**` becomes "bold", NOT "**bold**"). */
function visibleText(node: ReactNode): string {
  if (node == null || node === false) return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(visibleText).join("");
  if (isValidElement(node)) {
    const children = (node.props as { children?: ReactNode }).children;
    return visibleText(children ?? "");
  }
  return "";
}

/** Collect the tag names of any wrapping elements ("strong", "em") produced. */
function wrappingTags(node: ReactNode): string[] {
  if (node == null || node === false) return [];
  if (typeof node === "string" || typeof node === "number") return [];
  if (Array.isArray(node)) return node.flatMap(wrappingTags);
  if (isValidElement(node)) {
    const t = typeof node.type === "string" ? [node.type] : [];
    const children = (node.props as { children?: ReactNode }).children;
    return [...t, ...wrappingTags(children ?? "")];
  }
  return [];
}

describe("renderInlineMd", () => {
  it("returns null for empty/nullish input", () => {
    expect(renderInlineMd(null)).toBeNull();
    expect(renderInlineMd(undefined)).toBeNull();
    expect(renderInlineMd("")).toBeNull();
  });

  it("passes plain text through unchanged", () => {
    const out = renderInlineMd("just a sentence");
    expect(visibleText(out)).toBe("just a sentence");
    expect(wrappingTags(out)).toEqual([]);
  });

  it("wraps **bold** in <strong>", () => {
    const out = renderInlineMd("this **word** is bold");
    expect(visibleText(out)).toBe("this word is bold");
    expect(wrappingTags(out)).toContain("strong");
  });

  it("wraps *italic* in <em>", () => {
    const out = renderInlineMd("this *word* is italic");
    expect(visibleText(out)).toBe("this word is italic");
    expect(wrappingTags(out)).toContain("em");
  });

  it("handles bold + italic in the same string", () => {
    const out = renderInlineMd("**hard** and *soft*");
    expect(visibleText(out)).toBe("hard and soft");
    const tags = wrappingTags(out);
    expect(tags).toContain("strong");
    expect(tags).toContain("em");
  });

  it.skip("(known limitation) nested italic inside bold — current BOLD_RE excludes any `*`", () => {
    // Documented limitation: BOLD_RE at render-inline-md.ts:23 uses
    // `[^*]+?` which forbids any `*` inside a bold span, so
    // `**foo *bar* baz**` doesn't collapse. Not a regression — LLM
    // output rarely nests emphasis. If the LLM starts doing this, this
    // test becomes the failing anchor for the fix.
    const out = renderInlineMd("**foo *bar* baz**");
    expect(visibleText(out)).toBe("foo bar baz");
  });

  it("regression: whyChosen-shaped string renders bold, not raw `**`", () => {
    // The literal shape the LLM emits for `c.whyChosen` — this is what was
    // showing up on prod as `**Gita 2.47**: ...` after 4d170da.
    const whyChosen = "**Gita 2.47**: Krishna's core injunction on action without attachment.";
    const out = renderInlineMd(whyChosen);
    const visible = visibleText(out);
    // Must not leak the ** markers.
    expect(visible).not.toContain("**");
    // The bold portion is rendered.
    expect(visible).toBe("Gita 2.47: Krishna's core injunction on action without attachment.");
    expect(wrappingTags(out)).toContain("strong");
  });

  it("regression: doctrinal paragraph with mid-sentence bold", () => {
    const para = "The seeker must **remember the Name** at all hours.";
    const out = renderInlineMd(para);
    expect(visibleText(out)).toBe("The seeker must remember the Name at all hours.");
    expect(wrappingTags(out)).toContain("strong");
  });

  it("does not consume single asterisks that aren't real emphasis", () => {
    // A stray `*` on its own or with whitespace on the inside should not
    // become <em>. Bare `*` remains visible in the output.
    const out = renderInlineMd("footnote: see * for source");
    expect(visibleText(out)).toBe("footnote: see * for source");
    expect(wrappingTags(out)).not.toContain("em");
  });

  it("leaves Devanagari content untouched around emphasis", () => {
    const out = renderInlineMd("**नामस्मरण** is the practice.");
    expect(visibleText(out)).toBe("नामस्मरण is the practice.");
    expect(wrappingTags(out)).toContain("strong");
  });
});
