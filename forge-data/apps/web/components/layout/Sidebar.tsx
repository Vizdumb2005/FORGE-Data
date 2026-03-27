"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FolderOpen,
  Database,
  FlaskConical,
  ScrollText,
  Zap,
  Settings,
  LogOut,
  ChevronRight,
  PanelLeftClose,
  PanelLeft,
} from "lucide-react";
import { cn, initials } from "@/lib/utils";
import { useAuth } from "@/lib/hooks/useAuth";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Logo } from "@/components/Logo";
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
  { href: "/automation", label: "Automation", icon: Zap },
  { href: "/audit", label: "Audit Log", icon: ScrollText },
];

const BOTTOM_ITEMS = [
  { href: "/settings", label: "Settings", icon: Settings },
];

export default function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const { workspaces } = useWorkspace();

  const sidebarWidth = collapsed ? "w-16" : "w-72";

  return (
    <TooltipProvider delayDuration={200}>
      <aside
        className={cn(
          "relative flex h-full shrink-0 flex-col border-r border-border bg-card transition-all duration-200",    
          sidebarWidth
        )}
      >
        {/* Logo */}
        <div className={cn("flex h-14 items-center border-b border-border px-4", collapsed ? "justify-center" : "justify-between")}>
          <Logo size={collapsed ? "sm" : "md"} className={cn(collapsed && "w-8 overflow-hidden")} />
          {!collapsed && (
            <button
              onClick={onToggle}
              className="ml-auto rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
            >
              <PanelLeftClose className="h-4 w-4" />
            </button>
          )}
          {collapsed && (
             <button
              onClick={onToggle}
              className="absolute -right-3 top-4 z-20 rounded-full border border-border bg-background p-1 text-muted-foreground shadow-md hover:text-foreground"
            >
              <ChevronRight className="h-3 w-3" />
            </button>
          )}
        </div>

        {/* Main nav */}
        <nav className="flex-1 overflow-y-auto px-3 py-4">
          <ul className="space-y-1">
            {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
              const active = pathname.startsWith(href);
              const item = (
                <Link
                  href={href}
                  className={cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    active
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                    collapsed && "justify-center px-2"
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {!collapsed && <span>{label}</span>}
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
            <div className="mt-8">
              <p className="mb-2 px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground/70">
                Workspaces
              </p>
              <ul className="space-y-1">
                {workspaces.slice(0, 5).map((ws) => {
                  const active = pathname === `/workspace/${ws.id}`;
                  return (
                    <li key={ws.id}>
                      <Link
                        href={`/workspace/${ws.id}`}
                        className={cn(
                          "flex items-center gap-2 rounded-md px-3 py-1.5 text-sm transition-colors",
                          active
                            ? "bg-primary/10 text-primary"
                            : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                        )}
                      >
                        <FolderOpen className="h-3.5 w-3.5 shrink-0 opacity-70" />
                        <span className="truncate">{ws.name}</span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          {collapsed && workspaces.length > 0 && (
            <div className="mt-4 flex justify-center">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Link
                    href="/dashboard"
                    className="flex items-center justify-center rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
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
        <div className="border-t border-border px-3 py-4">
          <ul className="space-y-1">
            {BOTTOM_ITEMS.map(({ href, label, icon: Icon }) => {
              const active = pathname.startsWith(href);
              const item = (
                <Link
                  href={href}
                  className={cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    active
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                    collapsed && "justify-center px-2"
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {!collapsed && <span>{label}</span>}
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
        </div>

        {/* User footer */}
        <div className="border-t border-border p-4">
          <div
            className={cn(
              "flex items-center gap-3",
              collapsed && "justify-center"
            )}
          >
            <Avatar className="h-8 w-8 shrink-0 border border-border">
              <AvatarFallback className="text-xs bg-muted text-muted-foreground">
                {initials(user?.full_name ?? user?.email ?? "?")}
              </AvatarFallback>
            </Avatar>
            {!collapsed && (
              <div className="flex flex-1 items-center justify-between overflow-hidden">
                <div className="truncate">
                  <p className="truncate text-sm font-medium text-foreground">
                    {user?.full_name || "User"}
                  </p>
                  <p className="truncate text-xs text-muted-foreground">
                    {user?.email}
                  </p>
                </div>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      onClick={logout}
                      className="ml-2 rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                    >
                      <LogOut className="h-4 w-4" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="right">Sign out</TooltipContent>
                </Tooltip>
              </div>
            )}
          </div>
        </div>
      </aside>
    </TooltipProvider>
  );
}
