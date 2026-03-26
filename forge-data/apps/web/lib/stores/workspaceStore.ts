import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import api from "@/lib/api";
import type {
  Workspace,
  WorkspaceCreatePayload,
  WorkspaceUpdatePayload,
  Cell,
  CellCreatePayload,
  CellUpdatePayload,
  CellOutput,
} from "@/types";

// ── Types ────────────────────────────────────────────────────────────────────

export type KernelStatus = "idle" | "busy" | "starting" | "dead" | "unknown";
export type CellRunStatus = "idle" | "running" | "success" | "error";

export interface CellState {
  cell: Cell;
  runStatus: CellRunStatus;
  outputs: CellOutput[];
  localContent: string;
  dirty: boolean;
}

export interface CollaboratorPresence {
  user_id: string;
  user_name: string;
  color: string;
  cursor_cell_id: string | null;
  last_seen: number;
}

export interface CollaboratorCursor {
  user_id: string;
  user_name: string;
  color: string;
  cell_id: string;
  last_seen: number;
}

export interface CellLockInfo {
  user_id: string;
  user_name: string;
  color: string;
}

interface WorkspaceState {
  workspaces: Workspace[];
  activeWorkspace: Workspace | null;
  cellStates: Record<string, CellState>;
  cellOrder: string[];
  kernelStatus: KernelStatus;
  activeCellId: string | null;
  /** ID of the cell currently receiving AI-streamed code (null when idle) */
  streamingCellId: string | null;
  isRunningAll: boolean;
  zoom: number;
  collaborators: CollaboratorPresence[];
  presenceMap: Record<string, CollaboratorPresence>;
  cursors: Record<string, CollaboratorCursor>;
  lockedCells: Record<string, CellLockInfo>;
  typingByCell: Record<string, { user_id: string; user_name: string; color: string; char_count: number; last_seen: number }>;
  loading: boolean;
  error: string | null;
}

interface WorkspaceActions {
  // Workspace CRUD
  fetchWorkspaces: () => Promise<void>;
  createWorkspace: (payload: WorkspaceCreatePayload) => Promise<Workspace>;
  updateWorkspace: (id: string, payload: WorkspaceUpdatePayload) => Promise<void>;
  deleteWorkspace: (id: string) => Promise<void>;
  setActiveWorkspace: (ws: Workspace | null) => void;

  // Cell CRUD
  fetchCells: (workspaceId: string) => Promise<void>;
  createCell: (workspaceId: string, payload: CellCreatePayload) => Promise<Cell>;
  updateCell: (workspaceId: string, cellId: string, payload: CellUpdatePayload) => void;
  updateCellSync: (workspaceId: string, cellId: string, payload: CellUpdatePayload) => Promise<void>;
  updateCellContent: (cellId: string, content: string) => void;
  applyRemoteCellContent: (cellId: string, content: string) => void;
  applyRemoteCellOutput: (
    cellId: string,
    output: {
      outputs?: CellOutput[];
      status?: string;
    },
  ) => void;
  setPresenceMap: (users: CollaboratorPresence[]) => void;
  upsertCursor: (cursor: CollaboratorCursor) => void;
  setTypingIndicator: (cellId: string, typing: { user_id: string; user_name: string; color: string; char_count: number; last_seen: number }) => void;
  clearTypingIndicator: (cellId: string) => void;
  setCollaborators: (users: CollaboratorPresence[]) => void;
  setCellLocked: (cellId: string, lock: CellLockInfo) => void;
  setCellUnlocked: (cellId: string) => void;
  deleteCell: (cellId: string, workspaceId: string) => Promise<void>;
  updateCellPosition: (cellId: string, workspaceId: string, x: number, y: number) => Promise<void>;
  reorderCells: (orderedIds: string[]) => void;

  // Execution
  setActiveCellId: (id: string | null) => void;
  setCellRunStatus: (cellId: string, status: CellRunStatus) => void;
  appendCellOutput: (cellId: string, output: CellOutput) => void;
  setCellOutputs: (cellId: string, outputs: CellOutput[]) => void;
  clearCellOutputs: (cellId: string) => void;
  setKernelStatus: (status: KernelStatus) => void;
  setIsRunningAll: (running: boolean) => void;

  // Zoom
  setZoom: (zoom: number) => void;

  // AI streaming
  setStreamingCellId: (id: string | null) => void;

