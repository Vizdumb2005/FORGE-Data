"use client";

import { usePathname } from "next/navigation";
import { Bell } from "lucide-react";
import { useAuth } from "@/lib/hooks/useAuth";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { initials } from "@/lib/utils";
import Link from "next/link";

const ROUTE_LABELS: Record<string, string> = {
  "/dashboard": "Dashboard",
  "/datasets": "Datasets",
  "/experiments": "Experiments",
  "/audit": "Audit Log",
  "/settings": "Settings",
  "/settings/api-keys": "API Keys",
};

export default function Header() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  const label =
    ROUTE_LABELS[pathname] ??
    (pathname.startsWith("/workspace") ? "Workspace" : "FORGE Data");

  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-forge-border bg-forge-surface px-4">
      <h1 className="font-mono text-xs font-semibold uppercase tracking-wider text-forge-muted">
        {label}
      </h1>

      <div className="flex items-center gap-3">
        <button className="rounded-md p-1.5 text-forge-muted hover:bg-forge-border hover:text-foreground transition-colors">
          <Bell className="h-4 w-4" />
        </button>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="flex items-center gap-2 rounded-md px-2 py-1 hover:bg-forge-border/50 transition-colors">
              <Avatar className="h-6 w-6">
                <AvatarFallback className="text-[9px] bg-forge-accent/20 text-forge-accent">
                  {initials(user?.full_name ?? user?.email ?? "?")}
                </AvatarFallback>
              </Avatar>
              <span className="hidden sm:block text-xs text-forge-muted">
                {user?.full_name ?? user?.email ?? ""}
              </span>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <div className="px-2 py-1.5">
              <p className="text-sm font-medium">{user?.full_name}</p>
              <p className="text-xs text-forge-muted">{user?.email}</p>
            </div>
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild>
              <Link href="/settings">Settings</Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link href="/settings/api-keys">API Keys</Link>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={logout} className="text-red-400">
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
