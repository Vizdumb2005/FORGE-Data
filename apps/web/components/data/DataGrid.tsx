"use client";

import { useMemo, useState } from "react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { ArrowUpDown, ArrowUp, ArrowDown, Download } from "lucide-react";
import { cn } from "@/lib/utils";

interface DataGridProps {
  columns: string[];
  rows: unknown[][];
  maxHeight?: string;
  exportFilename?: string;
}

export default function DataGrid({
  columns,
  rows,
  maxHeight = "500px",
  exportFilename,
}: DataGridProps) {
  const [sorting, setSorting] = useState<SortingState>([]);

  const tableColumns = useMemo<ColumnDef<unknown[]>[]>(
    () =>
      columns.map((col, idx) => ({
        id: col,
        accessorFn: (row: unknown[]) => row[idx],
        header: ({ column }) => (
          <button
            className="flex items-center gap-1 font-mono text-xs font-semibold uppercase tracking-wider text-forge-muted hover:text-foreground"
            onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
          >
            {col}
            {column.getIsSorted() === "asc" ? (
              <ArrowUp className="h-3 w-3" />
            ) : column.getIsSorted() === "desc" ? (
              <ArrowDown className="h-3 w-3" />
            ) : (
              <ArrowUpDown className="h-3 w-3 opacity-40" />
            )}
          </button>
        ),
        cell: ({ getValue }) => {
          const val = getValue();
          if (val === null || val === undefined) {
            return <span className="text-forge-muted/50 italic">null</span>;
          }
          return (
            <span className="truncate font-mono text-xs">
              {String(val)}
            </span>
          );
        },
      })),
    [columns],
  );

  const table = useReactTable({
    data: rows,
    columns: tableColumns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const exportCsv = () => {
    const header = columns.join(",");
    const body = rows.map((r) =>
      r.map((v) => {
        if (v === null || v === undefined) return "";
        const s = String(v);
        return s.includes(",") || s.includes('"')
          ? `"${s.replace(/"/g, '""')}"`
          : s;
      }).join(","),
    ).join("\n");
    const blob = new Blob([header + "\n" + body], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = exportFilename || "export.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-col gap-2">
      {exportFilename && (
        <div className="flex justify-end">
          <button
            onClick={exportCsv}
            className="inline-flex items-center gap-1.5 rounded-md border border-forge-border px-2.5 py-1 text-xs text-forge-muted hover:bg-forge-border/50 hover:text-foreground"
          >
            <Download className="h-3 w-3" />
            Export CSV
          </button>
        </div>
      )}
      <div
        className="overflow-auto rounded-lg border border-forge-border"
        style={{ maxHeight }}
      >
        <table className="w-full min-w-max border-collapse">
          <thead className="sticky top-0 z-10 bg-forge-surface">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((header) => (
                  <th
                    key={header.id}
                    className="border-b border-forge-border px-3 py-2 text-left"
                  >
                    {header.isPlaceholder
                      ? null
                      : flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                className={cn(
                  "border-b border-forge-border/50 transition-colors hover:bg-forge-border/20",
                )}
              >
                {row.getVisibleCells().map((cell) => (
                  <td
                    key={cell.id}
                    className="max-w-[200px] truncate whitespace-nowrap px-3 py-1.5 text-sm text-foreground"
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && (
          <div className="py-8 text-center text-sm text-forge-muted">
            No data to display
          </div>
        )}
      </div>
    </div>
  );
}
