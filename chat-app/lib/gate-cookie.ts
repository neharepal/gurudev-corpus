// Shared constants for the invite-code + sadhak-name cookies (RFC-016 §3).
// Extracted here so route.ts files only expose HTTP handlers and stay
// compliant with Next 15 app-router linting.

export const COOKIE_NAME = "gurudev-invite";
export const NAME_COOKIE = "gurudev-sadhak-name";
export const COOKIE_MAX_AGE_SEC = 60 * 60 * 24 * 30;   // 30 days
