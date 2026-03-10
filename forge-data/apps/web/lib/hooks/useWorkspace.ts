import { useEffect } from "react";
import { useWorkspaceStore } from "@/lib/stores/workspaceStore";
import type { WorkspaceCreatePayload, WorkspaceUpdatePayload, CellCreatePayload } from "@/types";

export function useWorkspace(workspaceId?: string) {
  const store = useWorkspaceStore();

  useEffect(() => {
    store.fetchWorkspaces();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (workspaceId) {
      store.fetchCells(workspaceId);
    }
  }, [workspaceId]); // eslint-disable-line react-hooks/exhaustive-deps

  const createWorkspace = (payload: WorkspaceCreatePayload) =>
    store.createWorkspace(payload);

  const updateWorkspace = (id: string, payload: WorkspaceUpdatePayload) =>
    store.updateWorkspace(id, payload);

  const deleteWorkspace = (id: string) => store.deleteWorkspace(id);

  const createCell = (payload: CellCreatePayload) => {
    if (!workspaceId) throw new Error("workspaceId required to create a cell");
    return store.createCell(workspaceId, payload);
  };

  const deleteCell = (cellId: string) => {
    if (!workspaceId) throw new Error("workspaceId required to delete a cell");
    return store.deleteCell(cellId, workspaceId);
  };

  return {
    workspaces: store.workspaces,
    activeWorkspace: store.activeWorkspace,
    cells: workspaceId ? store.cells : [],
    loading: store.loading,
    error: store.error,
    setActive: store.setActiveWorkspace,
    createWorkspace,
    updateWorkspace,
    deleteWorkspace,
    createCell,
    deleteCell,
  };
}
