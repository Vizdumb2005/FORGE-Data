"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2 } from "lucide-react";
import { zxcvbn, zxcvbnOptions } from "@zxcvbn-ts/core";
import * as zxcvbnCommonPackage from "@zxcvbn-ts/language-common";
import * as zxcvbnEnPackage from "@zxcvbn-ts/language-en";
import { useAuth } from "@/lib/hooks/useAuth";
import { useToast } from "@/components/ui/use-toast";

// Initialize zxcvbn
zxcvbnOptions.setOptions({
  translations: zxcvbnEnPackage.translations,
  graphs: zxcvbnCommonPackage.adjacencyGraphs,
  dictionary: {
    ...zxcvbnCommonPackage.dictionary,
    ...zxcvbnEnPackage.dictionary,
  },
});

const schema = z
  .object({
    full_name: z.string().min(1, "Full name is required").max(255),
    email: z.string().email("Enter a valid email address"),
    password: z.string().min(8, "Password must be at least 8 characters"),
    confirm: z.string(),
  })
  .refine((d) => d.password === d.confirm, {
    message: "Passwords do not match",
    path: ["confirm"],
  });

type FormValues = z.infer<typeof schema>;

const STRENGTH_LABELS = ["Very weak", "Weak", "Fair", "Strong", "Very strong"];
const STRENGTH_COLORS = [
  "bg-red-500",
  "bg-orange-500",
  "bg-yellow-500",
  "bg-blue-500",
  "bg-green-500",
];

export default function RegisterPage() {
  const { register: registerUser, loading, clearError } = useAuth();
  const { toast } = useToast();
  const [submitting, setSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const passwordValue = watch("password", "");

  const strength = useMemo(() => {
    if (!passwordValue || passwordValue.length < 1) return null;
    return zxcvbn(passwordValue);
  }, [passwordValue]);

  const onSubmit = async (data: FormValues) => {
    // Check password strength client-side
    if (strength && strength.score < 2) {
      toast({
        title: "Password too weak",
        description:
          strength.feedback.warning ||
          "Choose a stronger password with more variety.",
        variant: "destructive",
      });
      return;
    }

    setSubmitting(true);
    clearError();
    try {
      await registerUser({
        email: data.email,
        password: data.password,
        full_name: data.full_name,
      });
    } catch (err: unknown) {
      const detail = (
        err as {
          response?: {
            data?: { detail?: string | Array<{ msg: string }> };
          };
        }
      )?.response?.data?.detail;
      let msg = "Registration failed";
      if (typeof detail === "string") {
        msg = detail;
      } else if (Array.isArray(detail) && detail.length > 0) {
        msg = detail[0].msg;
      }
      toast({ title: "Registration failed", description: msg, variant: "destructive" });
    } finally {
      setSubmitting(false);
    }
  };

  const isLoading = submitting || loading;

  return (
    <div className="rounded-xl border border-forge-border bg-forge-surface p-8 shadow-xl">
      <h1 className="mb-1 font-sans text-xl font-semibold text-foreground">
        Create account
      </h1>
      <p className="mb-6 font-mono text-sm text-forge-muted">
        Already have an account?{" "}
        <Link href="/login" className="text-forge-accent hover:underline">
          Sign in
        </Link>
      </p>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        {/* Full name */}
        <div>
          <label className="mb-1.5 block font-mono text-xs font-medium uppercase tracking-wider text-forge-muted">
            Full name
          </label>
          <input
            type="text"
            autoComplete="name"
            disabled={isLoading}
            {...register("full_name")}
            className="w-full rounded-md border border-forge-border bg-forge-bg px-3 py-2.5 font-mono text-sm text-foreground placeholder:text-forge-muted/50 focus:border-forge-accent focus:outline-none focus:ring-1 focus:ring-forge-accent/30 disabled:opacity-50"
            placeholder="Ada Lovelace"
          />
          {errors.full_name && (
            <p className="mt-1 font-mono text-xs text-red-400">
              {errors.full_name.message}
            </p>
          )}
        </div>

        {/* Email */}
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

        {/* Password */}
        <div>
          <label className="mb-1.5 block font-mono text-xs font-medium uppercase tracking-wider text-forge-muted">
            Password
          </label>
          <input
            type="password"
            autoComplete="new-password"
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

          {/* Password strength meter */}
          {strength !== null && (
            <div className="mt-2">
              <div className="flex gap-1">
                {[0, 1, 2, 3, 4].map((i) => (
                  <div
                    key={i}
                    className={`h-1 flex-1 rounded-full transition-colors ${
                      i <= strength.score
                        ? STRENGTH_COLORS[strength.score]
                        : "bg-forge-border"
                    }`}
                  />
                ))}
              </div>
              <p className="mt-1 font-mono text-xs text-forge-muted">
                {STRENGTH_LABELS[strength.score]}
                {strength.feedback.warning &&
                  ` — ${strength.feedback.warning}`}
              </p>
            </div>
          )}
        </div>

        {/* Confirm password */}
        <div>
          <label className="mb-1.5 block font-mono text-xs font-medium uppercase tracking-wider text-forge-muted">
            Confirm password
          </label>
          <input
            type="password"
            autoComplete="new-password"
            disabled={isLoading}
            {...register("confirm")}
            className="w-full rounded-md border border-forge-border bg-forge-bg px-3 py-2.5 font-mono text-sm text-foreground placeholder:text-forge-muted/50 focus:border-forge-accent focus:outline-none focus:ring-1 focus:ring-forge-accent/30 disabled:opacity-50"
            placeholder="••••••••"
          />
          {errors.confirm && (
            <p className="mt-1 font-mono text-xs text-red-400">
              {errors.confirm.message}
            </p>
          )}
        </div>

        <button
          type="submit"
          disabled={isLoading}
          className="flex w-full items-center justify-center gap-2 rounded-md bg-forge-accent px-4 py-2.5 font-mono text-sm font-semibold text-forge-bg transition-colors hover:bg-forge-accent-dim disabled:opacity-50"
        >
          {isLoading && <Loader2 className="h-4 w-4 animate-spin" />}
          {isLoading ? "Creating account..." : "Create account"}
        </button>
      </form>
    </div>
  );
}
