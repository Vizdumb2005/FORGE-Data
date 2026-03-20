import { useEffect, useRef, useCallback } from "react";
import { useWorkspaceStore } from "@/lib/stores/workspaceStore";
import api from "@/lib/api";
import { getAccessToken } from "@/lib/auth";
import { parseSseLine } from "@/lib/utils";
import type {
  WorkspaceCreatePayload,
  WorkspaceUpdatePayload,
  CellCreatePayload,
  CellOutput,
} from "@/types";

// All fetch/SSE calls run in the browser (inside useEffect / callbacks).
// Empty string = relative paths → routed through Next.js rewrites.
const BASE_URL = "";
const DEBOUNCE_MS = 500;

export function useWorkspace(workspaceId?: string) {
  const store = useWorkspaceStore();
  const debounceTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  useEffect(() => {
    store.fetchWorkspaces();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (workspaceId) {
      store.fetchCells(workspaceId);
      // Fetch kernel status
      api.get(`/api/v1/workspaces/${workspaceId}/kernel/status`)
        .then((r) => store.setKernelStatus(r.data.status ?? "idle"))
        .catch(() => store.setKernelStatus("unknown"));
    }
  }, [workspaceId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Debounced content sync to API
  const syncContent = useCallback((cellId: string, content: string) => {
    if (!workspaceId) return;

    // Update local state immediately
    store.updateCellContent(cellId, content);

    // Debounce API call
    const existing = debounceTimers.current.get(cellId);
    if (existing) clearTimeout(existing);

    debounceTimers.current.set(cellId, setTimeout(() => {
      debounceTimers.current.delete(cellId);
      store.updateCell(workspaceId, cellId, { content });
    }, DEBOUNCE_MS));
  }, [workspaceId, store]);

  // Run a cell via SSE streaming
  const runCell = useCallback(async (cellId: string) => {
    if (!workspaceId) return;

    const cs = store.cellStates[cellId];
    if (!cs) return;

    const code = cs.localContent;
    const language = cs.cell.language ?? "python";

    // Flush any pending content sync (await to ensure DB is updated before execution)
    const pending = debounceTimers.current.get(cellId);
    if (pending) {
      clearTimeout(pending);
      debounceTimers.current.delete(cellId);
      await store.updateCellSync(workspaceId, cellId, { content: code });
    }

    store.setCellRunStatus(cellId, "running");
    store.clearCellOutputs(cellId);
    store.setKernelStatus("busy");

    try {
      const token = getAccessToken();
      const resp = await fetch(
        `${BASE_URL}/api/v1/workspaces/${workspaceId}/cells/${cellId}/run`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ code, language }),
        }
      );

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: "Execution failed" }));
        store.appendCellOutput(cellId, {
          mime_type: "error",
          data: { ename: "ExecutionError", evalue: err.detail ?? "Unknown error", traceback: [] },
        });
        store.setCellRunStatus(cellId, "error");
        store.setKernelStatus("idle");
        return;
      }

      // Check if SSE or JSON response
      const contentType = resp.headers.get("content-type") ?? "";

      if (contentType.includes("text/event-stream")) {
        // SSE streaming response
        const reader = resp.body!.pipeThrough(new TextDecoderStream()).getReader();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += value;
          const lines = buffer.split("\n");
          buffer = lines.pop()!;

          for (const line of lines) {
            const payload = parseSseLine<{
              event?: string;
              type?: string;
              text?: string;
              data?: Record<string, unknown>;
              mime_type?: string;
              outputs?: CellOutput[];
              execution_time_ms?: number;
              status?: string;
              ename?: string;
              evalue?: string;
              traceback?: string[];
            }>(line);

            if (!payload) continue;

            const eventType = payload.event ?? payload.type ?? "";

            switch (eventType) {
              case "stream":
                store.appendCellOutput(cellId, {
                  mime_type: `stream/${payload.data?.name ?? "stdout"}`,
                  data: { text: payload.text ?? payload.data?.text ?? "" },
                });
                break;
              case "result":
              case "execute_result":
                store.appendCellOutput(cellId, {
                  mime_type: payload.mime_type ?? "text/plain",
                  data: payload.data ?? { "text/plain": payload.text ?? "" },
                });
                break;
              case "image":
              case "display_data":
                store.appendCellOutput(cellId, {
                  mime_type: "image/png",
                  data: payload.data ?? {},
                });
                break;
              case "error":
                store.appendCellOutput(cellId, {
                  mime_type: "error",
                  data: {
                    ename: payload.ename ?? "Error",
                    evalue: payload.evalue ?? "",
                    traceback: payload.traceback ?? [],
                  },
                });
                break;
              case "complete":
                // Final event with aggregated outputs
                if (payload.outputs) {
                  store.setCellOutputs(cellId, payload.outputs);
                }
                break;
            }
          }
        }
      } else {
        // JSON response (SQL cells return direct JSON)
        const data = await resp.json();
        const rawOutputs: CellOutput[] | undefined = data.outputs ?? (data.output ? [data.output] : undefined);
        if (rawOutputs) {
          // Backend sends "type" field; normalize to "mime_type" for frontend
          const normalized = rawOutputs.map((o) => ({
            ...o,
            mime_type:
              o.mime_type ??
              ((o.data as Record<string, unknown> | undefined)?.type as string | undefined) ??
              "text/plain",
          })) as CellOutput[];
          store.setCellOutputs(cellId, normalized);
        }
      }

      // Check final status
      const finalCs = store.cellStates[cellId];
      const hasError = finalCs?.outputs.some((o) => o.mime_type === "error");
      store.setCellRunStatus(cellId, hasError ? "error" : "success");
    } catch (err) {
      store.appendCellOutput(cellId, {
        mime_type: "error",
        data: {
          ename: "NetworkError",
          evalue: err instanceof Error ? err.message : "Failed to connect",
          traceback: [],
        },
      });
      store.setCellRunStatus(cellId, "error");
    } finally {
      store.setKernelStatus("idle");
    }
  }, [workspaceId, store]);

  // Run all cells sequentially
  const runAll = useCallback(async () => {
    if (!workspaceId) return;
    store.setIsRunningAll(true);
    for (const cellId of store.cellOrder) {
      const cs = store.cellStates[cellId];
      if (!cs) continue;
      if (cs.cell.cell_type === "code" || cs.cell.cell_type === "sql") {
        await runCell(cellId);
      }
    }
    store.setIsRunningAll(false);
  }, [workspaceId, store, runCell]);

  const restartKernel = useCallback(async () => {
    if (!workspaceId) return;
    store.setKernelStatus("starting");
    try {
      await api.post(`/api/v1/workspaces/${workspaceId}/kernel/restart`);
      store.setKernelStatus("idle");
    } catch {
      store.setKernelStatus("dead");
    }
  }, [workspaceId, store]);

  const interruptKernel = useCallback(async () => {
    if (!workspaceId) return;
    try {
      await api.post(`/api/v1/workspaces/${workspaceId}/kernel/interrupt`);
    } catch {
      // ignore
    }
  }, [workspaceId]);

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

  // Cleanup debounce timers on unmount
  useEffect(() => {
    const timers = debounceTimers.current;
    return () => {
      timers.forEach((timer) => clearTimeout(timer));
      timers.clear();
    };
  }, []);

  return {
    workspaces: store.workspaces,
    activeWorkspace: store.activeWorkspace,
    cellStates: store.cellStates,
    cellOrder: store.cellOrder,
    kernelStatus: store.kernelStatus,
    activeCellId: store.activeCellId,
    isRunningAll: store.isRunningAll,
    zoom: store.zoom,
    loading: store.loading,
    error: store.error,
    setActive: store.setActiveWorkspace,
    setActiveCellId: store.setActiveCellId,
    setZoom: store.setZoom,
    createWorkspace,
    updateWorkspace,
    deleteWorkspace,
    createCell,
    deleteCell,
    syncContent,
    runCell,
    runAll,
    restartKernel,
    interruptKernel,
  };
}
