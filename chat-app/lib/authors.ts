// Author display-name convention (F7): never show "Ranade".
// Gurudev Ranade is always rendered as "Shri Gurudev" in attributions/headers.
// Other corpus authors get their proper display names; unknown ids are humanized.

const KNOWN: Record<string, string> = {
  gurudev_ranade: "Shri Gurudev",
  bhausaheb_maharaj: "Bhausaheb Maharaj",
  nimbargi_maharaj: "Nimbargi Maharaj",
  amburao_maharaj: "Amburao Maharaj",
  kakasaheb_tulpule: "Kakasaheb Tulpule",
};

export function authorDisplayName(author?: string | null): string {
  if (!author) return "";
  const raw = author.trim();
  const key = raw.toLowerCase().replace(/\s+/g, "_");
  if (KNOWN[key]) return KNOWN[key];
  // Any value mentioning "Ranade" collapses to "Shri Gurudev" (the convention).
  if (/ranade/i.test(raw)) return "Shri Gurudev";
  // Fallback: humanize an id like "some_author" -> "Some Author".
  return raw.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
