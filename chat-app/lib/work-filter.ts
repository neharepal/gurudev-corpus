// Reading-picker filter: match a user's typed query against a work's
// display title AND its roman `title_en` gloss. Marathi/Devanagari-titled
// books get `title_en` populated so that typing "charitra" or "pathway"
// surfaces `गुरुदेव...चरित्र...` even though the display stays Devanagari.

export type WorkForFilter = {
  title: string;
  title_en?: string;
};

/** True if the query (case-insensitive) is a substring of either
 *  `title` or `title_en`. Empty query matches everything.
 */
export function matchesWorkQuery(work: WorkForFilter, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  if (work.title.toLowerCase().includes(q)) return true;
  const te = (work.title_en ?? "").toLowerCase();
  return te ? te.includes(q) : false;
}

/** Filter a list of works by `matchesWorkQuery`. */
export function filterWorksByQuery<T extends WorkForFilter>(
  works: readonly T[],
  query: string,
): T[] {
  return works.filter((w) => matchesWorkQuery(w, query));
}
