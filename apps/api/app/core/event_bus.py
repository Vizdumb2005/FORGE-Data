"""FORGE Event Bus for dataset/experiment-triggered workflows."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from sqlalchemy import and_, select

from app.core.redis import get_redis
from app.database import AsyncSessionLocal
from app.models.workflow import Workflow, WorkflowTriggerType

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.core.workflow_engine import OrionEngine


class ForgeEventBus:
    EVENTS: ClassVar[set[str]] = {
        "dataset.version_created",
        "dataset.quality_check_failed",
        "dataset.quality_check_passed",
        "experiment.run_completed",
        "experiment.metric_threshold_crossed",
    }

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        if event_type not in self.EVENTS:
            raise ValueError(f"Unsupported event_type '{event_type}'")
        event = {
            "event_type": event_type,
            "payload": payload,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        serialized = json.dumps(event)
        redis = await get_redis()
        await redis.rpush(f"forge:events:{event_type}", serialized)
        await redis.publish("forge:events", serialized)

    async def subscribe_and_dispatch(self) -> None:
        redis = await get_redis()
        pubsub = redis.pubsub()
        await pubsub.subscribe("forge:events")
        from app.core.workflow_engine import OrionEngine

        engine = OrionEngine()
        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not message:
                    await asyncio.sleep(0.1)
                    continue
                raw = message.get("data")
                if not isinstance(raw, str):
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Skipping invalid forge:events message")
                    continue
                event_type = str(event.get("event_type") or "")
                payload = event.get("payload") or {}
                if event_type not in self.EVENTS or not isinstance(payload, dict):
                    continue
                await self._dispatch_event(engine, event_type, payload)
        finally:
            await pubsub.unsubscribe("forge:events")
            await pubsub.close()

    async def _dispatch_event(self, engine: OrionEngine, event_type: str, payload: dict[str, Any]) -> None:
        dataset_id = payload.get("dataset_id")
        workspace_id = payload.get("workspace_id")
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Workflow).where(
                    and_(
                        Workflow.is_active.is_(True),
                        Workflow.trigger_type == WorkflowTriggerType.dataset_event.value,
                    )
                )
            )
            workflows = list(result.scalars().all())

        for workflow in workflows:
            if workspace_id and str(workflow.workspace_id) != str(workspace_id):
                continue
            trigger_config = workflow.trigger_config or {}
            if trigger_config.get("event_type") != event_type:
                continue
            configured_dataset = trigger_config.get("dataset_id")
            if configured_dataset and str(configured_dataset) != str(dataset_id or ""):
                continue
            await engine.start_run(
                workflow_id=workflow.id,
                triggered_by="dataset_event",
                triggered_by_user_id=None,
                run_metadata={"workspace_id": workflow.workspace_id},
                trigger_payload=payload,
            )

    async def get_recent_events(
        self,
        event_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        redis = await get_redis()
        if event_type:
            keys = [f"forge:events:{event_type}"]
        else:
            keys = [f"forge:events:{name}" for name in sorted(self.EVENTS)]
        items: list[dict[str, Any]] = []
        for key in keys:
            raw_entries = await redis.lrange(key, -max(1, limit), -1)
            for raw in raw_entries:
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    items.append(parsed)
        items.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
        return items[:limit]


event_bus = ForgeEventBus()

