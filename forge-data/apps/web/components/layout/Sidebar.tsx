"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FolderOpen,
  Database,
  FlaskConical,
  ScrollText,
  Settings,
  LogOut,
  ChevronRight,
  PanelLeftClose,
  PanelLeft,
} from "lucide-react";
import { cn, initials } from "@/lib/utils";
import { useAuth } from "@/lib/hooks/useAuth";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
  TooltipProvider,
} from "@/components/ui/tooltip";
import { useWorkspace } from "@/lib/hooks/useWorkspace";

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/datasets", label: "Datasets", icon: Database },
  { href: "/experiments", label: "Experiments", icon: FlaskConical },
  { href: "/audit", label: "Audit Log", icon: ScrollText },
];

const BOTTOM_ITEMS = [
  { href: "/settings", label: "Settings", icon: Settings },
];

export default function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const { workspaces } = useWorkspace();

  const sidebarWidth = collapsed ? "w-16" : "w-60";

  return (
    <TooltipProvider delayDuration={200}>
      <aside
        className={cn(
          "flex h-full shrink-0 flex-col border-r border-forge-border bg-forge-surface transition-all duration-200",
          sidebarWidth
        )}
      >
        {/* Logo */}
        <div className="flex h-12 items-center justify-between border-b border-forge-border px-3">
          {!collapsed && (
            <Link href="/dashboard" className="flex items-center gap-1.5">
              <span className="font-mono text-sm font-semibold text-forge-accent">
                FORGE
              </span>
              <span className="font-sans text-xs font-light text-forge-muted">
                Data
              </span>
            </Link>
          )}
          <button
            onClick={onToggle}
            className={cn(
              "rounded-md p-1.5 text-forge-muted hover:bg-forge-border hover:text-foreground transition-colors",
              collapsed && "mx-auto"
            )}
          >
            {collapsed ? (
              <PanelLeft className="h-4 w-4" />
            ) : (
              <PanelLeftClose className="h-4 w-4" />
            )}
          </button>
        </div>

        {/* Main nav */}
        <nav className="flex-1 overflow-y-auto px-2 py-3">
          <ul className="space-y-0.5">
            {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
              const active = pathname.startsWith(href);
              const item = (
                <Link
                  href={href}
                  className={cn(
                    "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                    active
                      ? "bg-forge-accent/10 text-forge-accent"
                      : "text-forge-muted hover:bg-forge-border/50 hover:text-foreground",
                    collapsed && "justify-center px-0"
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {!collapsed && label}
                </Link>
              );

              return (
                <li key={href}>
                  {collapsed ? (
                    <Tooltip>
                      <TooltipTrigger asChild>{item}</TooltipTrigger>
                      <TooltipContent side="right">{label}</TooltipContent>
                    </Tooltip>
                  ) : (
                    item
                  )}
                </li>
              );
            })}
          </ul>

          {/* Workspaces section */}
          {!collapsed && workspaces.length > 0 && (
            <div className="mt-5">
              <p className="mb-1.5 px-3 font-mono text-[10px] font-semibold uppercase tracking-widest text-forge-muted">
                Workspaces
              </p>
              <ul className="space-y-0.5">
                {workspaces.slice(0, 5).map((ws) => {
                  const active = pathname === `/workspace/${ws.id}`;
                  return (
                    <li key={ws.id}>
                      <Link
                        href={`/workspace/${ws.id}`}
                        className={cn(
                          "flex items-center gap-2 rounded-md px-3 py-1.5 text-xs transition-colors",
                          active
                            ? "bg-forge-accent/10 text-forge-accent"
                            : "text-forge-muted hover:bg-forge-border/50 hover:text-foreground"
                        )}
                      >
                        <FolderOpen className="h-3 w-3 shrink-0" />
                        <span className="truncate">{ws.name}</span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          {collapsed && workspaces.length > 0 && (
            <div className="mt-3">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Link
                    href="/dashboard"
                    className="flex items-center justify-center rounded-md px-3 py-2 text-forge-muted hover:bg-forge-border/50 hover:text-foreground"
                  >
                    <FolderOpen className="h-4 w-4" />
                  </Link>
                </TooltipTrigger>
                <TooltipContent side="right">Workspaces</TooltipContent>
              </Tooltip>
            </div>
          )}
        </nav>

        {/* Bottom nav (Settings) */}
        <div className="border-t border-forge-border px-2 py-2">
          {BOTTOM_ITEMS.map(({ href, label, icon: Icon }) => {
            const active = pathname.startsWith(href);
            const item = (
              <Link
                href={href}
                className={cn(
                  "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                  active
                    ? "bg-forge-accent/10 text-forge-accent"
                    : "text-forge-muted hover:bg-forge-border/50 hover:text-foreground",
                  collapsed && "justify-center px-0"
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {!collapsed && label}
              </Link>
            );

            return collapsed ? (
              <Tooltip key={href}>
                <TooltipTrigger asChild>{item}</TooltipTrigger>
                <TooltipContent side="right">{label}</TooltipContent>
              </Tooltip>
            ) : (
              <div key={href}>{item}</div>
            );
          })}
        </div>

        {/* User footer */}
        <div className="border-t border-forge-border p-3">
          <div
            className={cn(
              "flex items-center",
              collapsed ? "justify-center" : "gap-2"
            )}
          >
            <Avatar className="h-7 w-7 shrink-0">
              <AvatarFallback className="text-[10px] bg-forge-accent/20 text-forge-accent">
                {initials(user?.full_name ?? user?.email ?? "?")}
              </AvatarFallback>
            </Avatar>
            {!collapsed && (
              <>
                <div className="flex-1 min-w-0">
                  <p className="truncate text-xs font-medium text-foreground">
                    {user?.full_name ?? user?.email}
                  </p>
                  <p className="truncate text-[10px] text-forge-muted">
                    {user?.email}
                  </p>
                </div>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      onClick={logout}
                      className="text-forge-muted hover:text-foreground transition-colors"
                    >
                      <LogOut className="h-3.5 w-3.5" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="right">Sign out</TooltipContent>
                </Tooltip>
              </>
            )}
          </div>
        </div>
      </aside>
    </TooltipProvider>
  );
}
