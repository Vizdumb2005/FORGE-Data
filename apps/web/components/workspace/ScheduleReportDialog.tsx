"use client";

import { useMemo, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { scheduleReport } from "@/lib/api/publishing";
import { toast } from "@/components/ui/use-toast";
import type { CellState } from "@/lib/stores/workspaceStore";

interface ScheduleReportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workspaceId: string;
  cellStates: Record<string, CellState>;
  cellOrder: string[];
}

const PRESETS: Record<string, string> = {
  daily9: "0 9 * * *",
  weeklyMon: "0 9 * * 1",
};

export default function ScheduleReportDialog({
  open,
  onOpenChange,
  workspaceId,
  cellStates,
  cellOrder,
}: ScheduleReportDialogProps) {
  const [format, setFormat] = useState<"html" | "pdf">("pdf");
  const [scheduleMode, setScheduleMode] = useState("daily9");
  const [customCron, setCustomCron] = useState("0 9 * * *");
  const [deliveryType, setDeliveryType] = useState<"email" | "slack_webhook">("email");
  const [emails, setEmails] = useState("");
  const [webhook, setWebhook] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(() => new Set(cellOrder));

  const cells = useMemo(() => cellOrder.map((id) => cellStates[id]).filter(Boolean), [cellOrder, cellStates]);
  const cron = scheduleMode === "custom" ? customCron : PRESETS[scheduleMode];

  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };

  const submit = async () => {
    setSubmitting(true);
    try {
      const delivery =
        deliveryType === "email"
          ? { type: "email", recipients: emails.split(",").map((e) => e.trim()).filter(Boolean) }
          : { type: "slack_webhook", url: webhook.trim() };
      await scheduleReport(workspaceId, {
        cell_ids: Array.from(selected),
        format,
        schedule: cron,
        delivery,
      });
      toast({ title: "Report scheduled" });
      onOpenChange(false);
    } catch {
      toast({ title: "Failed to schedule report", variant: "destructive" });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Schedule Report</DialogTitle>
          <DialogDescription>Generate recurring HTML/PDF reports for selected cells.</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <Label className="mb-2 block">Cells</Label>
            <div className="max-h-40 space-y-2 overflow-auto rounded border border-forge-border p-2">
              {cells.map((c) => (
                <label key={c.cell.id} className="flex items-center gap-2 rounded p-2 hover:bg-forge-border/30">
                  <input type="checkbox" checked={selected.has(c.cell.id)} onChange={() => toggle(c.cell.id)} />
                  <span className="text-xs">{c.cell.cell_type.toUpperCase()} • {c.cell.language}</span>
                </label>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="mb-2 block">Format</Label>
              <Select value={format} onValueChange={(v) => setFormat(v as "html" | "pdf")}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="html">HTML</SelectItem>
                  <SelectItem value="pdf">PDF</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="mb-2 block">Schedule</Label>
              <Select value={scheduleMode} onValueChange={setScheduleMode}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="daily9">Daily at 9am</SelectItem>
                  <SelectItem value="weeklyMon">Weekly Monday</SelectItem>
                  <SelectItem value="custom">Custom cron</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {scheduleMode === "custom" ? (
            <div>
              <Label className="mb-2 block">Cron expression</Label>
              <Input value={customCron} onChange={(e) => setCustomCron(e.target.value)} />
            </div>
          ) : null}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="mb-2 block">Delivery</Label>
              <Select value={deliveryType} onValueChange={(v) => setDeliveryType(v as "email" | "slack_webhook")}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="email">Email</SelectItem>
                  <SelectItem value="slack_webhook">Slack Webhook</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              {deliveryType === "email" ? (
                <>
                  <Label className="mb-2 block">Recipients (comma separated)</Label>
                  <Input value={emails} onChange={(e) => setEmails(e.target.value)} placeholder="a@x.com,b@y.com" />
                </>
              ) : (
                <>
                  <Label className="mb-2 block">Webhook URL</Label>
                  <Input value={webhook} onChange={(e) => setWebhook(e.target.value)} placeholder="https://hooks.slack.com/..." />
                </>
              )}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} disabled={submitting || selected.size === 0}>
            {submitting ? "Scheduling..." : "Schedule"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

