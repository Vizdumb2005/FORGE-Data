/**
 * Token management utilities.
 *
 * Security model:
 *  - Access token: stored in a JS-readable cookie ONLY so Next.js middleware
 *    can check auth on the edge. It is short-lived (15 min) so the exposure
 *    window from XSS is minimal.
 *  - Refresh token: stored exclusively in the httpOnly cookie set by the API
 *    server on /login and /refresh. The browser never reads or writes it.
 *    localStorage is NOT used for any token.
 */
import Cookies from "js-cookie";

const ACCESS_COOKIE = "forge_access_token";
const COOKIE_OPTS: Cookies.CookieAttributes = {
  sameSite: "Strict",
  secure: process.env.NODE_ENV === "production",
  // Not httpOnly here because Next.js middleware (edge runtime) needs to read
  // it client-side. The short TTL (15 min) limits XSS exposure.
};

// ── Accessors ─────────────────────────────────────────────────────────────────

export function getAccessToken(): string | null {
  return Cookies.get(ACCESS_COOKIE) ?? null;
}

// Refresh token is httpOnly — the browser cannot read it.
// The /refresh endpoint reads it automatically from the cookie jar.
export function getRefreshToken(): null {
  return null;
}

// ── Mutators ──────────────────────────────────────────────────────────────────

export function setTokens(access: string, _refresh?: string): void {
  // Only store the access token. The refresh token is managed server-side
  // via the httpOnly cookie set in the Set-Cookie response header.
  Cookies.set(ACCESS_COOKIE, access, COOKIE_OPTS);
}

export function clearTokens(): void {
  Cookies.remove(ACCESS_COOKIE, COOKIE_OPTS);
}

// ── JWT helpers ───────────────────────────────────────────────────────────────

interface JwtPayload {
  sub: string;
  exp: number;
  type: "access" | "refresh";
}

export function decodeAccessToken(token: string): JwtPayload | null {
  try {
    const [, payloadB64] = token.split(".");
    const json = atob(payloadB64.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(json) as JwtPayload;
  } catch {
    return null;
  }
}

export function isTokenExpired(token: string): boolean {
  const payload = decodeAccessToken(token);
  if (!payload) return true;
  return Date.now() / 1000 >= payload.exp - 30; // 30 s buffer
}
