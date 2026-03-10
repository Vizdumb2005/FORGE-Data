/**
 * Axios instance with automatic JWT injection, 401 → token-refresh, and
 * redirect-to-login fallback.
 */
import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";
import { getAccessToken, getRefreshToken, setTokens, clearTokens } from "./auth";

const BASE_URL =
  typeof window === "undefined"
    ? process.env.NEXT_PUBLIC_API_URL ?? "http://api:8000"
    : ""; // in-browser: use Next.js rewrites (/api/v1/...)

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
  withCredentials: false,
});

// ── Request interceptor — attach access token ─────────────────────────────────

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getAccessToken();
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Response interceptor — handle 401 with token refresh ──────────────────────

let _refreshing: Promise<string | null> | null = null;

api.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & {
      _retried?: boolean;
    };

    if (error.response?.status !== 401 || original._retried) {
      return Promise.reject(error);
    }

    original._retried = true;

    const refreshToken = getRefreshToken();
    if (!refreshToken) {
      _handleLogout();
      return Promise.reject(error);
    }

    // Deduplicate concurrent refresh calls
    if (!_refreshing) {
      _refreshing = _doRefresh(refreshToken).finally(() => {
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

async function _doRefresh(refreshToken: string): Promise<string | null> {
  try {
    const resp = await axios.post<{
      access_token: string;
      refresh_token: string;
    }>(`${BASE_URL}/api/v1/auth/refresh`, { refresh_token: refreshToken });
    setTokens(resp.data.access_token, resp.data.refresh_token);
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
