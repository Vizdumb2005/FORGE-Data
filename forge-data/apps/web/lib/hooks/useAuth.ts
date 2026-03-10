import { useCallback } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/stores/authStore";
import type { RegisterPayload } from "@/types";

export function useAuth() {
  const router = useRouter();
  const { user, loading, error, login, register, logout, fetchMe, clearError } =
    useAuthStore();

  const handleLogin = useCallback(
    async (email: string, password: string, next?: string) => {
      await login(email, password);
      router.push(next ?? "/dashboard");
    },
    [login, router]
  );

  const handleRegister = useCallback(
    async (payload: RegisterPayload) => {
      await register(payload);
      // Auto-login is handled by the store; redirect to dashboard
      router.push("/dashboard");
    },
    [register, router]
  );

  const handleLogout = useCallback(async () => {
    await logout();
    router.push("/login");
  }, [logout, router]);

  return {
    user,
    loading,
    error,
    isAuthenticated: !!user,
    login: handleLogin,
    register: handleRegister,
    logout: handleLogout,
    fetchMe,
    clearError,
  };
}
