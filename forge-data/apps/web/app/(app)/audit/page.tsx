"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Activity, Download } from "lucide-react";
import { useWorkspaceStore } from "@/lib/stores/workspaceStore";
import { useAuthStore } from "@/lib/stores/authStore";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";

type AuditItem = {
  id: string;
  action: string;
  user_id: string | null;
  user_name: string | null;
  resource_type: string | null;
  resource_id: string | null;
  ip_address: string | null;
  created_at: string;
  metadata: Record<string, unknown>;
};

type AuditPageResponse = { items: AuditItem[]; total: number; page: number; limit: number };

const ACTION_OPTIONS = ["create", "update", "delete", "query", "export", "login"];
const RESOURCE_OPTIONS = ["workspace", "dataset", "cell", "query", "workspace_member"];

export default function AuditPage() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const workspaces = useWorkspaceStore((s) => s.workspaces);
  const fetchWorkspaces = useWorkspaceStore((s) => s.fetchWorkspaces);
  const [workspaceId, setWorkspaceId] = useState<string>("");
  const [members, setMembers] = useState<Array<{ user_id: string; role: string }>>([]);
  const [items, setItems] = useState<AuditItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [limit] = useState(50);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [userFilter, setUserFilter] = useState<string>("all");
  const [actionFilter, setActionFilter] = useState<string>("all");
  const [resourceFilter, setResourceFilter] = useState<string>("all");
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");

  useEffect(() => {
    void fetchWorkspaces();
  }, [fetchWorkspaces]);

  useEffect(() => {
    if (!workspaceId && workspaces.length > 0) {
      setWorkspaceId(workspaces[0].id);
    }
  }, [workspaceId, workspaces]);

  useEffect(() => {
    if (!workspaceId) return;
    api
      .get<Array<{ user_id: string; role: string }>>(`/api/v1/workspaces/${workspaceId}/members`)
      .then((r) => {
        setMembers(r.data);
        const me = r.data.find((m) => m.user_id === user?.id);
        if (!me || me.role !== "admin") router.replace("/dashboard");
      })
      .catch(() => router.replace("/dashboard"));
  }, [workspaceId, user?.id, router]);

  useEffect(() => {
    if (!workspaceId) return;
    setLoading(true);
    void api
      .get<AuditPageResponse>(`/api/v1/audit/workspaces/${workspaceId}/audit`, {
        params: {
          page,
          limit,
          user_id: userFilter === "all" ? undefined : userFilter,
          action: actionFilter === "all" ? undefined : actionFilter,
          resource_type: resourceFilter === "all" ? undefined : resourceFilter,
          start_date: startDate || undefined,
          end_date: endDate || undefined,
        },
      })
      .then((r) => {
        setItems(r.data.items);
        setTotal(r.data.total);
      })
      .finally(() => setLoading(false));
  }, [workspaceId, page, limit, userFilter, actionFilter, resourceFilter, startDate, endDate]);

  const stats = useMemo(() => {
    const uniqueUsers = new Set(items.map((i) => i.user_id).filter(Boolean)).size;
    const userCount = new Map<string, number>();
    const actionCount = new Map<string, number>();
    for (const item of items) {
      if (item.user_name) userCount.set(item.user_name, (userCount.get(item.user_name) ?? 0) + 1);
      actionCount.set(item.action, (actionCount.get(item.action) ?? 0) + 1);
    }
    const mostActiveUser = Array.from(userCount.entries()).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "—";
    const mostCommonAction = Array.from(actionCount.entries()).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "—";
    return { total, uniqueUsers, mostActiveUser, mostCommonAction };
  }, [items, total]);

  const columns = useMemo<ColumnDef<AuditItem>[]>(
    () => [
      { accessorKey: "created_at", header: "Timestamp", cell: ({ row }) => <span className="text-xs">{formatDate(row.original.created_at)}</span> },
      {
        accessorKey: "user_name",
        header: "User",
        cell: ({ row }) => <span className="text-xs">{row.original.user_name ?? "System"}</span>,
      },
      {
        accessorKey: "action",
        header: "Action",
        cell: ({ row }) => (
          <Badge variant={row.original.action.includes("delete") ? "destructive" : row.original.action.includes("create") ? "success" : "warning"}>
            {row.original.action}
          </Badge>
        ),
      },
      {
        id: "resource",
        header: "Resource",
        cell: ({ row }) => <span className="text-xs">{row.original.resource_type ?? "—"} {row.original.resource_id ? `· ${row.original.resource_id.slice(0, 8)}` : ""}</span>,
      },
      {
        id: "details",
        header: "Details",
        cell: ({ row }) => (
          <button
            className="text-xs text-forge-accent hover:underline"
            onClick={() => setExpanded((prev) => ({ ...prev, [row.original.id]: !prev[row.original.id] }))}
          >
            {expanded[row.original.id] ? "Hide" : "Expand"}
          </button>
        ),
      },
    ],
    [expanded],
  );

  const table = useReactTable({ data: items, columns, getCoreRowModel: getCoreRowModel() });

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-foreground flex items-center gap-2">
          <Activity className="h-6 w-6 text-forge-accent" />
          Audit Log
        </h1>
        <Button
          variant="outline"
          size="sm"
          onClick={async () => {
            const resp = await api.get(`/api/v1/audit/workspaces/${workspaceId}/audit/export`, {
              params: {
                user_id: userFilter === "all" ? undefined : userFilter,
                action: actionFilter === "all" ? undefined : actionFilter,
                resource_type: resourceFilter === "all" ? undefined : resourceFilter,
                start_date: startDate || undefined,
                end_date: endDate || undefined,
              },
              responseType: "blob",
            });
            const url = URL.createObjectURL(resp.data as Blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `audit_${workspaceId}.csv`;
            a.click();
            URL.revokeObjectURL(url);
          }}
        >
          <Download className="h-3.5 w-3.5" />
          Export CSV
        </Button>
      </div>

      <div className="grid grid-cols-4 gap-2">
        <StatCard label="Total events" value={String(stats.total)} />
        <StatCard label="Unique users active" value={String(stats.uniqueUsers)} />
        <StatCard label="Most active user" value={stats.mostActiveUser} />
        <StatCard label="Most common action" value={stats.mostCommonAction} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-5 gap-2">
        <Select value={workspaceId} onValueChange={setWorkspaceId}>
          <SelectTrigger><SelectValue placeholder="Workspace" /></SelectTrigger>
          <SelectContent>
            {workspaces.map((w) => <SelectItem key={w.id} value={w.id}>{w.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={userFilter} onValueChange={setUserFilter}>
          <SelectTrigger><SelectValue placeholder="User" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All users</SelectItem>
            {members.map((m) => <SelectItem key={m.user_id} value={m.user_id}>{m.user_id.slice(0, 8)}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={actionFilter} onValueChange={setActionFilter}>
          <SelectTrigger><SelectValue placeholder="Action type" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All actions</SelectItem>
            {ACTION_OPTIONS.map((a) => <SelectItem key={a} value={a}>{a}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={resourceFilter} onValueChange={setResourceFilter}>
          <SelectTrigger><SelectValue placeholder="Resource type" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All resources</SelectItem>
            {RESOURCE_OPTIONS.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
          </SelectContent>
        </Select>
        <div className="flex gap-2">
          <Input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
        </div>
      </div>

      <div className="overflow-hidden rounded-lg border border-forge-border">
        <table className="w-full text-sm">
          <thead className="bg-forge-surface">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((header) => (
                  <th key={header.id} className="px-3 py-2 text-left text-xs text-forge-muted">
                    {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {loading ? (
              <tr><td className="px-3 py-6 text-sm text-forge-muted" colSpan={5}>Loading...</td></tr>
            ) : items.length === 0 ? (
              <tr><td className="px-3 py-6 text-sm text-forge-muted" colSpan={5}>No audit events yet.</td></tr>
            ) : (
              table.getRowModel().rows.map((row) => (
                <>
                  <tr key={row.id} className="border-t border-forge-border/60">
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="px-3 py-2">{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                    ))}
                  </tr>
                  {expanded[row.original.id] ? (
                    <tr className="border-t border-forge-border/30 bg-forge-bg/40">
                      <td className="px-3 py-2" colSpan={5}>
                        <pre className="overflow-auto text-[11px] text-forge-muted">{JSON.stringify(row.original.metadata ?? {}, null, 2)}</pre>
                      </td>
                    </tr>
                  ) : null}
                </>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between">
        <span className="text-xs text-forge-muted">
          Page {page} · {total} total
        </span>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
          <Button variant="outline" size="sm" disabled={page * limit >= total} onClick={() => setPage((p) => p + 1)}>Next</Button>
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-forge-border bg-forge-bg p-3">
      <p className="text-[10px] uppercase tracking-wide text-forge-muted">{label}</p>
      <p className="mt-1 text-sm font-semibold text-foreground">{value}</p>
    </div>
  );
}
