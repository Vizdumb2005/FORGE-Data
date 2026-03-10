import { create } from "zustand";
import { immer } from "zustand/middleware/immer";
import api from "@/lib/api";
import type {
  Workspace,
  WorkspaceCreatePayload,
  WorkspaceUpdatePayload,
  Cell,
  CellCreatePayload,
} from "@/types";

interface WorkspaceState {
  workspaces: Workspace[];
  activeWorkspace: Workspace | null;
  cells: Cell[];
  loading: boolean;
  error: string | null;
}

interface WorkspaceActions {
  fetchWorkspaces: () => Promise<void>;
  createWorkspace: (payload: WorkspaceCreatePayload) => Promise<Workspace>;
  updateWorkspace: (id: string, payload: WorkspaceUpdatePayload) => Promise<void>;
  deleteWorkspace: (id: string) => Promise<void>;
  setActiveWorkspace: (ws: Workspace | null) => void;
  fetchCells: (workspaceId: string) => Promise<void>;
  createCell: (workspaceId: string, payload: CellCreatePayload) => Promise<Cell>;
  updateCellPosition: (
    cellId: string,
    workspaceId: string,
    x: number,
    y: number
  ) => Promise<void>;
  deleteCell: (cellId: string, workspaceId: string) => Promise<void>;
  clearError: () => void;
}

export const useWorkspaceStore = create<WorkspaceState & WorkspaceActions>()(
  immer((set) => ({
    workspaces: [],
    activeWorkspace: null,
    cells: [],
    loading: false,
    error: null,

    fetchWorkspaces: async () => {
      set((s) => {
        s.loading = true;
      });
      try {
        const resp = await api.get<Workspace[]>("/api/v1/workspaces");
        set((s) => {
          s.workspaces = resp.data;
          s.loading = false;
        });
      } catch {
        set((s) => {
          s.loading = false;
        });
      }
    },

    createWorkspace: async (payload) => {
      const resp = await api.post<Workspace>("/api/v1/workspaces", payload);
      set((s) => {
        s.workspaces.unshift(resp.data);
      });
      return resp.data;
    },

    updateWorkspace: async (id, payload) => {
      const resp = await api.patch<Workspace>(
        `/api/v1/workspaces/${id}`,
        payload
      );
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

    setActiveWorkspace: (ws) =>
      set((s) => {
        s.activeWorkspace = ws;
      }),

    fetchCells: async (workspaceId) => {
      const resp = await api.get<Cell[]>(
        `/api/v1/workspaces/${workspaceId}/cells`
      );
      set((s) => {
        s.cells = resp.data;
      });
    },

    createCell: async (workspaceId, payload) => {
      const resp = await api.post<Cell>(
        `/api/v1/workspaces/${workspaceId}/cells`,
        payload
      );
      set((s) => {
        s.cells.push(resp.data);
      });
      return resp.data;
    },

    updateCellPosition: async (cellId, workspaceId, x, y) => {
      await api.patch(`/api/v1/workspaces/${workspaceId}/cells/${cellId}`, {
        position_x: x,
        position_y: y,
      });
      set((s) => {
        const cell = s.cells.find((c) => c.id === cellId);
        if (cell) {
          cell.position_x = x;
          cell.position_y = y;
        }
      });
    },

    deleteCell: async (cellId, workspaceId) => {
      await api.delete(
        `/api/v1/workspaces/${workspaceId}/cells/${cellId}`
      );
      set((s) => {
        s.cells = s.cells.filter((c) => c.id !== cellId);
      });
    },

    clearError: () =>
      set((s) => {
        s.error = null;
      }),
  }))
);
