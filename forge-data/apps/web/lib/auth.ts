/**
 * Token management utilities.
 * Tokens are stored in cookies (access) and localStorage (refresh) so the
 * Next.js middleware can read the access token server-side for route protection.
 */
import Cookies from "js-cookie";

const ACCESS_COOKIE = "forge_access_token";
const REFRESH_KEY = "forge_refresh_token";
const COOKIE_OPTS: Cookies.CookieAttributes = {
  sameSite: "Lax",
  secure: process.env.NODE_ENV === "production",
  // No httpOnly — middleware reads via req.cookies on the edge, which does NOT
  // require httpOnly.  Real httpOnly cookies must be set by the API server.
};

// ── Accessors ─────────────────────────────────────────────────────────────────

export function getAccessToken(): string | null {
  return Cookies.get(ACCESS_COOKIE) ?? null;
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH_KEY);
}

// ── Mutators ──────────────────────────────────────────────────────────────────

export function setTokens(access: string, refresh: string): void {
  Cookies.set(ACCESS_COOKIE, access, COOKIE_OPTS);
  if (typeof window !== "undefined") {
    localStorage.setItem(REFRESH_KEY, refresh);
  }
}

export function clearTokens(): void {
  Cookies.remove(ACCESS_COOKIE, COOKIE_OPTS);
  if (typeof window !== "undefined") {
    localStorage.removeItem(REFRESH_KEY);
  }
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
