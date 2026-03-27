import type { AutomationNodeType } from "@/types";

let draggedNodeType: AutomationNodeType | null = null;

export function setDraggedNodeType(nodeType: AutomationNodeType | null): void {
  draggedNodeType = nodeType;
}

export function getDraggedNodeType(): AutomationNodeType | null {
  return draggedNodeType;
}
