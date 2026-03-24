"""Workspace lineage tracker for dataflow DAG generation."""

from collections import deque
from datetime import UTC, datetime, timedelta
import re
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cell import Cell
from app.models.dataset import Dataset
from app.models.lineage import LineageEdge, LineageNode

_NODE_SPACING_X = 280
_NODE_SPACING_Y = 140


class LineageTracker:
    """
    Tracks data transformations to build a lineage DAG.
    Every cell execution that produces output is a node.
    Edges connect source datasets → transformation cells → output datasets.
    """

    async def record_execution(
        self,
        db: AsyncSession,
        workspace_id: str,
        cell_id: str,
        input_dataset_ids: list[str],
        output_dataset_ids: list[str],
        code_snippet: str,
        execution_time_ms: int,
        executed_by_user_id: str | None = None,
    ) -> None:
        if not input_dataset_ids and not output_dataset_ids:
            inferred_input_ids, inferred_output_ids = await self._infer_dataset_links(
                db, workspace_id, code_snippet
            )
            input_dataset_ids = inferred_input_ids
            output_dataset_ids = inferred_output_ids

        cell_result = await db.execute(
            select(Cell).where(Cell.id == cell_id, Cell.workspace_id == workspace_id)
        )
        cell = cell_result.scalar_one_or_none()
        if cell is None:
            return

        cell_label = self._cell_label(cell_id, code_snippet)
        cell_node = await self._upsert_node(
            db=db,
            workspace_id=workspace_id,
            node_type="cell",
            ref_id=cell_id,
            label=cell_label,
            metadata_json={
                "cell_id": cell_id,
                "language": cell.language,
                "execution_time_ms": execution_time_ms,
                "code_snippet": code_snippet[:2000],
                "last_executed_by": executed_by_user_id,
            },
            last_executed_at=datetime.now(UTC),
        )

        input_nodes: list[LineageNode] = []
        for dataset_id in input_dataset_ids:
            node = await self._ensure_dataset_node(db, workspace_id, dataset_id)
            if node:
                input_nodes.append(node)

        output_nodes: list[LineageNode] = []
        for dataset_id in output_dataset_ids:
            node = await self._ensure_dataset_node(db, workspace_id, dataset_id)
            if node:
                output_nodes.append(node)

        now = datetime.now(UTC)
        for src in input_nodes:
            await self._upsert_edge(
                db=db,
                workspace_id=workspace_id,
                source_node_id=src.id,
                target_node_id=cell_node.id,
                edge_type="read",
                label="dataset read",
                metadata_json={"transformation": code_snippet[:500]},
                last_seen_at=now,
            )

        for target in output_nodes:
            await self._upsert_edge(
                db=db,
                workspace_id=workspace_id,
                source_node_id=cell_node.id,
                target_node_id=target.id,
                edge_type="write",
                label="dataset write",
                metadata_json={"transformation": code_snippet[:500]},
                last_seen_at=now,
            )

    async def get_workspace_lineage(self, db: AsyncSession, workspace_id: str) -> dict[str, Any]:
        node_rows = await db.execute(
            select(LineageNode).where(LineageNode.workspace_id == workspace_id)
        )
        nodes = list(node_rows.scalars().all())
        edge_rows = await db.execute(
            select(LineageEdge).where(LineageEdge.workspace_id == workspace_id)
        )
        edges = list(edge_rows.scalars().all())

        positioned = self._auto_layout(nodes, edges)

        return {
            "nodes": [
                {
                    "id": node.id,
                    "type": node.node_type,
                    "position": {
                        "x": positioned.get(node.id, {}).get("x", float(node.position_x or 0)),
                        "y": positioned.get(node.id, {}).get("y", float(node.position_y or 0)),
                    },
                    "label": node.label,
                    "metadata": node.metadata_json or {},
                    "last_executed_at": (
                        node.last_executed_at.isoformat() if node.last_executed_at else None
                    ),
                }
                for node in nodes
            ],
            "edges": [
                {
                    "id": edge.id,
                    "source": edge.source_node_id,
                    "target": edge.target_node_id,
                    "type": edge.edge_type,
                    "label": edge.label,
                    "is_active": edge.is_active,
                    "is_recent": bool(
                        edge.last_seen_at and edge.last_seen_at >= datetime.now(UTC) - timedelta(days=1)
                    ),
                    "metadata": edge.metadata_json or {},
                    "last_seen_at": edge.last_seen_at.isoformat() if edge.last_seen_at else None,
                }
                for edge in edges
            ],
        }

    async def delete_cell_lineage(self, db: AsyncSession, workspace_id: str, cell_id: str) -> None:
        node_q = await db.execute(
            select(LineageNode.id).where(
                LineageNode.workspace_id == workspace_id,
                LineageNode.node_type == "cell",
                LineageNode.ref_id == cell_id,
            )
        )
        node_id = node_q.scalar_one_or_none()
        if not node_id:
            return
        await db.execute(
            delete(LineageEdge).where(
                LineageEdge.workspace_id == workspace_id,
                (LineageEdge.source_node_id == node_id) | (LineageEdge.target_node_id == node_id),
            )
        )
        await db.execute(delete(LineageNode).where(LineageNode.id == node_id))

    async def _ensure_dataset_node(
        self, db: AsyncSession, workspace_id: str, dataset_id: str
    ) -> LineageNode | None:
        ds_q = await db.execute(
            select(Dataset).where(Dataset.id == dataset_id, Dataset.workspace_id == workspace_id)
        )
        ds = ds_q.scalar_one_or_none()
        if ds is None:
            return None
        return await self._upsert_node(
            db=db,
            workspace_id=workspace_id,
            node_type="dataset",
            ref_id=ds.id,
            label=ds.name,
            metadata_json={
                "dataset_id": ds.id,
                "row_count": ds.row_count,
                "source_type": ds.source_type,
                "version": ds.version,
            },
            last_executed_at=None,
        )

    async def _upsert_node(
        self,
        *,
        db: AsyncSession,
        workspace_id: str,
        node_type: str,
        ref_id: str,
        label: str,
        metadata_json: dict | None,
        last_executed_at: datetime | None,
    ) -> LineageNode:
        query = await db.execute(
            select(LineageNode).where(
                LineageNode.workspace_id == workspace_id,
                LineageNode.node_type == node_type,
                LineageNode.ref_id == ref_id,
            )
        )
        node = query.scalar_one_or_none()
        if node is None:
            node = LineageNode(
                workspace_id=workspace_id,
                node_type=node_type,
                ref_id=ref_id,
                label=label,
                metadata_json=metadata_json or {},
                last_executed_at=last_executed_at,
            )
            db.add(node)
            await db.flush()
            return node

        node.label = label
        node.metadata_json = metadata_json or {}
        if last_executed_at is not None:
            node.last_executed_at = last_executed_at
        await db.flush()
        return node

    async def _upsert_edge(
        self,
        *,
        db: AsyncSession,
        workspace_id: str,
        source_node_id: str,
        target_node_id: str,
        edge_type: str,
        label: str,
        metadata_json: dict | None,
        last_seen_at: datetime,
    ) -> None:
        query = await db.execute(
            select(LineageEdge).where(
                LineageEdge.workspace_id == workspace_id,
                LineageEdge.source_node_id == source_node_id,
                LineageEdge.target_node_id == target_node_id,
                LineageEdge.edge_type == edge_type,
            )
        )
        edge = query.scalar_one_or_none()
        if edge is None:
            edge = LineageEdge(
                workspace_id=workspace_id,
                source_node_id=source_node_id,
                target_node_id=target_node_id,
                edge_type=edge_type,
                label=label,
                metadata_json=metadata_json or {},
                is_active=True,
                last_seen_at=last_seen_at,
            )
            db.add(edge)
            await db.flush()
            return
        edge.label = label
        edge.metadata_json = metadata_json or {}
        edge.is_active = True
        edge.last_seen_at = last_seen_at
        await db.flush()

    def _cell_label(self, cell_id: str, code_snippet: str) -> str:
        first_line = (code_snippet or "").strip().splitlines()
        if first_line and first_line[0]:
            text = first_line[0].strip()
            return text[:64]
        return f"Cell {cell_id[:8]}"

    def _auto_layout(self, nodes: list[LineageNode], edges: list[LineageEdge]) -> dict[str, dict[str, float]]:
        if not nodes:
            return {}
        in_degree: dict[str, int] = {n.id: 0 for n in nodes}
        outgoing: dict[str, list[str]] = {n.id: [] for n in nodes}
        for edge in edges:
            if edge.source_node_id in outgoing and edge.target_node_id in in_degree:
                outgoing[edge.source_node_id].append(edge.target_node_id)
                in_degree[edge.target_node_id] += 1

        queue = deque([node_id for node_id, deg in in_degree.items() if deg == 0])
        layers: dict[str, int] = {node_id: 0 for node_id in in_degree}
        while queue:
            current = queue.popleft()
            for nxt in outgoing.get(current, []):
                layers[nxt] = max(layers.get(nxt, 0), layers.get(current, 0) + 1)
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)

        by_layer: dict[int, list[str]] = {}
        for node in nodes:
            layer = layers.get(node.id, 0)
            by_layer.setdefault(layer, []).append(node.id)

        pos: dict[str, dict[str, float]] = {}
        for layer, node_ids in by_layer.items():
            node_ids.sort()
            for idx, node_id in enumerate(node_ids):
                pos[node_id] = {"x": float(layer * _NODE_SPACING_X), "y": float(idx * _NODE_SPACING_Y)}
        return pos

    async def _infer_dataset_links(
        self, db: AsyncSession, workspace_id: str, code_snippet: str
    ) -> tuple[list[str], list[str]]:
        dataset_rows = await db.execute(
            select(Dataset.id, Dataset.name).where(Dataset.workspace_id == workspace_id)
        )
        datasets = list(dataset_rows.all())
        if not datasets:
            return [], []

        lowered = (code_snippet or "").lower()
        outputs: set[str] = set()
        inputs: set[str] = set()

        create_targets = re.findall(
            r"(?:create\s+table|insert\s+into|create\s+or\s+replace\s+table)\s+([a-zA-Z0-9_]+)",
            lowered,
        )
        output_names = {name.strip().lower() for name in create_targets}

        for dataset_id, dataset_name in datasets:
            name_lower = str(dataset_name).lower()
            if not name_lower or name_lower not in lowered:
                continue
            if name_lower in output_names:
                outputs.add(str(dataset_id))
            else:
                inputs.add(str(dataset_id))

        return list(inputs), list(outputs)

