"use client";

import { useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/lib/hooks/useAuth";
import { useToast } from "@/components/ui/use-toast";

const schema = z.object({
  email: z.string().email("Enter a valid email address"),
  password: z.string().min(8, "Password must be at least 8 characters"),
});

type FormValues = z.infer<typeof schema>;

export default function LoginPage() {
  const searchParams = useSearchParams();
  const next = searchParams.get("next") ?? undefined;

  const { login, loading, clearError } = useAuth();
  const { toast } = useToast();
  const [submitting, setSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (data: FormValues) => {
    setSubmitting(true);
    clearError();
    try {
      await login(data.email, data.password, next);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Invalid email or password";
      toast({ title: "Login failed", description: msg, variant: "destructive" });
    } finally {
      setSubmitting(false);
    }
  };

  const isLoading = submitting || loading;

  return (
    <div className="rounded-xl border border-forge-border bg-forge-surface p-8 shadow-xl">
      <h1 className="mb-1 font-sans text-xl font-semibold text-foreground">
        Sign in
      </h1>
      <p className="mb-6 font-mono text-sm text-forge-muted">
        Don&apos;t have an account?{" "}
        <Link href="/register" className="text-forge-accent hover:underline">
          Register
        </Link>
      </p>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <div>
          <label className="mb-1.5 block font-mono text-xs font-medium uppercase tracking-wider text-forge-muted">
            Email
          </label>
          <input
            type="email"
            autoComplete="email"
            disabled={isLoading}
            {...register("email")}
            className="w-full rounded-md border border-forge-border bg-forge-bg px-3 py-2.5 font-mono text-sm text-foreground placeholder:text-forge-muted/50 focus:border-forge-accent focus:outline-none focus:ring-1 focus:ring-forge-accent/30 disabled:opacity-50"
            placeholder="you@example.com"
          />
          {errors.email && (
            <p className="mt-1 font-mono text-xs text-red-400">
              {errors.email.message}
            </p>
          )}
        </div>

        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <label className="block font-mono text-xs font-medium uppercase tracking-wider text-forge-muted">
              Password
            </label>
            <Link
              href="/forgot-password"
              className="font-mono text-xs text-forge-muted hover:text-forge-accent"
            >
              Forgot password?
            </Link>
          </div>
          <input
            type="password"
            autoComplete="current-password"
            disabled={isLoading}
            {...register("password")}
            className="w-full rounded-md border border-forge-border bg-forge-bg px-3 py-2.5 font-mono text-sm text-foreground placeholder:text-forge-muted/50 focus:border-forge-accent focus:outline-none focus:ring-1 focus:ring-forge-accent/30 disabled:opacity-50"
            placeholder="••••••••"
          />
          {errors.password && (
            <p className="mt-1 font-mono text-xs text-red-400">
              {errors.password.message}
            </p>
          )}
        </div>

        <button
          type="submit"
          disabled={isLoading}
          className="flex w-full items-center justify-center gap-2 rounded-md bg-forge-accent px-4 py-2.5 font-mono text-sm font-semibold text-forge-bg transition-colors hover:bg-forge-accent-dim disabled:opacity-50"
        >
          {isLoading && <Loader2 className="h-4 w-4 animate-spin" />}
          {isLoading ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </div>
  );
}
