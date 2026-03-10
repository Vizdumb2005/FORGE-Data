"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Activity } from "lucide-react";
import type { AuditLog } from "@/types";

export default function AuditPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<AuditLog[]>("/api/v1/audit?limit=100")
      .then((r) => setLogs(r.data))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h1 className="mb-6 text-2xl font-semibold text-foreground flex items-center gap-2">
        <Activity className="h-6 w-6 text-forge-accent" />
        Audit Log
      </h1>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="h-10 rounded shimmer" />
          ))}
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-forge-border">
          <table className="w-full text-sm">
            <thead className="bg-forge-surface">
              <tr>
                {["Timestamp", "Action", "Resource", "IP"].map((h) => (
                  <th
                    key={h}
                    className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-forge-muted"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-forge-border">
              {logs.map((log) => (
                <tr key={log.id} className="hover:bg-forge-surface/50">
                  <td className="px-4 py-2.5 font-mono text-xs text-forge-muted">
                    {formatDate(log.created_at)}
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs text-forge-accent">
                    {log.action}
                  </td>
                  <td className="px-4 py-2.5 text-xs text-foreground">
                    {log.resource_type ?? "—"}
                    {log.resource_id ? (
                      <span className="text-forge-muted"> · {log.resource_id.slice(0, 8)}</span>
                    ) : null}
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs text-forge-muted">
                    {log.ip_address ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {logs.length === 0 && (
            <p className="p-8 text-center text-sm text-forge-muted">
              No audit events yet.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
