"use client";

import { useState } from "react";
import { Download, FileText, FileType2, NotebookTabs } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { exportWorkspace } from "@/lib/api/publishing";
import { toast } from "@/components/ui/use-toast";
import type { CellState } from "@/lib/stores/workspaceStore";
import ScheduleReportDialog from "./ScheduleReportDialog";

interface ExportMenuProps {
  workspaceId: string;
  cellOrder: string[];
  cellStates: Record<string, CellState>;
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function ExportMenu({ workspaceId, cellOrder, cellStates }: ExportMenuProps) {
  const [openSchedule, setOpenSchedule] = useState(false);

  const doExport = async (format: "jupyter" | "html" | "pdf") => {
    try {
      const blob = await exportWorkspace(workspaceId, format, cellOrder);
      const ext = format === "jupyter" ? "ipynb" : format;
      downloadBlob(blob, `forge-${workspaceId}.${ext}`);
      toast({ title: `Exported ${format.toUpperCase()}` });
    } catch {
      toast({ title: "Export failed", variant: "destructive" });
    }
  };

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm">
            <Download className="h-4 w-4" />
            Export
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={() => void doExport("jupyter")}>
            <NotebookTabs className="h-4 w-4" />
            Export as Jupyter Notebook (.ipynb)
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => void doExport("html")}>
            <FileText className="h-4 w-4" />
            Export as HTML
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => void doExport("pdf")}>
            <FileType2 className="h-4 w-4" />
            Export as PDF
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => setOpenSchedule(true)}>
            Schedule Report
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <ScheduleReportDialog
        open={openSchedule}
        onOpenChange={setOpenSchedule}
        workspaceId={workspaceId}
        cellOrder={cellOrder}
        cellStates={cellStates}
      />
    </>
  );
}

