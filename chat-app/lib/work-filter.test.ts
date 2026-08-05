import { describe, it, expect } from "vitest";
import { matchesWorkQuery, filterWorksByQuery } from "./work-filter";

describe("matchesWorkQuery", () => {
  it("empty query matches every work", () => {
    expect(matchesWorkQuery({ title: "काकांची प्रवचने" }, "")).toBe(true);
    expect(matchesWorkQuery({ title: "काकांची प्रवचने" }, "   ")).toBe(true);
  });

  it("matches a case-insensitive substring of `title`", () => {
    expect(matchesWorkQuery({ title: "Bhagavadgita" }, "gita")).toBe(true);
    expect(matchesWorkQuery({ title: "Bhagavadgita" }, "GITA")).toBe(true);
  });

  it("matches a substring of `title_en` when title is Devanagari", () => {
    const w = { title: "गुरुदेव रा. द. रानडे चरित्र व तत्वज्ञान",
                title_en: "Gurudev R. D. Ranade Charitra va Tatvajnan" };
    expect(matchesWorkQuery(w, "charitra")).toBe(true);
    expect(matchesWorkQuery(w, "tatvajnan")).toBe(true);
    expect(matchesWorkQuery(w, "ranade")).toBe(true);
  });

  it("matches Devanagari query against Devanagari title", () => {
    const w = { title: "काकांची प्रवचने", title_en: "Kakanchi Pravachane" };
    expect(matchesWorkQuery(w, "काकांची")).toBe(true);
    expect(matchesWorkQuery(w, "प्रवचने")).toBe(true);
  });

  it("returns false when query is in neither field", () => {
    const w = { title: "काकांची प्रवचने", title_en: "Kakanchi Pravachane" };
    expect(matchesWorkQuery(w, "geeta")).toBe(false);
  });

  it("handles missing title_en gracefully", () => {
    const w = { title: "Bhagavadgita" };
    expect(matchesWorkQuery(w, "geeta")).toBe(false);
    expect(matchesWorkQuery(w, "gita")).toBe(true);
  });

  it("regression: 'charitra' surfaces Marathi biography (Devanagari title)", () => {
    // The exact failure mode Neha called out — before title_en, a roman
    // query against a Devanagari-titled book returned no match.
    const w = { title: "गुरुदेव रा. द. रानडे चरित्र व तत्वज्ञान",
                title_en: "Gurudev R. D. Ranade Charitra va Tatvajnan" };
    expect(matchesWorkQuery(w, "charitra")).toBe(true);
  });

  it("regression: 'pathway' surfaces Kannada-Marathi book", () => {
    const w = { title: "कन्नड परमार्थ सोपान (Kannad Parmarth Sopan, Marathi)",
                title_en: "Pathway to God in Kannada Literature" };
    expect(matchesWorkQuery(w, "pathway")).toBe(true);
    expect(matchesWorkQuery(w, "kannada literature")).toBe(true);
  });
});

describe("filterWorksByQuery", () => {
  const corpus = [
    { title: "Bhagavadgita", title_en: "Bhagavadgita" },
    { title: "काकांची प्रवचने", title_en: "Kakanchi Pravachane" },
    { title: "साधकाची आत्मकथा", title_en: "Sadhakachi Atmakatha" },
    { title: "महाराजांची सूत्रे", title_en: "Maharajanchi Sutre" },
  ];

  it("empty query returns all works", () => {
    expect(filterWorksByQuery(corpus, "")).toHaveLength(4);
  });

  it("matches by roman title_en for Devanagari-titled works", () => {
    const out = filterWorksByQuery(corpus, "sutre");
    expect(out).toHaveLength(1);
    expect(out[0].title).toBe("महाराजांची सूत्रे");
  });

  it("matches by shared substring across multiple works", () => {
    const out = filterWorksByQuery(corpus, "chi");
    // All three -chi endings: Sadhaka-chi, Kakan-chi, Maharajan-chi
    expect(out.map((w) => w.title_en).sort()).toEqual(
      ["Kakanchi Pravachane", "Maharajanchi Sutre", "Sadhakachi Atmakatha"].sort(),
    );
  });
});
