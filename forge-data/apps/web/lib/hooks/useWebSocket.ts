"use client";

import { useEffect, useMemo, useRef } from "react";
import { io, type Socket } from "socket.io-client";
import { useWorkspaceStore } from "@/lib/stores/workspaceStore";
import { getSocketBaseUrl } from "@/lib/socket";

interface UseWebSocketOptions {
  workflowId: string;
  workspaceId?: string | null;
}

type RunStartedPayload = {
  workflow_id?: string;
  run_id?: string;
};

type NodeStatusChangePayload = {
  workflow_id?: string;
  run_id?: string;
  node_id?: string;
  status?: "pending" | "running" | "success" | "failed" | "skipped";
};

type RunCompletedPayload = {
  workflow_id?: string;
  run_id?: string;
  status?: "success" | "failed" | "cancelled";
};

export function useWebSocket({ workflowId, workspaceId }: UseWebSocketOptions) {
  const socketRef = useRef<Socket | null>(null);
  const onRunStarted = useWorkspaceStore((s) => s.handleWorkflowRunStarted);
  const onNodeStatusChange = useWorkspaceStore((s) => s.handleWorkflowNodeStatusChange);
  const onRunCompleted = useWorkspaceStore((s) => s.handleWorkflowRunCompleted);

  const authPayload = useMemo(
    () => ({
      workflow_id: workflowId,
      workspace_id: workspaceId ?? undefined,
    }),
    [workflowId, workspaceId],
  );

  useEffect(() => {
    if (!workflowId || !workspaceId) return;

    const socket = io(getSocketBaseUrl(), {
      path: "/socket.io",
      transports: ["websocket", "polling"],
      withCredentials: true,
      auth: authPayload,
    });

    socket.on("run_started", (payload: RunStartedPayload) => {
      const targetWorkflowId = payload.workflow_id ?? workflowId;
      if (!payload.run_id) return;
      onRunStarted(targetWorkflowId, payload.run_id);
    });

    socket.on("node_status_change", (payload: NodeStatusChangePayload) => {
      const targetWorkflowId = payload.workflow_id ?? workflowId;
      if (!payload.node_id || !payload.status) return;
      onNodeStatusChange(targetWorkflowId, payload.node_id, payload.status, payload.run_id);
    });

    socket.on("run_completed", (payload: RunCompletedPayload) => {
      const targetWorkflowId = payload.workflow_id ?? workflowId;
      if (!payload.run_id || !payload.status) return;
      onRunCompleted(targetWorkflowId, payload.run_id, payload.status);
    });

    socketRef.current = socket;
    return () => {
      socket.disconnect();
      socketRef.current = null;
    };
  }, [authPayload, onNodeStatusChange, onRunCompleted, onRunStarted, workflowId, workspaceId]);

  return {
    socketRef,
  };
}
