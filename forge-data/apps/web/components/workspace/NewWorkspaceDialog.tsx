"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { useWorkspace } from "@/lib/hooks/useWorkspace";
import { useToast } from "@/components/ui/use-toast";

const schema = z.object({
  name: z.string().min(1, "Name is required").max(255),
  description: z.string().max(2000).optional(),
});

type FormValues = z.infer<typeof schema>;

interface NewWorkspaceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function NewWorkspaceDialog({
  open,
  onOpenChange,
}: NewWorkspaceDialogProps) {
  const { createWorkspace } = useWorkspace();
  const { toast } = useToast();
  const [submitting, setSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (data: FormValues) => {
    setSubmitting(true);
    try {
      await createWorkspace({
        name: data.name,
        description: data.description || undefined,
      });
      toast({ title: "Workspace created", description: data.name });
      reset();
      onOpenChange(false);
    } catch {
      toast({
        title: "Failed to create workspace",
        variant: "destructive",
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New Workspace</DialogTitle>
          <DialogDescription>
            Create a workspace to organize datasets, cells, and experiments.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <label className="mb-1.5 block font-mono text-xs font-medium uppercase tracking-wider text-forge-muted">
              Name
            </label>
            <input
              type="text"
              disabled={submitting}
              {...register("name")}
              className="w-full rounded-md border border-forge-border bg-forge-bg px-3 py-2.5 font-mono text-sm text-foreground placeholder:text-forge-muted/50 focus:border-forge-accent focus:outline-none focus:ring-1 focus:ring-forge-accent/30 disabled:opacity-50"
              placeholder="My Analysis"
              autoFocus
            />
            {errors.name && (
              <p className="mt-1 font-mono text-xs text-red-400">
                {errors.name.message}
              </p>
            )}
          </div>

          <div>
            <label className="mb-1.5 block font-mono text-xs font-medium uppercase tracking-wider text-forge-muted">
              Description
            </label>
            <textarea
              disabled={submitting}
              {...register("description")}
              rows={3}
              className="w-full rounded-md border border-forge-border bg-forge-bg px-3 py-2.5 font-mono text-sm text-foreground placeholder:text-forge-muted/50 focus:border-forge-accent focus:outline-none focus:ring-1 focus:ring-forge-accent/30 disabled:opacity-50 resize-none"
              placeholder="Optional description..."
            />
          </div>

          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              className="rounded-md px-4 py-2 text-sm text-forge-muted hover:text-foreground transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="flex items-center gap-2 rounded-md bg-forge-accent px-4 py-2 font-mono text-sm font-semibold text-forge-bg transition-colors hover:bg-forge-accent-dim disabled:opacity-50"
            >
              {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
              Create
            </button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
