"use client";

import { useAuth } from "@/lib/hooks/useAuth";
import { Settings as SettingsIcon } from "lucide-react";
import Link from "next/link";

export default function SettingsPage() {
  const { user } = useAuth();

  return (
    <div className="container max-w-4xl py-10 space-y-8">
      <div className="flex items-center justify-between space-y-2">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Settings</h2>
          <p className="text-muted-foreground">
            Manage your account settings and preferences.
          </p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {/* Profile */}
        <div className="col-span-2 lg:col-span-4 rounded-xl border bg-card text-card-foreground shadow-sm">
          <div className="flex flex-col space-y-1.5 p-6">
            <h3 className="font-semibold leading-none tracking-tight">Profile</h3>
            <p className="text-sm text-muted-foreground">
              Your personal information.
            </p>
          </div>
          <div className="p-6 pt-0 space-y-4">
            <div className="grid gap-1">
              <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                Name
              </label>
              <div className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50">
                {user?.full_name ?? "—"}
              </div>
            </div>
            <div className="grid gap-1">
              <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                Email
              </label>
              <div className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50">
                {user?.email}
              </div>
            </div>
          </div>
        </div>

        {/* AI API Keys */}
        <div className="col-span-2 lg:col-span-4 rounded-xl border bg-card text-card-foreground shadow-sm">
          <div className="p-6 flex flex-row items-center justify-between space-y-0">
            <div className="space-y-1.5">
              <h3 className="font-semibold leading-none tracking-tight">AI Provider Configuration</h3>
              <p className="text-sm text-muted-foreground">
                Manage API keys and model parameters via JSON config.
              </p>
            </div>
            <Link
              href="/settings/api-keys"
              className="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-secondary text-secondary-foreground hover:bg-secondary/80 h-9 px-4 py-2"
            >
              Manage Configuration
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
