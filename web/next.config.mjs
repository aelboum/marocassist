// Plain JavaScript: `next start` loads this file at run time and the runtime
// image has no TypeScript compiler (same reasoning as SaaS-OS's frontend).
//
// Security headers for every page. The Content Security Policy itself is
// set per request, with a fresh nonce, by `proxy.ts` (Phase 1 finding
// S-10); the headers below are static.

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
