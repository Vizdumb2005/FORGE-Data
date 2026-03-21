"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  CheckCircle2,
  ChevronRight,
  Eye,
  EyeOff,
  Loader2,
  Lock,
  Server,
  ShieldCheck,
  Sparkles,
  User,
} from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface StepProps {
  onNext: () => void;
  onBack?: () => void;
}

// ── Step indicator ────────────────────────────────────────────────────────────

const STEPS = [
  { label: "Welcome", icon: ShieldCheck },
  { label: "AI Provider", icon: Sparkles },
  { label: "Admin Account", icon: User },
  { label: "Launch", icon: Server },
];

function StepIndicator({ current }: { current: number }) {
  return (
    <div className="flex items-center justify-center gap-0 mb-10">
      {STEPS.map((step, i) => {
        const Icon = step.icon;
        const done = i < current;
        const active = i === current;
        return (
          <div key={step.label} className="flex items-center">
            <div className="flex flex-col items-center gap-1.5">
              <div
                className={[
                  "flex h-9 w-9 items-center justify-center rounded-full border-2 transition-all",
                  done
                    ? "border-green-500 bg-green-500 text-white"
                    : active
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-muted-foreground/30 bg-transparent text-muted-foreground/40",
                ].join(" ")}
              >
                {done ? (
                  <CheckCircle2 className="h-4 w-4" />
                ) : (
                  <Icon className="h-4 w-4" />
                )}
              </div>
              <span
                className={[
                  "text-[11px] font-medium",
                  active ? "text-foreground" : "text-muted-foreground/50",
                ].join(" ")}
              >
                {step.label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div
                className={[
                  "mx-2 mb-5 h-px w-12 transition-all",
                  done ? "bg-green-500" : "bg-muted-foreground/20",
                ].join(" ")}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Step 0: Welcome ───────────────────────────────────────────────────────────

function WelcomeStep({ onNext }: StepProps) {
  return (
    <div className="space-y-6 text-center">
      <div className="flex justify-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10">
          <ShieldCheck className="h-8 w-8 text-primary" />
        </div>
      </div>
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Welcome to FORGE Data</h1>
        <p className="mt-2 text-sm text-muted-foreground max-w-sm mx-auto">
          This wizard takes under 15 minutes. We&apos;ll generate all security secrets
          automatically and get you running safely.
        </p>
      </div>

      <div className="rounded-lg border bg-muted/30 p-4 text-left space-y-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          What happens during setup
        </p>
        {[
          ["🔐", "Strong secrets generated server-side", "JWT, encryption salt, MinIO & Jupyter tokens — never sent to your browser"],
          ["🤖", "AI provider configured", "Connect Ollama, OpenAI, Anthropic, or any local model"],
          ["👤", "Admin account created", "Your first user — full access to all features"],
          ["🚀", "Stack restart prompted", "Apply the new secrets and you're live"],
        ].map(([icon, title, desc]) => (
          <div key={title} className="flex gap-3">
            <span className="text-base mt-0.5">{icon}</span>
            <div>
              <p className="text-sm font-medium">{title}</p>
              <p className="text-xs text-muted-foreground">{desc}</p>
            </div>
          </div>
        ))}
      </div>

      <button
        onClick={onNext}
        className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
      >
        Get started <ChevronRight className="h-4 w-4" />
      </button>
    </div>
  );
}

// ── Step 1: AI Provider ───────────────────────────────────────────────────────

interface AiConfig {
  ollamaUrl: string;
  openaiKey: string;
  anthropicKey: string;
}

function AiProviderStep({
  onNext,
  onBack,
  value,
  onChange,
}: StepProps & { value: AiConfig; onChange: (v: AiConfig) => void }) {
  const [showOpenai, setShowOpenai] = useState(false);
  const [showAnthropic, setShowAnthropic] = useState(false);

  const set = (k: keyof AiConfig) => (e: React.ChangeEvent<HTMLInputElement>) =>
    onChange({ ...value, [k]: e.target.value });

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold tracking-tight">Configure AI Provider</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Fill in at least one provider. You can change these later in Settings.
        </p>
      </div>

      {/* Ollama */}
      <div className="rounded-lg border bg-card p-4 space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-base">🦙</span>
          <div>
            <p className="text-sm font-semibold">Ollama (local, recommended)</p>
            <p className="text-xs text-muted-foreground">Free, private, runs on your machine</p>
          </div>
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground">Base URL</label>
          <input
            type="url"
            value={value.ollamaUrl}
            onChange={set("ollamaUrl")}
            placeholder="http://host.docker.internal:11434"
            className="mt-1 flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          />
          <p className="mt-1 text-[11px] text-muted-foreground">
            Use <code className="bg-muted px-1 rounded">host.docker.internal</code> when Ollama runs on your host machine.
          </p>
        </div>
      </div>

      {/* OpenAI */}
      <div className="rounded-lg border bg-card p-4 space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-base">✦</span>
          <div>
            <p className="text-sm font-semibold">OpenAI</p>
            <p className="text-xs text-muted-foreground">GPT-4o, GPT-4o-mini</p>
          </div>
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground">API Key</label>
          <div className="relative mt-1">
            <input
              type={showOpenai ? "text" : "password"}
              value={value.openaiKey}
              onChange={set("openaiKey")}
              placeholder="sk-..."
              autoComplete="off"
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 pr-9 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
            <button
              type="button"
              onClick={() => setShowOpenai((v) => !v)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              {showOpenai ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </div>
      </div>

      {/* Anthropic */}
      <div className="rounded-lg border bg-card p-4 space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-base">◆</span>
          <div>
            <p className="text-sm font-semibold">Anthropic</p>
            <p className="text-xs text-muted-foreground">Claude 3.5 Sonnet, Haiku</p>
          </div>
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground">API Key</label>
          <div className="relative mt-1">
            <input
              type={showAnthropic ? "text" : "password"}
              value={value.anthropicKey}
              onChange={set("anthropicKey")}
              placeholder="sk-ant-..."
              autoComplete="off"
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 pr-9 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
            <button
              type="button"
              onClick={() => setShowAnthropic((v) => !v)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              {showAnthropic ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </div>
      </div>

      <p className="text-xs text-muted-foreground text-center">
        API keys are encrypted server-side before storage. You can skip and add them later.
      </p>

      <div className="flex gap-3">
        <button
          onClick={onBack}
          className="flex-1 rounded-md border border-input bg-transparent px-4 py-2.5 text-sm font-medium hover:bg-accent transition-colors"
        >
          Back
        </button>
        <button
          onClick={onNext}
          className="flex-1 inline-flex items-center justify-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          Continue <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

// ── Step 2: Admin Account ─────────────────────────────────────────────────────

interface AdminConfig {
  name: string;
  email: string;
  password: string;
  confirmPassword: string;
}

function AdminAccountStep({
  onNext,
  onBack,
  value,
  onChange,
  error,
}: StepProps & { value: AdminConfig; onChange: (v: AdminConfig) => void; error: string }) {
  const [showPw, setShowPw] = useState(false);
  const set = (k: keyof AdminConfig) => (e: React.ChangeEvent<HTMLInputElement>) =>
    onChange({ ...value, [k]: e.target.value });

  const passwordsMatch = value.password === value.confirmPassword;
  const canSubmit =
    value.name.trim() &&
    value.email.trim() &&
    value.password.length >= 12 &&
    passwordsMatch;

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold tracking-tight">Create Admin Account</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          This is the first and only account until you invite others.
        </p>
      </div>

      <div className="space-y-4">
        <div>
          <label className="text-sm font-medium">Full name</label>
          <input
            type="text"
            value={value.name}
            onChange={set("name")}
            placeholder="Your name"
            className="mt-1 flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          />
        </div>

        <div>
          <label className="text-sm font-medium">Email address</label>
          <input
            type="email"
            value={value.email}
            onChange={set("email")}
            placeholder="you@example.com"
            autoComplete="email"
            className="mt-1 flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          />
        </div>

        <div>
          <label className="text-sm font-medium">Password</label>
          <div className="relative mt-1">
            <input
              type={showPw ? "text" : "password"}
              value={value.password}
              onChange={set("password")}
              placeholder="12+ characters, mix of types"
              autoComplete="new-password"
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 pr-9 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
            <button
              type="button"
              onClick={() => setShowPw((v) => !v)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
          {value.password && value.password.length < 12 && (
            <p className="mt-1 text-xs text-destructive">Minimum 12 characters</p>
          )}
        </div>

        <div>
          <label className="text-sm font-medium">Confirm password</label>
          <input
            type="password"
            value={value.confirmPassword}
            onChange={set("confirmPassword")}
            placeholder="Repeat password"
            autoComplete="new-password"
            className="mt-1 flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          />
          {value.confirmPassword && !passwordsMatch && (
            <p className="mt-1 text-xs text-destructive">Passwords do not match</p>
          )}
        </div>
      </div>

      <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-300 flex gap-2">
        <Lock className="h-3.5 w-3.5 mt-0.5 shrink-0" />
        <span>
          All security secrets (JWT, encryption, MinIO, Jupyter) are generated server-side
          and written directly to <code className="bg-amber-900/40 px-1 rounded">.env</code>.
          They are never sent to your browser.
        </span>
      </div>

      {error && (
        <div className="rounded-md bg-destructive/15 border border-destructive/20 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="flex gap-3">
        <button
          onClick={onBack}
          className="flex-1 rounded-md border border-input bg-transparent px-4 py-2.5 text-sm font-medium hover:bg-accent transition-colors"
        >
          Back
        </button>
        <button
          onClick={onNext}
          disabled={!canSubmit}
          className="flex-1 inline-flex items-center justify-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:pointer-events-none transition-colors"
        >
          Create account <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

// ── Step 3: Launch ────────────────────────────────────────────────────────────

function LaunchStep({ success, onGoToLogin }: { success: boolean; onGoToLogin: () => void }) {
  return (
    <div className="space-y-6 text-center">
      <div className="flex justify-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-green-500/10">
          <CheckCircle2 className="h-8 w-8 text-green-500" />
        </div>
      </div>

      <div>
        <h2 className="text-xl font-bold tracking-tight">Setup complete!</h2>
        <p className="mt-2 text-sm text-muted-foreground max-w-sm mx-auto">
          Your secrets have been written to <code className="bg-muted px-1 rounded">.env</code> and
          your admin account is ready.
        </p>
      </div>

      <div className="rounded-lg border bg-amber-500/10 border-amber-500/30 p-4 text-left space-y-2">
        <p className="text-sm font-semibold text-amber-300">⚠ Restart required</p>
        <p className="text-xs text-amber-300/80">
          The new secrets take effect after a stack restart. Run:
        </p>
        <pre className="rounded bg-black/40 px-3 py-2 text-xs font-mono text-amber-200 overflow-x-auto">
          docker compose down && docker compose up -d
        </pre>
        <p className="text-xs text-amber-300/80">
          After restart, log in with the admin account you just created.
        </p>
      </div>

      <div className="rounded-lg border bg-muted/30 p-4 text-left space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          What was configured
        </p>
        <ul className="text-xs text-muted-foreground space-y-1 list-disc list-inside">
          <li>JWT_SECRET — 64-char hex, server-generated</li>
          <li>ENCRYPTION_SALT — 32-char hex, server-generated</li>
          <li>MINIO_SECRET_KEY — 64-char hex, server-generated</li>
          <li>JUPYTER_TOKEN — 64-char hex, server-generated</li>
          <li>POSTGRES_PASSWORD — 48-char hex, server-generated</li>
          <li>Admin account created and verified</li>
        </ul>
      </div>

      <button
        onClick={onGoToLogin}
        className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
      >
        Go to login
      </button>
    </div>
  );
}

// ── Main wizard ───────────────────────────────────────────────────────────────

export default function SetupPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [done, setDone] = useState(false);

  const [aiConfig, setAiConfig] = useState<AiConfig>({
    ollamaUrl: "http://host.docker.internal:11434",
    openaiKey: "",
    anthropicKey: "",
  });

  const [adminConfig, setAdminConfig] = useState<AdminConfig>({
    name: "",
    email: "",
    password: "",
    confirmPassword: "",
  });

  const handleSubmit = async () => {
    setSubmitting(true);
    setSubmitError("");
    try {
      const res = await fetch("/api/v1/setup/initialize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          admin_email: adminConfig.email,
          admin_password: adminConfig.password,
          admin_name: adminConfig.name,
          ollama_base_url: aiConfig.ollamaUrl,
          openai_api_key: aiConfig.openaiKey,
          anthropic_api_key: aiConfig.anthropicKey,
        }),
      });
      const data = (await res.json()) as { ok: boolean; message: string };
      if (!res.ok || !data.ok) {
        setSubmitError(data.message ?? "Setup failed. Please try again.");
        return;
      }
      setDone(true);
      setStep(3);
    } catch {
      setSubmitError("Network error — is the API running?");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-lg">
        {/* Logo / brand */}
        <div className="text-center mb-8">
          <p className="text-2xl font-bold tracking-tight">FORGE Data</p>
          <p className="text-xs text-muted-foreground mt-1">First-run setup</p>
        </div>

        <StepIndicator current={step} />

        <div className="rounded-xl border bg-card text-card-foreground shadow-sm p-6 md:p-8">
          {step === 0 && <WelcomeStep onNext={() => setStep(1)} />}

          {step === 1 && (
            <AiProviderStep
              value={aiConfig}
              onChange={setAiConfig}
              onNext={() => setStep(2)}
              onBack={() => setStep(0)}
            />
          )}

          {step === 2 && (
            <AdminAccountStep
              value={adminConfig}
              onChange={setAdminConfig}
              error={submitError}
              onBack={() => setStep(1)}
              onNext={async () => {
                await handleSubmit();
              }}
            />
          )}

          {step === 3 && (
            <LaunchStep
              success={done}
              onGoToLogin={() => router.push("/login")}
            />
          )}
        </div>

        {/* Submitting overlay */}
        {submitting && (
          <div className="fixed inset-0 bg-background/80 backdrop-blur-sm flex items-center justify-center z-50">
            <div className="flex flex-col items-center gap-3">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
              <p className="text-sm text-muted-foreground">
                Generating secrets & creating account…
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
