"use client";

import { useMemo, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const TEMPLATES = [
  {
    id: "daily-drift",
    icon: "📉",
    name: "Daily Drift Monitor",
    description: "Checks drift on selected datasets and alerts if threshold exceeded.",
    params: ["dataset_id", "threshold"],
  },
  {
    id: "retrain-and-publish",
    icon: "🔁",
    name: "Retrain & Publish",
    description: "Retrains model and publishes updated dashboard snapshot.",
    params: ["model_name", "dashboard_slug"],
  },
  {
    id: "sql-alert",
    icon: "🛎️",
    name: "SQL Alert Pipeline",
    description: "Runs SQL checks and sends email notifications on anomalies.",
    params: ["query", "email_to"],
  },
  {
    id: "api-sync",
    icon: "🔗",
    name: "API Sync",
    description: "Pulls data from API and triggers downstream transformation.",
    params: ["endpoint", "auth_token"],
  },
];

interface TemplateGalleryProps {
  open: boolean;
  onClose: () => void;
  onSelect: (templateId: string, name: string, config: Record<string, unknown>) => Promise<void>;
}

export default function TemplateGallery({ open, onClose, onSelect }: TemplateGalleryProps) {
  const [selectedTemplate, setSelectedTemplate] = useState<string>("");
  const [workflowName, setWorkflowName] = useState("");
  const [formState, setFormState] = useState<Record<string, string>>({});

  const activeTemplate = useMemo(
    () => TEMPLATES.find((t) => t.id === selectedTemplate) ?? null,
    [selectedTemplate],
  );

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-3xl bg-[#0f131b]">
        <DialogHeader>
          <DialogTitle>Workflow Templates</DialogTitle>
          <DialogDescription>Choose a starter and configure parameters.</DialogDescription>
        </DialogHeader>

        {!selectedTemplate ? (
          <div className="grid grid-cols-2 gap-3">
            {TEMPLATES.map((tpl) => (
              <button
                key={tpl.id}
                onClick={() => {
                  setSelectedTemplate(tpl.id);
                  setWorkflowName(tpl.name);
                }}
                className="rounded-lg border border-forge-border bg-forge-surface p-4 text-left hover:border-[#f97316]/70"
              >
                <p className="text-lg">{tpl.icon}</p>
                <p className="mt-2 font-semibold">{tpl.name}</p>
                <p className="mt-1 text-sm text-forge-muted">{tpl.description}</p>
                <span className="mt-3 inline-block text-xs text-[#f97316]">Use Template</span>
              </button>
            ))}
          </div>
        ) : (
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label>Workflow Name</Label>
              <Input value={workflowName} onChange={(e) => setWorkflowName(e.target.value)} />
            </div>
            {activeTemplate?.params.map((param) => (
              <div key={param} className="space-y-1.5">
                <Label>{param}</Label>
                <Input
                  value={formState[param] ?? ""}
                  onChange={(e) => setFormState((prev) => ({ ...prev, [param]: e.target.value }))}
                />
              </div>
            ))}
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setSelectedTemplate("")}>Back</Button>
              <Button
                className="bg-[#f97316] text-black hover:bg-[#ea580c]"
                onClick={async () => {
                  if (!activeTemplate) return;
                  await onSelect(activeTemplate.id, workflowName, formState);
                  onClose();
                }}
              >
                Create from Template
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
