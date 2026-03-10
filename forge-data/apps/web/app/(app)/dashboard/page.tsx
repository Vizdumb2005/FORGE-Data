"use client";

import { useState, useEffect, useMemo } from "react";
import { Plus, LayoutDashboard, Database, FlaskConical, ScrollText } from "lucide-react";
import { useAuth } from "@/lib/hooks/useAuth";
import { useWorkspace } from "@/lib/hooks/useWorkspace";
import api from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import WorkspaceCard from "@/components/workspace/WorkspaceCard";
import NewWorkspaceDialog from "@/components/workspace/NewWorkspaceDialog";
import type { AuditLog } from "@/types";

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

interface DashboardStats {
  workspaces: number;
  datasets: number;
  experiments: number;
}

export default function DashboardPage() {
  const { user } = useAuth();
  const { workspaces, loading: wsLoading } = useWorkspace();
  const [showNewDialog, setShowNewDialog] = useState(false);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [activities, setActivities] = useState<AuditLog[]>([]);
  const [loadingStats, setLoadingStats] = useState(true);
  const [loadingActivity, setLoadingActivity] = useState(true);

  const greeting = useMemo(() => getGreeting(), []);
  const firstName = user?.full_name?.split(" ")[0] ?? user?.email ?? "";

  // Fetch stats
  useEffect(() => {
    async function loadStats() {
      try {
        const [datasetsResp, experimentsResp] = await Promise.allSettled([
          api.get("/api/v1/datasets"),
          api.get("/api/v1/experiments"),
        ]);
        setStats({
          workspaces: workspaces.length,
          datasets:
            datasetsResp.status === "fulfilled"
              ? (datasetsResp.value.data as unknown[]).length
              : 0,
          experiments:
            experimentsResp.status === "fulfilled"
              ? (experimentsResp.value.data as unknown[]).length
              : 0,
        });
      } catch {
        setStats({ workspaces: workspaces.length, datasets: 0, experiments: 0 });
      } finally {
        setLoadingStats(false);
      }
    }
    if (!wsLoading) loadStats();
  }, [workspaces.length, wsLoading]);

  // Fetch recent audit activity
  useEffect(() => {
    async function loadActivity() {
      try {
        const resp = await api.get<AuditLog[]>("/api/v1/health/audit", {
          params: { limit: 5 },
        });
        setActivities(resp.data);
      } catch {
        // Audit endpoint might not exist yet; degrade gracefully
        setActivities([]);
      } finally {
        setLoadingActivity(false);
      }
    }
    loadActivity();
  }, []);

  const statCards = [
    {
      label: "Workspaces",
      value: stats?.workspaces ?? workspaces.length,
      icon: LayoutDashboard,
    },
    { label: "Datasets", value: stats?.datasets ?? 0, icon: Database },
    { label: "Experiments", value: stats?.experiments ?? 0, icon: FlaskConical },
  ];

  return (
    <div className="p-6 max-w-6xl mx-auto">
      {/* Greeting */}
      <div className="mb-8">
        <h1 className="text-2xl font-sans font-semibold text-foreground">
          {greeting}, {firstName}
        </h1>
        <p className="mt-1 font-mono text-sm text-forge-muted">
          Here&apos;s what&apos;s happening in your workspaces.
        </p>
      </div>

      {/* Stat cards */}
      <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
        {statCards.map(({ label, value, icon: Icon }) => (
          <div
            key={label}
            className="rounded-lg border border-forge-border bg-forge-surface p-5"
          >
            <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-forge-muted mb-3">
              <Icon className="h-3.5 w-3.5" />
              {label}
            </div>
            {loadingStats ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <p className="text-3xl font-semibold text-foreground">{value}</p>
            )}
          </div>
        ))}
      </div>

      {/* Recent Workspaces */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-mono text-xs font-semibold uppercase tracking-wider text-forge-muted">
            Recent Workspaces
          </h2>
          <button
            onClick={() => setShowNewDialog(true)}
            className="inline-flex items-center gap-1.5 rounded-md bg-forge-accent px-3 py-1.5 font-mono text-xs font-semibold text-forge-bg hover:bg-forge-accent-dim transition-colors"
          >
            <Plus className="h-3.5 w-3.5" />
            New Workspace
          </button>
        </div>

        {wsLoading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-28 rounded-lg" />
            ))}
          </div>
        ) : workspaces.length === 0 ? (
          <div className="rounded-lg border border-dashed border-forge-border p-12 text-center">
            <p className="font-mono text-sm text-forge-muted">
              No workspaces yet.
            </p>
            <button
              onClick={() => setShowNewDialog(true)}
              className="mt-3 inline-flex items-center gap-1.5 font-mono text-sm text-forge-accent hover:underline"
            >
              <Plus className="h-3.5 w-3.5" />
              Create your first workspace
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {workspaces.slice(0, 6).map((ws) => (
              <WorkspaceCard key={ws.id} workspace={ws} />
            ))}
          </div>
        )}
      </div>

      {/* Recent Activity */}
      <div>
        <h2 className="mb-4 font-mono text-xs font-semibold uppercase tracking-wider text-forge-muted">
          Recent Activity
        </h2>
        {loadingActivity ? (
          <div className="space-y-2">
            {[1, 2, 3, 4, 5].map((i) => (
              <Skeleton key={i} className="h-10 rounded-md" />
            ))}
          </div>
        ) : activities.length === 0 ? (
          <div className="rounded-lg border border-dashed border-forge-border p-8 text-center">
            <ScrollText className="h-5 w-5 mx-auto text-forge-muted mb-2" />
            <p className="font-mono text-sm text-forge-muted">No recent activity.</p>
          </div>
        ) : (
          <div className="space-y-1">
            {activities.map((log) => (
              <div
                key={log.id}
                className="flex items-center justify-between rounded-md border border-forge-border bg-forge-surface px-4 py-2.5"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-forge-accent" />
                  <span className="truncate font-mono text-xs text-foreground">
                    {log.action}
                  </span>
                  {log.resource_type && (
                    <span className="shrink-0 font-mono text-[10px] text-forge-muted">
                      {log.resource_type}
                    </span>
                  )}
                </div>
                <span className="shrink-0 font-mono text-[10px] text-forge-muted ml-4">
                  {formatDate(log.created_at)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <NewWorkspaceDialog open={showNewDialog} onOpenChange={setShowNewDialog} />
    </div>
  );
}
