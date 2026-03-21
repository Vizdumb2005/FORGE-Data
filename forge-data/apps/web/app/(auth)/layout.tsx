"use client";

import { Toaster } from "@/components/ui/toaster";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen bg-forge-bg">
      {/* Left — Brand panel */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-center px-16 xl:px-24">
        {/* Feature list header */}
        <div className="mb-10">
          <h2 className="font-sans text-3xl font-bold tracking-tight text-foreground">
            Enterprise Data Platform
          </h2>
          <p className="mt-3 text-lg text-forge-muted max-w-md">
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
                <p className="text-sm font-medium text-foreground">
                  {item.title}
                </p>
                <p className="text-sm text-forge-muted">{item.desc}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>

      {/* Right — Form panel */}
      <div className="flex w-full lg:w-1/2 flex-col items-center justify-center px-6 py-12">
        <div className="w-full max-w-md">{children}</div>
      </div>

      <Toaster />
    </div>
  );
}
