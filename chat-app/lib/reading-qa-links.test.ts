// RFC-023 — unit tests for the Reading-Q&A link helpers.
//
// The helpers are dead-simple, but they're the touch-point for the U2 fix
// (same-slug drawer close), so their contract should never drift silently.

import { describe, it, expect } from "vitest";
import type { PassageLink } from "../data/mock-conversations";
import { buildReadingLinkHref, isSameSlug } from "./reading-qa-links";

describe("buildReadingLinkHref", () => {
  it("emits /read/<slug>?page=N&lang=<lang> in the expected order", () => {
    const href = buildReadingLinkHref(
      { workSlug: "kakanchi-pravachane", page: 47 },
      { lang: "en" },
    );
    expect(href).toBe("/read/kakanchi-pravachane?page=47&lang=en");
  });

  it("honors the Marathi lang toggle", () => {
    const href = buildReadingLinkHref(
      { workSlug: "kakanchi-pravachane", page: 12 },
      { lang: "mr" },
    );
    expect(href).toBe("/read/kakanchi-pravachane?page=12&lang=mr");
  });

  it("accepts the full PassageLink shape (extra fields are ignored)", () => {
    const link: PassageLink = {
      label: "where Gurudev discusses nama-smaran",
      workSlug: "pathway-to-god-in-hindi-literature",
      page: 3,
      workTitle: "Pathway to God in Hindi Literature",
    };
    const href = buildReadingLinkHref(link, { lang: "en" });
    expect(href).toBe(
      "/read/pathway-to-god-in-hindi-literature?page=3&lang=en",
    );
  });
});

describe("isSameSlug", () => {
  it("returns true when workSlug matches currentSlug exactly", () => {
    expect(
      isSameSlug({ workSlug: "kakanchi-pravachane" }, "kakanchi-pravachane"),
    ).toBe(true);
  });

  it("returns false when the slugs differ", () => {
    expect(
      isSameSlug({ workSlug: "kakanchi-pravachane" }, "mysticism-in-maharashtra"),
    ).toBe(false);
  });

  it("is case-sensitive (slugs are canonical, so casing must match)", () => {
    // A drift from canonical casing IS a different slug — /read/<slug> would
    // 404 anyway. Documenting the contract, not endorsing sloppy input.
    expect(
      isSameSlug({ workSlug: "Kakanchi-Pravachane" }, "kakanchi-pravachane"),
    ).toBe(false);
  });

  it("returns false on empty/missing slug either side", () => {
    expect(isSameSlug({ workSlug: "" }, "kakanchi-pravachane")).toBe(false);
    expect(isSameSlug({ workSlug: "kakanchi-pravachane" }, "")).toBe(false);
  });

  it("recognises a cross-work link (different slug) with a workTitle carried", () => {
    // Cross-work links come with `workTitle` so the label can annotate the
    // link with the target book — the helper still only cares about slug.
    const link: PassageLink = {
      label: "the parallel passage in Kakanchi Pravachane",
      workSlug: "kakanchi-pravachane",
      page: 5,
      workTitle: "Kakanchi Pravachane",
    };
    expect(isSameSlug(link, "pathway-to-god-in-hindi-literature")).toBe(false);
  });
});
