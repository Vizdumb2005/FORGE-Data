"use client";

import { useEffect } from "react";
import { useParams } from "next/navigation";
import { useWorkspaceStore } from "@/lib/stores/workspaceStore";
import Canvas from "@/components/workspace/Canvas";
import ChatPanel from "@/components/ai/ChatPanel";

export default function WorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const { activeWorkspace, workspaces, setActiveWorkspace, fetchCells } =
    useWorkspaceStore();

  useEffect(() => {
    const ws = workspaces.find((w) => w.id === id);
    if (ws) setActiveWorkspace(ws);
    fetchCells(id);
  }, [id, workspaces]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!activeWorkspace) {
    return (
      <div className="flex h-full items-center justify-center text-forge-muted text-sm">
        Loading workspace…
      </div>
    );
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Infinite canvas */}
      <div className="flex-1 overflow-hidden">
        <Canvas workspaceId={id} />
      </div>

      {/* AI chat panel */}
      <div className="w-80 shrink-0 border-l border-forge-border">
        <ChatPanel workspaceId={id} />
      </div>
    </div>
  );
}
