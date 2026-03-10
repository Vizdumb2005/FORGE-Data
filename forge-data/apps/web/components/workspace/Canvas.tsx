"use client";

import { useCallback, useRef } from "react";
import ReactFlow, {
  addEdge,
  Background,
  Controls,
  MiniMap,
  useEdgesState,
  useNodesState,
  type Connection,
  type NodeTypes,
  type Node,
} from "reactflow";
import "reactflow/dist/style.css";
import { useWorkspaceStore } from "@/lib/stores/workspaceStore";
import CellNode from "./Cell";
import AddCellMenu from "./AddCellMenu";

const nodeTypes: NodeTypes = { cell: CellNode };

interface CanvasProps {
  workspaceId: string;
}

export default function Canvas({ workspaceId }: CanvasProps) {
  const cells = useWorkspaceStore((s) => s.cells);

  const initialNodes: Node[] = cells.map((c) => ({
    id: c.id,
    type: "cell",
    position: { x: c.position_x, y: c.position_y },
    data: { cell: c, workspaceId },
    style: { width: c.width, height: c.height },
  }));

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const updatePositionRef = useRef(useWorkspaceStore.getState().updateCellPosition);

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge(params, eds)),
    [setEdges]
  );

  const onNodeDragStop = useCallback(
    (_: React.MouseEvent, node: Node) => {
      updatePositionRef.current(
        node.id,
        workspaceId,
        node.position.x,
        node.position.y
      );
    },
    [workspaceId]
  );

  return (
    <div className="relative h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeDragStop={onNodeDragStop}
        nodeTypes={nodeTypes}
        fitView
        className="bg-forge-bg"
      >
        <Background color="#1e2433" gap={24} />
        <Controls className="!border-forge-border !bg-forge-surface !text-foreground" />
        <MiniMap
          className="!border-forge-border !bg-forge-surface"
          nodeColor="#1e2433"
          maskColor="rgba(10,12,16,0.7)"
        />
      </ReactFlow>

      {/* Floating add-cell button */}
      <div className="absolute bottom-6 left-1/2 -translate-x-1/2">
        <AddCellMenu workspaceId={workspaceId} />
      </div>
    </div>
  );
}
