"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import { io, type Socket } from "socket.io-client";
import { useWorkspaceStore } from "@/lib/stores/workspaceStore";
import { useAuthStore } from "@/lib/stores/authStore";
import { useToast } from "@/components/ui/use-toast";

type PresenceUser = {
  user_id: string;
  name: string;
  color: string;
  cursor_cell_id: string | null;
  last_seen: number;
};

type SharedOutput = {
  outputs?: Array<{ mime_type: string; data: Record<string, unknown> }>;
  status?: string;
};

export function useWorkspaceSocket(workspaceId: string) {
  const store = useWorkspaceStore();
  const activeCellId = useWorkspaceStore((s) => s.activeCellId);
  const lockedCells = useWorkspaceStore((s) => s.lockedCells);
  const currentUser = useAuthStore((s) => s.user);
  const { toast } = useToast();
  const socketRef = useRef<Socket | null>(null);
  const lastLockedToastRef = useRef<{ cellId: string; at: number } | null>(null);

  const authPayload = useMemo(
    () => ({
      workspace_id: workspaceId,
    }),
    [workspaceId],
  );

  useEffect(() => {
    if (!workspaceId) return;

    const socket = io("/", {
      path: "/socket.io",
      transports: ["websocket", "polling"],
      withCredentials: true,
      auth: authPayload,
    });

    socket.on("presence_update", (payload: { users?: PresenceUser[] }) => {
      const users = (payload.users ?? []).map((u) => ({
        user_id: u.user_id,
        user_name: u.name,
        color: u.color,
        cursor_cell_id: u.cursor_cell_id,
        last_seen: u.last_seen,
      }));
      store.setPresenceMap(users);
    });

    socket.on("cursor_update", (payload: { user_id: string; user_name: string; color: string; cell_id: string }) => {
      store.upsertCursor({
        user_id: payload.user_id,
        user_name: payload.user_name,
        color: payload.color,
        cell_id: payload.cell_id,
        last_seen: Date.now(),
      });
    });

    socket.on("cell_locked", (payload: { cell_id: string; user_id: string; user_name: string; color: string }) => {
      store.setCellLocked(payload.cell_id, {
        user_id: payload.user_id,
        user_name: payload.user_name,
        color: payload.color,
      });
    });

    socket.on("cell_locked_by", (payload: { cell_id?: string; user_id?: string; user_name?: string; color?: string; error?: string }) => {
      const cellId = payload.cell_id;
      const userName = payload.user_name;
      if (cellId && payload.user_id && userName && payload.color) {
        store.setCellLocked(cellId, {
          user_id: payload.user_id,
          user_name: userName,
          color: payload.color,
        });
      }
      if (cellId && userName) {
        const now = Date.now();
        const prev = lastLockedToastRef.current;
        if (!prev || prev.cellId !== cellId || now - prev.at > 2000) {
          toast({ title: `This cell is being edited by ${userName}` });
          lastLockedToastRef.current = { cellId, at: now };
        }
      } else if (payload.error === "insufficient_role") {
        toast({ title: "Editor role required to lock cells", variant: "destructive" });
      }
    });

    socket.on("cell_unlocked", (payload: { cell_id: string }) => {
      store.setCellUnlocked(payload.cell_id);
      store.clearTypingIndicator(payload.cell_id);
    });

    socket.on("cell_content_update", (payload: { cell_id: string; content: string; user_id?: string }) => {
      const typingUser = lockedCells[payload.cell_id];
      if (payload.user_id && typingUser && payload.user_id === typingUser.user_id) {
        store.setTypingIndicator(payload.cell_id, {
          user_id: typingUser.user_id,
          user_name: typingUser.user_name,
          color: typingUser.color,
          char_count: payload.content.length,
          last_seen: Date.now(),
        });
      }
      if (activeCellId !== payload.cell_id) {
        store.applyRemoteCellContent(payload.cell_id, payload.content);
      }
    });

    socket.on("cell_executed", (payload: { cell_id: string; output: SharedOutput }) => {
      store.applyRemoteCellOutput(payload.cell_id, {
        outputs: payload.output?.outputs ?? [],
        status: payload.output?.status,
      });
    });

    socketRef.current = socket;
    return () => {
      socket.disconnect();
      socketRef.current = null;
    };
  }, [workspaceId, authPayload, store, toast, activeCellId, lockedCells]);

  const emitCursorMove = useCallback(
    (cellId: string) => {
      socketRef.current?.emit("cursor_move", { workspace_id: workspaceId, cell_id: cellId });
    },
    [workspaceId],
  );

  const emitCellFocus = useCallback(
    (cellId: string) => {
      socketRef.current?.emit("cell_focus", { workspace_id: workspaceId, cell_id: cellId });
    },
    [workspaceId],
  );

  const emitCellBlur = useCallback(
    (cellId: string) => {
      socketRef.current?.emit("cell_blur", { workspace_id: workspaceId, cell_id: cellId });
    },
    [workspaceId],
  );

  const emitCellContentChange = useCallback(
    (cellId: string, content: string) => {
      if (!currentUser) return;
      socketRef.current?.emit("cell_content_change", {
        workspace_id: workspaceId,
        cell_id: cellId,
        content,
      });
    },
    [workspaceId, currentUser],
  );

  return {
    socket: socketRef,
    emitCursorMove,
    emitCellFocus,
    emitCellBlur,
    emitCellContentChange,
  };
}