  clearError: () => void;
}

export const useWorkspaceStore = create<WorkspaceState & WorkspaceActions>()(
  immer((set) => ({
    workspaces: [],
    activeWorkspace: null,
    cellStates: {},
    cellOrder: [],
    kernelStatus: "unknown",
    activeCellId: null,
    streamingCellId: null,
    isRunningAll: false,
    zoom: 1,
    collaborators: [],
    presenceMap: {},
    cursors: {},
    lockedCells: {},
    typingByCell: {},
    loading: false,
    error: null,

    // ── Workspace CRUD ──────────────────────────────────────────────────

    fetchWorkspaces: async () => {
      set((s) => { s.loading = true; });
      try {
        const resp = await api.get<Workspace[]>("/api/v1/workspaces");
        set((s) => { s.workspaces = resp.data; s.loading = false; });
      } catch {
        set((s) => { s.loading = false; });
      }
    },

    createWorkspace: async (payload) => {
      const resp = await api.post<Workspace>("/api/v1/workspaces", payload);
      set((s) => { s.workspaces.unshift(resp.data); });
      return resp.data;
    },

    updateWorkspace: async (id, payload) => {
      const resp = await api.patch<Workspace>(`/api/v1/workspaces/${id}`, payload);
      set((s) => {
        const idx = s.workspaces.findIndex((w) => w.id === id);
        if (idx !== -1) s.workspaces[idx] = resp.data;
        if (s.activeWorkspace?.id === id) s.activeWorkspace = resp.data;
      });
    },

    deleteWorkspace: async (id) => {
      await api.delete(`/api/v1/workspaces/${id}`);
      set((s) => {
        s.workspaces = s.workspaces.filter((w) => w.id !== id);
        if (s.activeWorkspace?.id === id) s.activeWorkspace = null;
      });
    },

    setActiveWorkspace: (ws) => set((s) => { s.activeWorkspace = ws; }),

    // ── Cell CRUD ───────────────────────────────────────────────────────

    fetchCells: async (workspaceId) => {
      const resp = await api.get<Cell[]>(`/api/v1/workspaces/${workspaceId}/cells`);
      set((s) => {
        const newStates: Record<string, CellState> = {};
        const order: string[] = [];
        for (const cell of resp.data) {
          order.push(cell.id);
          newStates[cell.id] = {
            cell,
            runStatus: "idle",
            outputs: cell.output ? [cell.output] : [],
            localContent: cell.content,
            dirty: false,
          };
        }
        // Sort by position_y then position_x
        order.sort((a, b) => {
          const ca = newStates[a].cell;
          const cb = newStates[b].cell;
          return ca.position_y - cb.position_y || ca.position_x - cb.position_x;
        });
        s.cellStates = newStates;
        s.cellOrder = order;
      });
    },

    createCell: async (workspaceId, payload) => {
      const resp = await api.post<Cell>(`/api/v1/workspaces/${workspaceId}/cells`, payload);
      const cell = resp.data;
      set((s) => {
        s.cellStates[cell.id] = {
          cell,
          runStatus: "idle",
          outputs: [],
          localContent: cell.content,
          dirty: false,
        };
        s.cellOrder.push(cell.id);
        s.activeCellId = cell.id;
      });
      return cell;
    },

    updateCell: (workspaceId, cellId, payload) => {
      // Optimistic update — fire API call in background
      api.patch(`/api/v1/workspaces/${workspaceId}/cells/${cellId}`, payload).catch(() => {});
      set((s) => {
        const cs = s.cellStates[cellId];
        if (!cs) return;
        if (payload.content !== undefined) {
          cs.cell.content = payload.content;
          cs.localContent = payload.content;
          cs.dirty = false;
        }
        if (payload.position_x !== undefined) cs.cell.position_x = payload.position_x;
        if (payload.position_y !== undefined) cs.cell.position_y = payload.position_y;
        if (payload.width !== undefined) cs.cell.width = payload.width;
        if (payload.height !== undefined) cs.cell.height = payload.height;
      });
    },

    updateCellSync: async (workspaceId, cellId, payload) => {
      // Awaitable version — waits for the PATCH to complete before returning
      await api.patch(`/api/v1/workspaces/${workspaceId}/cells/${cellId}`, payload);
      set((s) => {
        const cs = s.cellStates[cellId];
        if (!cs) return;
        if (payload.content !== undefined) {
          cs.cell.content = payload.content;
          cs.localContent = payload.content;
          cs.dirty = false;
        }
      });
    },

    updateCellContent: (cellId, content) => {
      set((s) => {
        const cs = s.cellStates[cellId];
        if (!cs) return;
        cs.localContent = content;
        cs.dirty = content !== cs.cell.content;
      });
    },

    applyRemoteCellContent: (cellId, content) => {
      set((s) => {
        const cs = s.cellStates[cellId];
        if (!cs) return;
        cs.localContent = content;
        cs.cell.content = content;
        cs.dirty = false;
      });
    },

    applyRemoteCellOutput: (cellId, output) => {
      set((s) => {
        const cs = s.cellStates[cellId];
        if (!cs) return;
        cs.cell.output = (output.outputs?.[0] ?? null);
        const outputs = output.outputs ?? [];
        cs.outputs = outputs;
        cs.runStatus = (output.status === "ok" ? "success" : output.status === "error" ? "error" : cs.runStatus);
      });
    },

    setCollaborators: (users) => set((s) => { s.collaborators = users; }),
    setPresenceMap: (users) => set((s) => {
      const map: Record<string, CollaboratorPresence> = {};
      for (const user of users) {
        map[user.user_id] = user;
      }
      s.presenceMap = map;
      s.collaborators = users;
    }),
    upsertCursor: (cursor) => set((s) => {
      s.cursors[cursor.user_id] = cursor;
      const presence = s.presenceMap[cursor.user_id];
      if (presence) {
        presence.cursor_cell_id = cursor.cell_id;
        presence.last_seen = cursor.last_seen;
      }
    }),
    setTypingIndicator: (cellId, typing) => set((s) => {
      s.typingByCell[cellId] = typing;
    }),
    clearTypingIndicator: (cellId) => set((s) => {
      delete s.typingByCell[cellId];
    }),
    setCellLocked: (cellId, lock) => set((s) => { s.lockedCells[cellId] = lock; }),
    setCellUnlocked: (cellId) => set((s) => { delete s.lockedCells[cellId]; }),

    deleteCell: async (cellId, workspaceId) => {
      await api.delete(`/api/v1/workspaces/${workspaceId}/cells/${cellId}`);
      set((s) => {
        delete s.cellStates[cellId];
        s.cellOrder = s.cellOrder.filter((id) => id !== cellId);
        if (s.activeCellId === cellId) s.activeCellId = null;
      });
    },

    updateCellPosition: async (cellId, workspaceId, x, y) => {
      await api.patch(`/api/v1/workspaces/${workspaceId}/cells/${cellId}`, {
        position_x: x,
        position_y: y,
      });
      set((s) => {
        const cs = s.cellStates[cellId];
        if (cs) {
          cs.cell.position_x = x;
          cs.cell.position_y = y;
        }
      });
    },

    reorderCells: (orderedIds) => {
      set((s) => { s.cellOrder = orderedIds; });
    },

    // ── Execution ───────────────────────────────────────────────────────

    setActiveCellId: (id) => set((s) => { s.activeCellId = id; }),

    setCellRunStatus: (cellId, status) => {
      set((s) => {
        const cs = s.cellStates[cellId];
        if (cs) cs.runStatus = status;
      });
    },

    appendCellOutput: (cellId, output) => {
      set((s) => {
        const cs = s.cellStates[cellId];
        if (cs) cs.outputs.push(output);
      });
    },

    setCellOutputs: (cellId, outputs) => {
      set((s) => {
        const cs = s.cellStates[cellId];
        if (cs) cs.outputs = outputs;
      });
    },

    clearCellOutputs: (cellId) => {
      set((s) => {
        const cs = s.cellStates[cellId];
        if (cs) cs.outputs = [];
      });
    },

    setKernelStatus: (status) => set((s) => { s.kernelStatus = status; }),
    setIsRunningAll: (running) => set((s) => { s.isRunningAll = running; }),

    // ── Zoom ────────────────────────────────────────────────────────────

    setZoom: (zoom) => set((s) => { s.zoom = Math.max(0.5, Math.min(2, zoom)); }),

    setStreamingCellId: (id) => set((s) => { s.streamingCellId = id; }),

    clearError: () => set((s) => { s.error = null; }),
  }))
);
