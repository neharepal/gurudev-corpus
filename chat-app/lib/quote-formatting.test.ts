import { describe, it, expect } from "vitest";
import {
  buildReadHref,
  buildAttribution,
  cleanParaphrase,
  formatCardAttribution,
  formatInlineAttribution,
} from "./quote-formatting";

const MIM_QUOTE = {
  kind: "canonical" as const,
  workId: "mysticism-in-maharashtra",
  workTitle: "Mysticism in Maharashtra",
  location: "Part I · Chapter II. Jñānadeva: Biographical Introduction",
  author: "gurudev_ranade",
  readPage: 25,
};

describe("buildReadHref", () => {
  it("builds a full URL when workId + readPage + lang are set", () => {
    expect(buildReadHref(MIM_QUOTE, { lang: "en" })).toBe(
      "/read/mysticism-in-maharashtra?page=25&lang=en"
    );
  });

  it("adds `from` when provided", () => {
    expect(buildReadHref(MIM_QUOTE, { lang: "en", fromUrl: "/chat?q=x" })).toBe(
      "/read/mysticism-in-maharashtra?page=25&lang=en&from=%2Fchat%3Fq%3Dx"
    );
  });

  it("returns just the base URL when readPage/lang missing", () => {
    const q = { kind: "canonical" as const, workId: "mysticism-in-maharashtra" };
    expect(buildReadHref(q)).toBe("/read/mysticism-in-maharashtra");
  });

  it("returns null for non-canonical quotes", () => {
    expect(
      buildReadHref({ kind: "athvani", workId: "some", readPage: 5 })
    ).toBeNull();
    expect(
      buildReadHref({ kind: "biography", workId: "some", readPage: 5 })
    ).toBeNull();
  });

  it("returns null when workId is missing", () => {
    expect(buildReadHref({ kind: "canonical", workId: "" } as any)).toBeNull();
  });

  it("returns null for undefined", () => {
    expect(buildReadHref(undefined)).toBeNull();
  });
});

describe("buildAttribution", () => {
  it("returns all three pieces when location is non-redundant", () => {
    const a = buildAttribution(MIM_QUOTE);
    expect(a.title).toBe("Mysticism in Maharashtra");
    expect(a.location).toBe(
      "Part I · Chapter II. Jñānadeva: Biographical Introduction"
    );
    expect(a.author).toBe("Shri Gurudev");
  });

  it("drops location when it just repeats the title", () => {
    const a = buildAttribution({
      ...MIM_QUOTE,
      location: "Mysticism in Maharashtra",
    });
    expect(a.location).toBe("");
  });

  it("drops location when it just repeats the author", () => {
    const a = buildAttribution({ ...MIM_QUOTE, location: "Shri Gurudev" });
    expect(a.location).toBe("");
  });

  it("drops location when it starts with the title", () => {
    const a = buildAttribution({
      ...MIM_QUOTE,
      location: "Mysticism in Maharashtra, Preface",
    });
    expect(a.location).toBe("");
  });

  it("drops location when it contains the author name", () => {
    const a = buildAttribution({
      ...MIM_QUOTE,
      location: "as told by Shri Gurudev in a private lecture",
    });
    expect(a.location).toBe("");
  });

  it("returns empty pieces for undefined quote", () => {
    expect(buildAttribution(undefined)).toEqual({ title: "", location: "", author: "" });
  });
});

describe("formatCardAttribution", () => {
  it("assembles the full ‘— Title, Location · Author’ line", () => {
    expect(formatCardAttribution(MIM_QUOTE)).toBe(
      "— Mysticism in Maharashtra, Part I · Chapter II. Jñānadeva: Biographical Introduction · Shri Gurudev"
    );
  });

  it("collapses to ‘— Title · Author’ when location is redundant", () => {
    const q = { ...MIM_QUOTE, location: "Mysticism in Maharashtra" };
    expect(formatCardAttribution(q)).toBe(
      "— Mysticism in Maharashtra · Shri Gurudev"
    );
  });
});

describe("formatInlineAttribution", () => {
  it("assembles ‘Title · Location’ (no author, no dash)", () => {
    expect(formatInlineAttribution(MIM_QUOTE)).toBe(
      "Mysticism in Maharashtra · Part I · Chapter II. Jñānadeva: Biographical Introduction"
    );
  });

  it("returns just the title when location is redundant", () => {
    const q = { ...MIM_QUOTE, location: "Mysticism in Maharashtra" };
    expect(formatInlineAttribution(q)).toBe("Mysticism in Maharashtra");
  });
});

describe("cleanParaphrase", () => {
  it("strips a leading 'Paraphrase:' prefix", () => {
    expect(
      cleanParaphrase("Paraphrase: Bhausaheb Maharaj gave valuable guidance.")
    ).toBe("Bhausaheb Maharaj gave valuable guidance.");
  });

  it("strips 'Translation:' and 'Gloss:' variants", () => {
    expect(cleanParaphrase("Translation: he was born in Umadi.")).toBe(
      "he was born in Umadi."
    );
    expect(cleanParaphrase("Gloss: the word means devotion.")).toBe(
      "the word means devotion."
    );
  });

  it("is case-insensitive on the label", () => {
    expect(cleanParaphrase("PARAPHRASE: content")).toBe("content");
    expect(cleanParaphrase("paraphrase: content")).toBe("content");
  });

  it("accepts a dash or em-dash separator", () => {
    expect(cleanParaphrase("Paraphrase - content")).toBe("content");
    expect(cleanParaphrase("Paraphrase — content")).toBe("content");
  });

  it("leaves clean paraphrases unchanged", () => {
    expect(cleanParaphrase("Bhausaheb Maharaj gave valuable guidance.")).toBe(
      "Bhausaheb Maharaj gave valuable guidance."
    );
  });

  it("does NOT strip 'Paraphrase' when it's mid-sentence", () => {
    // Only strips a LEADING label — a mid-sentence "Paraphrase" is real content.
    expect(
      cleanParaphrase("The word 'paraphrase' means a restatement in other words.")
    ).toBe("The word 'paraphrase' means a restatement in other words.");
  });

  it("handles empty / undefined / whitespace inputs", () => {
    expect(cleanParaphrase("")).toBe("");
    expect(cleanParaphrase(undefined)).toBe("");
    expect(cleanParaphrase(null)).toBe("");
    expect(cleanParaphrase("   ")).toBe("");
  });
});
