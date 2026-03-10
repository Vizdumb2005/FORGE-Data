import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import { persist } from "zustand/middleware";
import api from "@/lib/api";
import { setTokens, clearTokens } from "@/lib/auth";
import type { User, AuthResponse, RegisterPayload } from "@/types";

interface AuthState {
  user: User | null;
  loading: boolean;
  error: string | null;
}

interface AuthActions {
  login: (email: string, password: string) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => Promise<void>;
  fetchMe: () => Promise<void>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState & AuthActions>()(
  persist(
    immer((set) => ({
      user: null,
      loading: false,
      error: null,

      login: async (email, password) => {
        set((s) => {
          s.loading = true;
          s.error = null;
        });
        try {
          const resp = await api.post<AuthResponse>("/api/v1/auth/login", {
            email,
            password,
          });
          setTokens(resp.data.access_token, resp.data.refresh_token);
          set((s) => {
            s.user = resp.data.user;
            s.loading = false;
          });
        } catch (err: unknown) {
          const msg =
            (err as { response?: { data?: { detail?: string } } })?.response
              ?.data?.detail ?? "Invalid credentials";
          set((s) => {
            s.error = msg;
            s.loading = false;
          });
          throw err;
        }
      },

      register: async (payload) => {
        set((s) => {
          s.loading = true;
          s.error = null;
        });
        try {
          const resp = await api.post<AuthResponse>(
            "/api/v1/auth/register",
            payload
          );
          // Auto-login after successful registration
          setTokens(resp.data.access_token, resp.data.refresh_token);
          set((s) => {
            s.user = resp.data.user;
            s.loading = false;
          });
        } catch (err: unknown) {
          const detail = (
            err as { response?: { data?: { detail?: string | Array<{ msg: string }> } } }
          )?.response?.data?.detail;
          let msg = "Registration failed";
          if (typeof detail === "string") {
            msg = detail;
          } else if (Array.isArray(detail) && detail.length > 0) {
            msg = detail[0].msg;
          }
          set((s) => {
            s.error = msg;
            s.loading = false;
          });
          throw err;
        }
      },

      logout: async () => {
        try {
          await api.post("/api/v1/auth/logout");
        } catch {
          // ignore — clear local state regardless
        }
        clearTokens();
        set((s) => {
          s.user = null;
        });
      },

      fetchMe: async () => {
        set((s) => {
          s.loading = true;
        });
        try {
          const resp = await api.get<User>("/api/v1/auth/me");
          set((s) => {
            s.user = resp.data;
            s.loading = false;
          });
        } catch {
          set((s) => {
            s.user = null;
            s.loading = false;
          });
        }
      },

      clearError: () =>
        set((s) => {
          s.error = null;
        }),
    })),
    {
      name: "forge-auth",
      partialize: (state) => ({ user: state.user }),
    }
  )
);
