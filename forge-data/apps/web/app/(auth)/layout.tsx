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
        {/* Animated FORGE logo */}
        <div className="mb-10">
          <div className="forge-logo-mark mb-6">
            <svg
              width="48"
              height="48"
              viewBox="0 0 48 48"
              fill="none"
              className="forge-logo-spin"
            >
              <rect
                x="4"
                y="4"
                width="40"
                height="40"
                rx="8"
                stroke="#00e5ff"
                strokeWidth="2"
                className="forge-logo-rect"
              />
              <path
                d="M16 16h16M16 24h12M16 32h8"
                stroke="#00e5ff"
                strokeWidth="2"
                strokeLinecap="round"
                className="forge-logo-lines"
              />
            </svg>
          </div>
          <h1 className="font-sans text-4xl font-bold tracking-tight text-foreground">
            FORGE{" "}
            <span className="font-light text-forge-muted">Data</span>
          </h1>
          <p className="mt-3 text-lg text-forge-muted max-w-md">
            Open-source, self-hosted data intelligence platform.
          </p>
        </div>

        <ul className="space-y-4">
          {[
            {
              title: "Interactive Workspaces",
              desc: "Code, SQL, and AI cells on a single canvas",
            },
            {
              title: "Bring Your Own Keys",
              desc: "OpenAI, Anthropic, Ollama — your keys, your control",
            },
            {
              title: "Enterprise-grade Security",
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
        {/* Mobile logo */}
        <div className="mb-8 lg:hidden text-center">
          <span className="font-mono text-2xl font-semibold text-forge-accent">
            FORGE
          </span>
          <span className="ml-1 font-sans text-2xl font-light text-forge-muted">
            Data
          </span>
        </div>

        <div className="w-full max-w-md">{children}</div>
      </div>

      <Toaster />

      {/* CSS animation for the logo */}
      <style jsx>{`
        .forge-logo-rect {
          stroke-dasharray: 160;
          stroke-dashoffset: 160;
          animation: forge-draw 2s ease forwards,
            forge-pulse 3s ease-in-out 2s infinite;
        }
        .forge-logo-lines {
          stroke-dasharray: 40;
          stroke-dashoffset: 40;
          animation: forge-draw-lines 1.2s ease 1s forwards;
        }
        @keyframes forge-draw {
          to {
            stroke-dashoffset: 0;
          }
        }
        @keyframes forge-draw-lines {
          to {
            stroke-dashoffset: 0;
          }
        }
        @keyframes forge-pulse {
          0%,
          100% {
            opacity: 1;
          }
          50% {
            opacity: 0.6;
          }
        }
      `}</style>
    </div>
  );
}
