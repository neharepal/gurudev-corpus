"use client";

import { useEffect, useState } from "react";

/**
 * useState backed by localStorage under a fixed key.
 *
 * First render returns `initial` (matches SSR / avoids hydration mismatch).
 * After mount, the effect reads from localStorage and replaces state if a
 * stored value is present. Subsequent state changes are persisted back.
 *
 * The brief flash between mount and the localStorage read is intentional
 * — Next.js client components can't read storage during SSR without a
 * hydration-mismatch warning.
 *
 * For Gurudev Sangrah this is the demo-grade persistence layer. Real
 * cross-device sync is on the post-demo todo (auth + server-side state).
 */
export function usePersistentState<T>(
  key: string,
  initial: T,
  opts?: { skipHydration?: boolean },
): readonly [T, React.Dispatch<React.SetStateAction<T>>] {
  const [state, setState] = useState<T>(initial);
  const [hydrated, setHydrated] = useState(false);
  const skipHydration = opts?.skipHydration ?? false;

  // Hydrate from storage on mount (and whenever the key changes — relevant
  // when the route param changes, e.g. user navigates between two reading
  // works in the same session).
  //
  // `skipHydration` lets a caller keep `initial` as the source of truth and
  // NOT be overwritten by localStorage — used by the reader when a `?page=`
  // deep-link must win over the persisted page. Without this, the hydration
  // read here (which also re-runs under dev StrictMode) clobbers the URL page
  // back to whatever was last stored. Persistence of subsequent changes still
  // works, so Prev/Next are remembered.
  useEffect(() => {
    if (skipHydration) {
      setHydrated(true);
      return;
    }
    try {
      const stored = localStorage.getItem(key);
      if (stored !== null) {
        setState(JSON.parse(stored) as T);
      } else {
        setState(initial);
      }
    } catch {
      // Bad JSON or storage unavailable — fall back to initial.
      setState(initial);
    }
    setHydrated(true);
    // We intentionally do NOT depend on `initial` — only on key. Re-hydrating
    // every time the caller passes a new initial value would defeat the
    // persistence.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  // Persist state changes. Gate on `hydrated` so the initial render doesn't
  // immediately clobber the stored value with the default.
  useEffect(() => {
    if (!hydrated) return;
    try {
      localStorage.setItem(key, JSON.stringify(state));
    } catch {
      // Quota exceeded or storage disabled — silent failure is acceptable
      // here, the page works without persistence.
    }
  }, [key, state, hydrated]);

  return [state, setState] as const;
}
