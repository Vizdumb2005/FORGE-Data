import type { NextConfig } from "next";

const API_URL = process.env.API_URL ?? "http://api:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${API_URL}/api/v1/:path*`,
      },
      {
        source: "/api/:path*",
        destination: `${API_URL}/api/:path*`,
      },
    ];
  },
  async headers() {
    const isProd = process.env.NODE_ENV === "production";
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          {
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              // Next.js requires 'unsafe-inline' for its runtime styles; tighten with nonces in future
              "style-src 'self' 'unsafe-inline'",
              "script-src 'self' 'unsafe-eval'", // 'unsafe-eval' needed by Monaco editor
              "img-src 'self' data: blob:",
              "font-src 'self' data:",
              `connect-src 'self' ${isProd ? "" : "ws://localhost:* http://localhost:*"} wss://localhost`,
              "frame-ancestors 'none'",
              "object-src 'none'",
              "base-uri 'self'",
            ].join("; "),
          },
          // HSTS — only send over HTTPS in production
          ...(isProd
            ? [{ key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains; preload" }]
            : []),
        ],
      },
    ];
  },
  webpack(config, { dev }) {
    // Suppress "Critical dependency" warnings from monaco-editor
    config.module = config.module ?? {};
    config.module.exprContextCritical = false;

    // Speed up HMR by excluding heavy packages from file watching
    if (dev) {
      config.watchOptions = {
        ...config.watchOptions,
        ignored: ["**/node_modules/**", "**/.git/**"],
      };
    }

    return config;
  },
};

export default nextConfig;
