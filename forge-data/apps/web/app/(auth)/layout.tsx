"use client";

import { Toaster } from "@/components/ui/toaster";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen bg-[#0a0c10] text-forge-text">
      {/* Left — Brand panel */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-center border-r border-forge-border bg-forge-surface/40 px-16 xl:px-24">
        {/* Feature list header */}
        <div className="mb-10">
          <h2 className="font-sans text-3xl font-bold tracking-tight text-slate-100">
            Enterprise Data Platform
          </h2>
          <p className="mt-3 max-w-md text-lg text-slate-300">
            Runs on your own infrastructure. Complete control over your data and AI workflows.
          </p>
        </div>

        <ul className="space-y-4">
          {[
            {
              title: "Unified Workspace",
              desc: "Code, SQL, and AI cells on a single canvas",
            },
            {
              title: "BYO Keys",
              desc: "Connect OpenAI, Anthropic, and Ollama securely",
            },
            {
              title: "Enterprise Security",
              desc: "Encrypted storage, RBAC, and full audit logging",
            },
          ].map((item) => (
            <li key={item.title} className="flex items-start gap-3">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-forge-accent" />
              <div>
                <p className="text-sm font-medium text-slate-100">
                  {item.title}
                </p>
                <p className="text-sm text-slate-300">{item.desc}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>

      {/* Right — Form panel */}
      <div className="flex w-full lg:w-1/2 flex-col items-center justify-center bg-[#0a0c10] px-6 py-12">
        <div className="w-full max-w-md">{children}</div>
      </div>

      <Toaster />
    </div>
  );
}
