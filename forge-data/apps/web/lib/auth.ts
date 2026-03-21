/**
 * Token helpers.
 *
 * Security model:
 *  - Access token: httpOnly cookie (set by API), never readable in JS.
 *  - Refresh token: httpOnly cookie (set by API), never readable in JS.
 *  - Browser auth relies on same-origin cookies with `withCredentials: true`.
 */

// ── Accessors ─────────────────────────────────────────────────────────────────

export function getAccessToken(): string | null {
  return null;
}

// Refresh token is httpOnly — the browser cannot read it.
// The /refresh endpoint reads it automatically from the cookie jar.
export function getRefreshToken(): null {
  return null;
}

// ── Mutators ──────────────────────────────────────────────────────────────────

export function setTokens(access: string, _refresh?: string): void {
  void access;
}

export function clearTokens(): void {
  // Cookies are httpOnly and cleared server-side on /logout.
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
