/**
 * Axios instance with automatic JWT injection, 401 → token-refresh, and
 * redirect-to-login fallback.
 */
import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";
import { setTokens, clearTokens } from "./auth";

// All API calls run in the browser (inside useEffect / event handlers).
// Empty baseURL = relative paths → routed through Next.js rewrites to the backend.
const BASE_URL = "";

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
  withCredentials: true,
});

// ── Request interceptor — attach access token ─────────────────────────────────

api.interceptors.request.use((config: InternalAxiosRequestConfig) => config);

// ── Response interceptor — handle 401 with token refresh ──────────────────────

let _refreshing: Promise<string | null> | null = null;

api.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & {
      _retried?: boolean;
    };

    // Network error (no response at all) — log and reject without retry
    if (!error.response) {
      const url = original?.url ?? "unknown";
      console.warn(`[api] Network error reaching ${url}:`, error.message);
      return Promise.reject(error);
    }

    if (error.response.status !== 401 || original._retried) {
      return Promise.reject(error);
    }

    original._retried = true;

    if (!_refreshing) {
      _refreshing = _doRefresh().finally(() => {
        _refreshing = null;
      });
    }

    const newAccessToken = await _refreshing;
    if (!newAccessToken) {
      _handleLogout();
      return Promise.reject(error);
    }

    original.headers = original.headers ?? {};
    original.headers.Authorization = `Bearer ${newAccessToken}`;
    return api(original);
  }
);

async function _doRefresh(): Promise<string | null> {
  try {
    // No body — the httpOnly refresh cookie is sent automatically by the browser.
    const resp = await axios.post<{ access_token: string }>(
      `${BASE_URL}/api/v1/auth/refresh`,
      {},
      { withCredentials: true },
    );
    setTokens(resp.data.access_token);
    return resp.data.access_token;
  } catch {
    clearTokens();
    return null;
  }
}

function _handleLogout() {
  clearTokens();
  if (typeof window !== "undefined") {
    window.location.href = "/login";
  }
}

// ── Typed helpers ─────────────────────────────────────────────────────────────

export default api;
