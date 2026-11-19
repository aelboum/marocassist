// Plain JavaScript: `next start` loads this file at run time and the runtime
// image has no TypeScript compiler (same reasoning as SaaS-OS's frontend).
//
// Security headers for every page. A strict, nonce-based Content Security
// Policy is a Phase 2 task (docs/phase-1/PHASE1_REPORT.md, open issues):
// Next.js needs per-request nonces for its inline bootstrap scripts, which
// requires middleware. Until then the policy below blocks framing, plugins,
// foreign form targets and foreign base URLs, and restricts connections to
// this origin.

/** @type {import("next").NextConfig} */
const nextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  output: "standalone",
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "Content-Security-Policy",
            value: [
              "frame-ancestors 'none'",
              "object-src 'none'",
              "base-uri 'self'",
              "form-action 'self'",
              "connect-src 'self'",
            ].join("; "),
          },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
