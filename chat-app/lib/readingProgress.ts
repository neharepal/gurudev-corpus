/**
 * Reading progress persistence — localStorage, SSR-safe.
 *
 * Key: `gd:read:progress`
 * Shape: ProgressRecord[] (most-recently-read first after sorting by lastReadAt desc)
 *
 * Cap: 20 entries, oldest dropped first.
 */

export type ProgressRecord = {
  slug: string;
  workTitle: string;
  page: number;
  totalPages: number;
  lastReadAt: number; // Date.now()
};

const KEY = "gd:read:progress";
const MAX_ENTRIES = 20;

/** Returns all progress records, sorted most-recent first. */
export function loadProgress(): ProgressRecord[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as ProgressRecord[];
    if (!Array.isArray(parsed)) return [];
    return parsed.slice().sort((a, b) => b.lastReadAt - a.lastReadAt);
  } catch {
    return [];
  }
}

/**
 * Upsert a progress record by slug.
 * Replaces any existing entry for the same slug, then caps the list at MAX_ENTRIES
 * (dropping the oldest by lastReadAt).
 */
export function upsertProgress(rec: ProgressRecord): void {
  if (typeof window === "undefined") return;
  try {
    const raw = localStorage.getItem(KEY);
    let existing: ProgressRecord[] = [];
    if (raw) {
      const parsed = JSON.parse(raw) as unknown;
      if (Array.isArray(parsed)) {
        existing = parsed as ProgressRecord[];
      }
    }
    // Remove any previous entry for this slug.
    const filtered = existing.filter((r) => r.slug !== rec.slug);
    // Prepend the new record.
    const updated = [rec, ...filtered];
    // Cap to MAX_ENTRIES — drop oldest by lastReadAt.
    const capped =
      updated.length > MAX_ENTRIES
        ? updated
            .slice()
            .sort((a, b) => b.lastReadAt - a.lastReadAt)
            .slice(0, MAX_ENTRIES)
        : updated;
    localStorage.setItem(KEY, JSON.stringify(capped));
  } catch {
    // Storage unavailable or quota exceeded — silent failure.
  }
}

/** Remove the progress record for a given slug. */
export function removeProgress(slug: string): void {
  if (typeof window === "undefined") return;
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return;
    const filtered = (parsed as ProgressRecord[]).filter(
      (r) => r.slug !== slug,
    );
    localStorage.setItem(KEY, JSON.stringify(filtered));
  } catch {
    // Silent failure.
  }
}
