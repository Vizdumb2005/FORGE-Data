"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/lib/hooks/useAuth";
import { useToast } from "@/components/ui/use-toast";
import { Logo } from "@/components/Logo";

const schema = z.object({
  email: z.string().email("Enter a valid email address"),
  password: z.string().min(8, "Password must be at least 8 characters"),
});

type FormValues = z.infer<typeof schema>;

function LoginForm() {
  const [next, setNext] = useState<string | undefined>(undefined);
  useEffect(() => {
    const value = new URLSearchParams(window.location.search).get("next");
    setNext(value && value.startsWith("/") ? value : undefined);
  }, []);

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
    <div className="w-full max-w-[400px] animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="mb-8 flex flex-col items-center text-center space-y-2">
        <Logo size="lg" className="mb-4" />
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Welcome back
        </h1>
        <p className="text-sm text-muted-foreground">
          Enter your credentials to access your workspace
        </p>
      </div>

      <div className="grid gap-6 rounded-lg border border-border bg-card p-6 shadow-sm">
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 text-muted-foreground">
              Email
            </label>
            <input
              type="email"
              autoComplete="email"
              disabled={isLoading}
              {...register("email")}
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 transition-all duration-200"
              placeholder="name@company.com"
            />
            {errors.email && (
              <p className="text-xs text-destructive font-medium">
                {errors.email.message}
              </p>
            )}
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 text-muted-foreground">
                Password
              </label>
              <Link
                href="/forgot-password"
                className="text-xs text-primary hover:text-primary/80 transition-colors"
              >
                Forgot password?
              </Link>
            </div>
            <input
              type="password"
              autoComplete="current-password"
              disabled={isLoading}
              {...register("password")}
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 transition-all duration-200"
              placeholder="••••••••"
            />
            {errors.password && (
              <p className="text-xs text-destructive font-medium">
                {errors.password.message}
              </p>
            )}
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="inline-flex w-full items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2 mt-2 shadow-sm hover:shadow-md active:scale-[0.98]"
          >
            {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {isLoading ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </div>
      
      <p className="px-8 text-center text-sm text-muted-foreground mt-6">
        Don&apos;t have an account?{" "}
        <Link 
          href="/register" 
          className="underline underline-offset-4 hover:text-primary transition-colors"
        >
          Create an account
        </Link>
      </p>
    </div>
  );
}

export default function LoginPage() {
  return (
    <div className="container relative min-h-screen flex-col items-center justify-center grid lg:max-w-none lg:grid-cols-1 lg:px-0">
      <div className="lg:p-8 flex items-center justify-center h-full w-full">
        <LoginForm />
      </div>
    </div>
  );
}
