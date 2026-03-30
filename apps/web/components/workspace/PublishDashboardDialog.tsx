"use client";

import { useMemo, useState } from "react";
import { Copy, Share2 } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { publishDashboard } from "@/lib/api/publishing";
import { toast } from "@/components/ui/use-toast";
import type { CellState } from "@/lib/stores/workspaceStore";

interface PublishDashboardDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workspaceId: string;
  cellStates: Record<string, CellState>;
  cellOrder: string[];
}

const REFRESH_OPTIONS = [
  { label: "15 min", value: "15" },
  { label: "1 hour", value: "60" },
  { label: "6 hours", value: "360" },
  { label: "24 hours", value: "1440" },
];

export default function PublishDashboardDialog({
  open,
  onOpenChange,
  workspaceId,
  cellStates,
  cellOrder,
}: PublishDashboardDialogProps) {
  const [title, setTitle] = useState("Published Dashboard");
  const [protectedMode, setProtectedMode] = useState(false);
  const [password, setPassword] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [interval, setInterval] = useState("60");
  const [publishing, setPublishing] = useState(false);
  const [publishedUrl, setPublishedUrl] = useState<string>("");
  const [selected, setSelected] = useState<Set<string>>(() => new Set(cellOrder));

  const cells = useMemo(() => cellOrder.map((id) => cellStates[id]).filter(Boolean), [cellOrder, cellStates]);
  const previewSlug = useMemo(() => {
    const t = title.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-");
    return t ? t.slice(0, 24) : "dashboard";
  }, [title]);

  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };

  const submit = async () => {
    setPublishing(true);
    try {
      const payload = {
        title,
        cell_ids: Array.from(selected),
        is_public: !protectedMode,
        password: protectedMode ? password : undefined,
        refresh_interval_minutes: autoRefresh ? Number(interval) : null,
      };
      const res = await publishDashboard(workspaceId, payload);
      const full = `${window.location.origin}${res.url}`;
      setPublishedUrl(full);
      toast({ title: "Dashboard published", description: full });
    } catch {
      toast({ title: "Failed to publish", variant: "destructive" });
    } finally {
      setPublishing(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Share2 className="h-4 w-4" /> Publish Dashboard
          </DialogTitle>
          <DialogDescription>One-click publish to a shareable live dashboard.</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <Label className="mb-2 block">Cells</Label>
            <div className="max-h-44 space-y-2 overflow-auto rounded border border-forge-border p-2">
              {cells.map((c) => (
                <label key={c.cell.id} className="flex cursor-pointer items-center gap-2 rounded p-2 hover:bg-forge-border/30">
                  <input
                    type="checkbox"
                    checked={selected.has(c.cell.id)}
                    onChange={() => toggle(c.cell.id)}
                    className="h-4 w-4"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-xs font-semibold">{c.cell.cell_type.toUpperCase()} • {c.cell.language}</div>
                    <div className="truncate text-[11px] text-forge-muted">{c.localContent || "Empty cell"}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          <div>
            <Label className="mb-2 block">Title</Label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>

          <div className="flex items-center gap-2">
            <Button variant={!protectedMode ? "default" : "outline"} size="sm" onClick={() => setProtectedMode(false)}>
              Public
            </Button>
            <Button variant={protectedMode ? "default" : "outline"} size="sm" onClick={() => setProtectedMode(true)}>
              Password Protected
            </Button>
          </div>

          {protectedMode ? (
            <div>
              <Label className="mb-2 block">Password</Label>
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </div>
          ) : null}

          <div className="flex items-center gap-2">
            <Button variant={autoRefresh ? "default" : "outline"} size="sm" onClick={() => setAutoRefresh((v) => !v)}>
              Auto-refresh {autoRefresh ? "On" : "Off"}
            </Button>
            {autoRefresh ? (
              <Select value={interval} onValueChange={setInterval}>
                <SelectTrigger className="w-[140px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {REFRESH_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : null}
          </div>

          <div className="rounded border border-forge-border p-2 text-xs text-forge-muted">
            Preview link: {window?.location?.origin ?? ""}/d/{previewSlug}
          </div>

          {publishedUrl ? (
            <div className="rounded border border-green-500/30 bg-green-950/20 p-2">
              <div className="mb-1 text-xs text-green-300">Shareable URL</div>
              <div className="flex items-center gap-2">
                <Input value={publishedUrl} readOnly />
                <Button
                  size="icon"
                  variant="outline"
                  onClick={async () => {
                    await navigator.clipboard.writeText(publishedUrl);
                    toast({ title: "Copied link" });
                  }}
                >
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ) : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Close</Button>
          <Button onClick={submit} disabled={publishing || selected.size === 0}>
            {publishing ? "Publishing..." : "Publish"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

