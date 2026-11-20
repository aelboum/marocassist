/**
 * Strict, nonce-based Content Security Policy for every page (Phase 1
 * finding S-10), following the Next.js 16 guide bundled with the installed
 * version (`node_modules/next/dist/docs/01-app/02-guides/content-security-policy.md`).
 *
 * A fresh random nonce per request; Next.js reads it from the request's
 * CSP header and attaches it to its own scripts and inline styles. Pages
 * are rendered per request (the root layout reads the locale cookie), so
 * the nonce is never baked into a cached page.
 *
 * - `script-src 'nonce-…' 'strict-dynamic'`: no inline or injected script
 *   runs without the nonce; `'unsafe-eval'` only in `next dev`.
 * - `connect-src 'self'`: the browser talks to this origin only (the API
 *   is same-origin behind the edge; no third party, no AI provider).
 * - No `unsafe-inline` anywhere.
 */

import { NextResponse, type NextRequest } from "next/server";

export function buildCsp(nonce: string, { dev, https }: { dev: boolean; https: boolean }): string {
  const directives = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    `style-src 'self' 'nonce-${nonce}'`,
    "img-src 'self' blob: data:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ];
  if (https) directives.push("upgrade-insecure-requests");
  return directives.join("; ");
}

function newNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes));
}

export function proxy(request: NextRequest) {
  const nonce = newNonce();
  const csp = buildCsp(nonce, {
    dev: process.env.NODE_ENV === "development",
    https: request.nextUrl.protocol === "https:",
  });
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  matcher: [
    {
      source: "/((?!_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
