"use client";

import { useMemo } from "react";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { MlflowRun } from "@/types";

interface RunsTableProps {
  runs: MlflowRun[];
  selectedRunIds: Set<string>;
  onToggleRun: (runId: string) => void;
  onRowClick: (run: MlflowRun) => void;
}

function statusBadge(status: string) {
  if (status === "FINISHED") return "success" as const;
  if (status === "FAILED") return "destructive" as const;
  return "warning" as const;
}

export default function RunsTable({ runs, selectedRunIds, onToggleRun, onRowClick }: RunsTableProps) {
  const metricColumns = useMemo(() => {
    const keys = new Set<string>();
    runs.forEach((r) => Object.keys(r.metrics).forEach((m) => keys.add(m)));
    return Array.from(keys).slice(0, 5);
  }, [runs]);

  const columns = useMemo<ColumnDef<MlflowRun>[]>(
    () => [
      {
        id: "select",
        header: () => <span className="text-xs text-forge-muted">Select</span>,
        cell: ({ row }) => (
          <input
            type="checkbox"
            checked={selectedRunIds.has(row.original.run_id)}
            onChange={(e) => {
              e.stopPropagation();
              onToggleRun(row.original.run_id);
            }}
            onClick={(e) => e.stopPropagation()}
          />
        ),
      },
      {
        accessorKey: "run_name",
        header: "Run Name",
        cell: ({ row }) => row.original.run_name || row.original.run_id,
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => <Badge variant={statusBadge(row.original.status)}>{row.original.status}</Badge>,
      },
      {
        id: "created",
        header: "Created",
        cell: ({ row }) =>
          row.original.start_time ? new Date(row.original.start_time).toLocaleString() : "—",
      },
      {
        id: "duration",
        header: "Duration",
        cell: ({ row }) => (row.original.duration ? `${row.original.duration.toFixed(2)}s` : "—"),
      },
      ...metricColumns.map<ColumnDef<MlflowRun>>((metric) => ({
        id: `metric_${metric}`,
        header: metric,
        cell: ({ row }) => row.original.metrics[metric] ?? "—",
      })),
      {
        id: "actions",
        header: "Actions",
        cell: ({ row }) => (
          <Button
            variant="ghost"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              onRowClick(row.original);
            }}
          >
            Open
          </Button>
        ),
      },
    ],
    [metricColumns, onRowClick, onToggleRun, selectedRunIds],
  );

  const table = useReactTable({
    data: runs,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="overflow-auto">
      <table className="w-full text-sm">
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id} className="text-left text-forge-muted">
              {hg.headers.map((header) => (
                <th key={header.id} className="py-2">
                  {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.id}
              className="cursor-pointer border-t border-forge-border/50 hover:bg-forge-border/20"
              onClick={() => onRowClick(row.original)}
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="py-2">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {runs.length === 0 ? <div className="py-8 text-center text-sm text-forge-muted">No runs found.</div> : null}
    </div>
  );
}

