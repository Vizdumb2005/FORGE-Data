"""Semantic layer for workspace metric memory and retrieval."""

from __future__ import annotations

import math

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.metric import Metric

try:
    from sentence_transformers import SentenceTransformer
except ImportError:  # pragma: no cover - dependency may be optional in some environments
    SentenceTransformer = None  # type: ignore[assignment]


_EMBED_MODEL: SentenceTransformer | None = None


class SemanticLayer:
    """
    Team-level memory that persists metric definitions, KPI formulas, and
    business context across sessions. This is FORGE's key differentiator —
    it learns what terms mean for YOUR company.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def define_metric(
        self,
        workspace_id: str,
        user_id: str,
        name: str,
        definition: str,
        formula_sql: str,
        depends_on: list[str] | None = None,
    ) -> Metric:
        text = f"{name}. {definition}. SQL: {formula_sql}"
        embedding = self._embed(text)
        metric = Metric(
            workspace_id=workspace_id,
            created_by=user_id,
            name=name.strip(),
            definition=definition.strip(),
            formula_sql=formula_sql.strip(),
            depends_on=depends_on or [],
            embedding=embedding,
        )
        self.db.add(metric)
        await self.db.flush()
        await self.db.refresh(metric)
        return metric

    async def search_metrics(self, workspace_id: str, query: str) -> list[Metric]:
        query_embedding = self._embed(query)
        result = await self.db.execute(select(Metric).where(Metric.workspace_id == workspace_id))
        metrics = list(result.scalars().all())
        scored: list[tuple[float, Metric]] = []
        for metric in metrics:
            metric_embedding = metric.embedding if isinstance(metric.embedding, list) else []
            if not metric_embedding:
                continue
            scored.append((self._cosine_similarity(query_embedding, metric_embedding), metric))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [metric for _, metric in scored[:5]]

    async def get_context_for_prompt(self, workspace_id: str, prompt: str) -> str:
        matches = await self.search_metrics(workspace_id, prompt)
        if not matches:
            return "No known workspace metrics defined yet."
        lines = ["Known metrics for this workspace:"]
        for metric in matches:
            lines.append(
                f"- {metric.name} = {metric.definition} | SQL: {metric.formula_sql} "
                f"| Depends on: {', '.join(metric.depends_on or [])}"
            )
        return "\n".join(lines)

    async def list_metrics(self, workspace_id: str) -> list[Metric]:
        result = await self.db.execute(
            select(Metric).where(Metric.workspace_id == workspace_id).order_by(Metric.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete_metric(self, workspace_id: str, metric_id: str) -> None:
        result = await self.db.execute(
            delete(Metric)
            .where(Metric.workspace_id == workspace_id, Metric.id == metric_id)
            .returning(Metric.id)
        )
        deleted = result.scalar_one_or_none()
        if deleted is None:
            raise NotFoundException("Metric", metric_id)

    def _embed(self, text: str) -> list[float]:
        model = _get_embedding_model()
        if model is None:
            return []
        vector = model.encode(text)
        return [float(value) for value in vector.tolist()]

    def _cosine_similarity(self, vec_a: list[float], vec_b: list[float]) -> float:
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return -1.0
        dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0 or norm_b == 0:
            return -1.0
        return dot / (norm_a * norm_b)


def _get_embedding_model() -> SentenceTransformer | None:
    global _EMBED_MODEL
    if SentenceTransformer is None:
        return None
    if _EMBED_MODEL is None:
        _EMBED_MODEL = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _EMBED_MODEL
