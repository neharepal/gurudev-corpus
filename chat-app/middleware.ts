// RFC-016 §3 gate: redirect to /gate when the invite cookie is missing.
// Runs on every non-static request. Public routes (/, /gate, /api/gate) skip
// the check; every other page + all backend proxies require the cookie.
//
// The cookie value itself is validated by the FastAPI backend (INVITE_CODE
// env), not here — this middleware only enforces "have a cookie at all".
// Invalid cookies bounce back here with ?reason=invalid via the API proxies.

import { NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = new Set([
  "/gate",
]);
const PUBLIC_API_PATHS = new Set([
  "/api/gate",
]);
const COOKIE_NAME = "gurudev-invite";

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Dev bypass — `npm run dev` sets NODE_ENV=development. Local testing must
  // not be blocked by the invite gate. In prod (Vercel) NODE_ENV=production is
  // the default, so the gate fires automatically once deployed.
  if (process.env.NODE_ENV !== "production") {
    return NextResponse.next();
  }

  // Static files, next internals, and public paths pass through.
  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon") ||
    pathname === "/paper-bg.jpg" ||
    pathname === "/lineage-portrait.jpg" ||
    PUBLIC_PATHS.has(pathname) ||
    PUBLIC_API_PATHS.has(pathname)
  ) {
    return NextResponse.next();
  }

  const hasCookie = !!req.cookies.get(COOKIE_NAME)?.value;
  if (hasCookie) return NextResponse.next();

  // For an API call, respond with 401 (client will surface + redirect) so we
  // don't send an HTML redirect to a fetch() that's expecting JSON.
  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "invite_required" }, { status: 401 });
  }

  // For a page navigation, redirect to /gate and remember where we came from.
  const url = req.nextUrl.clone();
  url.pathname = "/gate";
  url.search = `?from=${encodeURIComponent(pathname + req.nextUrl.search)}`;
  return NextResponse.redirect(url);
}

export const config = {
  // Run on everything except the images Next serves as static assets and the
  // internal manifest files. Middleware skips paths matching the exclude list.
  matcher: [
    "/((?!_next/static|_next/image|paper-bg\\.jpg|lineage-portrait\\.jpg).*)",
  ],
};
