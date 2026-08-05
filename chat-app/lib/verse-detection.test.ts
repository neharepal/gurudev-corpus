import { describe, it, expect } from "vitest";
import { isVerseParagraph } from "./verse-detection";

describe("isVerseParagraph", () => {
  it("matches a pure Sanskrit shloka", () => {
    // Iśopaniṣad 2 as cited in BGPGR Chapter I
    const shloka = "कुर्वन्नेवेह कर्माणि जिजीविषेच्छतं समाः ।";
    expect(isVerseParagraph(shloka)).toBe(true);
  });

  it("matches a two-line shloka with citation tail", () => {
    // Second line of Iśopaniṣad 2 with citation
    const shloka = "एवं त्वयि नान्यथेतोऽस्ति न कर्म लिप्यते नरे ॥ Iśa. Up. 2.";
    expect(isVerseParagraph(shloka)).toBe(true);
  });

  it("does not match English prose with an inline diacritic word", () => {
    const prose =
      "The Iśopaniṣad tells us that we are born here below in this mortal world in order to do action.";
    expect(isVerseParagraph(prose)).toBe(false);
  });

  it("does not match English prose containing a short Devanagari word", () => {
    // e.g. "1. Fearlessness... अभयम्" style attribution line from BGPGR
    const line = "1. Fearlessness... अभयम्";
    expect(isVerseParagraph(line)).toBe(false);
  });

  it("returns false for empty or very short strings", () => {
    expect(isVerseParagraph("")).toBe(false);
    expect(isVerseParagraph("   ")).toBe(false);
    expect(isVerseParagraph("ॐ")).toBe(false); // single glyph, below MIN length
  });

  it("skips detection in Marathi-book context (isMarathi=true)", () => {
    // Whole-Devanagari paragraph should NOT be boxed in a Marathi book
    const marathi = "आम्ही आत्मानं विदित्वा तेण उपाध्येन गुरुण उपसंधाय";
    expect(isVerseParagraph(marathi, { isMarathi: true })).toBe(false);
    expect(isVerseParagraph(marathi, { isMarathi: false })).toBe(true);
  });

  it("matches Bengali script paragraphs", () => {
    // Sample Bengali text (Rabindranath's opening line paraphrase, illustrative)
    const bengali = "আমার ভিতর ও বাহিরে অন্তরে অন্তরে আছ তুমি হৃদয়জুড়ে।";
    expect(isVerseParagraph(bengali)).toBe(true);
  });

  it("respects a custom threshold", () => {
    // Half-and-half — with default 0.5 threshold, might tip either way
    // depending on exact ratio; explicit 0.9 threshold rejects.
    const mixed = "कर्म means action or work in the philosophical sense.";
    expect(isVerseParagraph(mixed, { threshold: 0.9 })).toBe(false);
  });

  it("returns false for null / undefined-ish inputs (defensive)", () => {
    expect(isVerseParagraph(undefined as unknown as string)).toBe(false);
    expect(isVerseParagraph(null as unknown as string)).toBe(false);
  });
});
