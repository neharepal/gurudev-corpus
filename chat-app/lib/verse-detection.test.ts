import { describe, it, expect } from "vitest";
import {
  isVerseParagraph,
  splitVerseBlocks,
  splitVerseCitation,
  mergeSentenceContinuations,
} from "./verse-detection";

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

  it("matches an Ancient Greek quotation (basic Greek + polytonic)", () => {
    // From Plotinus, Enneads VI.9 — cited in MiM Preface + BGPGR
    const greek =
      "οὐ γάρ τι ἐκινεῖτο παρ' αὐτῷ, οὐ θυμός, οὐκ ἐπιθυμία ἄλλου παρῆν αὐτῷ ἀναβεβηκότι, ἀλλ᾿ οὐδὲ λόγος οὐδέ τις νόησις.";
    expect(isVerseParagraph(greek)).toBe(true);
  });

  it("matches a Greek quote wrapped by Ranade's ellipsis dots", () => {
    // Ranade often prefixes/suffixes Greek shlokas with `.....` runs — the
    // dots are whitespace-stripped out by the normalizer, and the remaining
    // characters are majority Greek, so should still match.
    const greek =
      "..................................οὐ γάρ τι ἐκινεῖτο παρ' αὐτῷ, οὐ θυμός............... οὐδὲ τῶν καλῶν, ἀλλὰ καὶ τὸ καλὸν ἤδη ὑπερθέων, ὑπερ- βὰς ἤδη καὶ τὸν τῶν ἀρετῶν χορόν .........";
    expect(isVerseParagraph(greek)).toBe(true);
  });

  it("does not match English prose with a single Greek loanword", () => {
    // Just because "logos" gets a Greek gloss doesn't make the whole
    // sentence a verse.
    const prose = "The Greek term logos (λόγος) has many philosophical uses.";
    expect(isVerseParagraph(prose)).toBe(false);
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

describe("splitVerseBlocks", () => {
  it("returns a single prose block for pure English", () => {
    const b = splitVerseBlocks("The Bhagavadgita teaches that we must act without attachment.");
    expect(b).toHaveLength(1);
    expect(b[0]).toEqual({
      type: "prose",
      text: "The Bhagavadgita teaches that we must act without attachment.",
    });
  });

  it("returns a single verse block for a pure Sanskrit shloka", () => {
    const shloka = "कुर्वन्नेवेह कर्माणि जिजीविषेच्छतं समाः ।";
    const b = splitVerseBlocks(shloka);
    expect(b).toHaveLength(1);
    expect(b[0].type).toBe("verse");
  });

  it("splits a mixed English + trailing Greek quotation (MiM Ideal Sage case)", () => {
    // Simplified version of the paragraph from MiM Preface p4: English
    // commentary about Plotinus followed by a Greek Enneads quotation.
    const mixed =
      "One of the most celebrated descriptions of the Ideal Sage occurs in Plotinus, where he writes: " +
      "..................................οὐ γάρ τι ἐκινεῖτο παρ᾿ αὐτῷ, οὐ θυμός, οὐκ ἐπιθυμία ἄλλου παρῆν αὐτῷ ἀναβεβηκότι, ἀλλ᾿ οὐδὲ λόγος οὐδέ τις νόησις οὐδ᾿ ὅλως αὐτός ..........";
    const b = splitVerseBlocks(mixed);
    expect(b.length).toBeGreaterThanOrEqual(2);
    expect(b[0].type).toBe("prose");
    expect(b[0].text).toMatch(/Plotinus/);
    const verse = b.find((x) => x.type === "verse");
    expect(verse).toBeDefined();
    expect(verse!.text).toMatch(/κινε/);
  });

  it("handles an English → Greek → English sandwich (long English surround)", () => {
    // English majority so whole-para verse shortcut doesn't fire; the
    // Greek run in the middle still gets extracted.
    const mixed =
      "The Greek philosopher Plotinus, writing in the Enneads, describes " +
      "the ideal sage in terms that Ranade often cites in his commentaries " +
      "on the mystical life. His most celebrated formulation reads: " +
      "οὐ γάρ τι ἐκινεῖτο παρ᾿ αὐτῷ, οὐ θυμός, οὐκ ἐπιθυμία ἄλλου παρῆν αὐτῷ ἀναβεβηκότι " +
      "which we may render as: nothing stirred within him, no anger, no desire, " +
      "no reason, no thought, no self was present to him — a description of the " +
      "sage completely at rest in the One, beyond even the virtues.";
    const b = splitVerseBlocks(mixed);
    expect(b).toHaveLength(3);
    expect(b[0].type).toBe("prose");
    expect(b[1].type).toBe("verse");
    expect(b[2].type).toBe("prose");
    expect(b[2].text).toMatch(/render/);
  });

  it("does NOT split on inline loanwords like `(λόγος)`", () => {
    const mixed = "The Greek term logos (λόγος) has many philosophical uses.";
    const b = splitVerseBlocks(mixed);
    expect(b).toHaveLength(1);
    expect(b[0].type).toBe("prose");
  });

  it("respects isMarathi and returns whole paragraph as prose", () => {
    const marathi = "आम्ही आत्मानं विदित्वा तेण उपाध्येन गुरुण उपसंधाय";
    const b = splitVerseBlocks(marathi, { isMarathi: true });
    expect(b).toHaveLength(1);
    expect(b[0].type).toBe("prose");
  });

  it("returns an empty array for empty input", () => {
    expect(splitVerseBlocks("")).toEqual([]);
    expect(splitVerseBlocks(undefined as unknown as string)).toEqual([]);
  });

  it("absorbs leading and trailing ellipsis dots into the verse run", () => {
    // Ranade's convention: ".....text....." wraps a quotation. The bordering
    // dot runs should be swallowed into the verse block so they don't render
    // as a leftover dot-only prose fragment above/below.
    const mixed =
      "The Greek philosopher Plotinus, writing in the Enneads, describes " +
      "the ideal sage in terms Ranade often cites in his commentaries on " +
      "the mystical life. He tells us: " +
      "..................................οὐ γάρ τι ἐκινεῖτο παρ᾿ αὐτῷ, οὐ θυμός, οὐκ ἐπιθυμία ἄλλου παρῆν αὐτῷ ἀναβεβηκότι, ἀλλ᾿ οὐδὲ λόγος οὐδέ τις νόησις........" +
      " and here Ranade closes the citation and returns to English commentary about the sage's stability.";
    const b = splitVerseBlocks(mixed);
    // We should get [prose, verse, prose] — no dot-only fragments.
    expect(b.length).toBe(3);
    expect(b[0].type).toBe("prose");
    expect(b[1].type).toBe("verse");
    expect(b[2].type).toBe("prose");
    // The prose blocks must NOT be dot-only fragments.
    expect(b[0].text.replace(/[.\s]/g, "").length).toBeGreaterThan(20);
    expect(b[2].text.replace(/[.\s]/g, "").length).toBeGreaterThan(20);
  });
});

describe("splitVerseCitation", () => {
  it("splits at the last `॥` and pulls a Roman.digit citation to citation", () => {
    // From BGPGR Ch XVIII / General Introduction — Ranade often ends a
    // shloka with `॥ XIII. 12-13.`
    const v =
      "हेयं यत्तत्प्रवक्ष्यामि यज्ज्ञात्वाऽमृतमस्तुते । अनादिमत्परं ब्रह्म न सत्तन्नासदुच्यते ॥ सर्वतः पाणिपादं तत्सर्वतोऽक्षिशिरोमुखम् । सर्वतः श्रुतिमल्लोके सर्वमातृत्य तिष्ठति ॥ XIII. 12-13.";
    const { verse, citation } = splitVerseCitation(v);
    expect(citation).toBe("XIII. 12-13.");
    expect(verse.endsWith("॥")).toBe(true);
    // Verse still contains both shloka lines
    expect(verse).toContain("पाणिपादं");
  });

  it("splits at last `॥` for Iśopaniṣad-style short citation", () => {
    const v = "एवं त्वयि नान्यथेतोऽस्ति न कर्म लिप्यते नरे ॥ Iśa. Up. 2.";
    const { verse, citation } = splitVerseCitation(v);
    expect(citation).toBe("Iśa. Up. 2.");
    expect(verse.endsWith("॥")).toBe(true);
  });

  it("returns null citation when verse has no reference tail", () => {
    const v = "कुर्वन्नेवेह कर्माणि जिजीविषेच्छतं समाः ।";
    const { verse, citation } = splitVerseCitation(v);
    expect(citation).toBeNull();
    expect(verse).toBe("कुर्वन्नेवेह कर्माणि जिजीविषेच्छतं समाः ।");
  });

  it("does NOT treat a long English sentence trailing the shloka as a citation", () => {
    // Only Latin+digits, short, comma-period-space content qualifies as a
    // citation — arbitrary trailing English prose does not.
    const v =
      "एवं त्वयि नान्यथेतोऽस्ति न कर्म लिप्यते नरे ॥ and here Ranade proceeds to gloss the meaning of the shloka in English.";
    const { citation } = splitVerseCitation(v);
    expect(citation).toBeNull();
  });

  it("fallback: finds a Latin citation when there is no closing `॥`", () => {
    // Some verses in the corpus miss the closing daṇḍa (OCR quirk). Still
    // extract the trailing "Iśa. Up. 2." style reference via the last-
    // foreign-char fallback.
    const v = "कुर्वन्नेवेह कर्माणि जिजीविषेच्छतं समाः  Iśa. Up. 2.";
    const { verse, citation } = splitVerseCitation(v);
    expect(citation).toBe("Iśa. Up. 2.");
    expect(verse).toContain("कर्माणि");
  });

  it("returns {verse: '', citation: null} for empty input", () => {
    expect(splitVerseCitation("")).toEqual({ verse: "", citation: null });
  });
});

describe("mergeSentenceContinuations", () => {
  it("merges when previous ends without terminator and current starts lowercase", () => {
    const input = [
      { n: 5, body: "The Mahārāshtra of Jñānadeva's time was a" },
      { n: 6, body: "free Mahārāshtra, yet unmolested by Mahomedan invaders." },
    ];
    const out = mergeSentenceContinuations(input);
    expect(out).toHaveLength(1);
    expect(out[0].n).toBe(5);
    expect(out[0].body).toBe(
      "The Mahārāshtra of Jñānadeva's time was a free Mahārāshtra, yet unmolested by Mahomedan invaders."
    );
  });

  it("joins across a hyphenated word-break with no space", () => {
    const input = [
      { n: 1, body: "the process of divine knowledge is a develop-" },
      { n: 2, body: "ment of the interior faculty of intuition." },
    ];
    const out = mergeSentenceContinuations(input);
    expect(out).toHaveLength(1);
    expect(out[0].body).toBe(
      "the process of divine knowledge is a development of the interior faculty of intuition."
    );
  });

  it("does NOT merge when previous ends with a full stop", () => {
    const input = [
      { n: 1, body: "The Mahārāshtra was a free country." },
      { n: 2, body: "moreover, its kings were all supreme." },
    ];
    const out = mergeSentenceContinuations(input);
    expect(out).toHaveLength(2);
    expect(out[0].body.endsWith(".")).toBe(true);
  });

  it("does NOT merge when current starts with an uppercase letter", () => {
    const input = [
      { n: 1, body: "the last word was" },
      { n: 2, body: "Mukundarāja who was..." }, // Uppercase M — likely new sentence with a name
    ];
    const out = mergeSentenceContinuations(input);
    expect(out).toHaveLength(2);
  });

  it("does NOT merge when current starts with a numeric marker", () => {
    // Ranade's `1. Title` / `(a) ...` conventions must stay as new blocks
    const input = [
      { n: 1, body: "the section that follows describes" },
      { n: 2, body: "1. The Condition of Mahārāshtra..." },
    ];
    const out = mergeSentenceContinuations(input);
    expect(out).toHaveLength(2);
  });

  it("does NOT merge across a sub-heading boundary", () => {
    const input = [
      { n: 1, body: "some prose ending without a period" },
      { n: 2, body: "2. Mukundarāja", is_subheading: true },
      { n: 3, body: "we must say a few words about him." },
    ];
    const out = mergeSentenceContinuations(input);
    expect(out).toHaveLength(3);
    expect(out[1].is_subheading).toBe(true);
  });

  it("chains multiple continuations into a single paragraph", () => {
    const input = [
      { n: 1, body: "the very long sentence starts here and" },
      { n: 2, body: "continues here and" },
      { n: 3, body: "finally ends here." },
    ];
    const out = mergeSentenceContinuations(input);
    expect(out).toHaveLength(1);
    expect(out[0].n).toBe(1);
    expect(out[0].body).toMatch(/starts here and continues here and finally ends here\.$/);
  });

  it("returns input unchanged when empty", () => {
    expect(mergeSentenceContinuations([])).toEqual([]);
  });
});
