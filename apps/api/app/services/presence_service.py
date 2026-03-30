"""Presence and lock service backed by Redis for collaborative workspace."""

from __future__ import annotations

import json
import time
from typing import Any

from app.core.redis import get_redis
from app.core.ws import ws_manager
from app.models.user import User
from app.services.chat_service import chat_service


class PresenceService:
    def __init__(self) -> None:
        self._cursor_emit_ms: dict[tuple[str, str], int] = {}

    @staticmethod
    def _presence_key(workspace_id: str, user_id: str) -> str:
        return f"forge:presence:{workspace_id}:{user_id}"

    @staticmethod
    def _presence_pattern(workspace_id: str) -> str:
        return f"forge:presence:{workspace_id}:*"

    @staticmethod
    def _lock_key(cell_id: str) -> str:
        return f"forge:lock:{cell_id}"

    @staticmethod
    def _lock_pattern() -> str:
        return "forge:lock:*"

    def _assign_user_color(self, user_id: str) -> str:
        colors = [
            "#f97316",
            "#a78bfa",
            "#34d399",
            "#60a5fa",
            "#f472b6",
            "#fbbf24",
            "#4ade80",
            "#e879f9",
        ]
        return colors[int(str(user_id).replace("-", ""), 16) % 8]

    async def join_workspace(self, workspace_id: str, user: User, websocket_id: str) -> list[dict[str, Any]]:
        redis = await get_redis()
        now = int(time.time())
        state = {
            "user_id": user.id,
            "full_name": user.full_name or user.email,
            "avatar_color": self._assign_user_color(user.id),
            "cursor_x": 0,
            "cursor_y": 0,
            "active_cell_id": None,
            "last_seen": now,
            "websocket_id": websocket_id,
        }
        await redis.hset(self._presence_key(workspace_id, user.id), mapping={k: json.dumps(v) for k, v in state.items()})
        await redis.expire(self._presence_key(workspace_id, user.id), 60)
        await ws_manager.broadcast_to_workspace(
            workspace_id,
            {"type": "user_joined", "data": {"workspace_id": workspace_id, "user": state}},
        )
        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            await chat_service.send_system_message(
                db,
                workspace_id,
                f"{state['full_name']} joined the workspace",
                metadata={"event": "presence_join", "user_id": user.id},
            )
            await db.commit()
        return await self.get_workspace_presence(workspace_id)

    async def leave_workspace(self, workspace_id: str, user_id: str) -> None:
        redis = await get_redis()
        key = self._presence_key(workspace_id, user_id)
        existing = await redis.hgetall(key)
        name = None
        if existing:
            try:
                name = json.loads(existing.get("full_name", "null"))
            except Exception:
                name = None
        await redis.delete(key)
        await self._release_all_locks_for_user(workspace_id, user_id)
        await ws_manager.broadcast_to_workspace(
            workspace_id,
            {"type": "user_left", "data": {"workspace_id": workspace_id, "user_id": user_id}},
        )
        if name:
            from app.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                await chat_service.send_system_message(
                    db,
                    workspace_id,
                    f"{name} left the workspace",
                    metadata={"event": "presence_leave", "user_id": user_id},
                )
                await db.commit()

    async def update_cursor(
        self,
        workspace_id: str,
        user_id: str,
        x: float,
        y: float,
        cell_id: str | None,
    ) -> None:
        redis = await get_redis()
        now = int(time.time())
        key = self._presence_key(workspace_id, user_id)
        await redis.hset(
            key,
            mapping={
                "cursor_x": json.dumps(x),
                "cursor_y": json.dumps(y),
                "active_cell_id": json.dumps(cell_id),
                "last_seen": json.dumps(now),
            },
        )
        await redis.expire(key, 60)
        throttle_key = (workspace_id, user_id)
        now_ms = int(time.time() * 1000)
        prev_ms = self._cursor_emit_ms.get(throttle_key, 0)
        if now_ms - prev_ms < 50:
            return
        self._cursor_emit_ms[throttle_key] = now_ms
        await ws_manager.broadcast_to_workspace(
            workspace_id,
            {
                "type": "cursor_moved",
                "data": {
                    "workspace_id": workspace_id,
                    "user_id": user_id,
                    "cursor_x": x,
                    "cursor_y": y,
                    "active_cell_id": cell_id,
                },
            },
        )

    async def get_workspace_presence(self, workspace_id: str) -> list[dict[str, Any]]:
        redis = await get_redis()
        now = int(time.time())
        cursor = 0
        result: list[dict[str, Any]] = []
        pattern = self._presence_pattern(workspace_id)
        while True:
            cursor, keys = await redis.scan(cursor=cursor, match=pattern, count=200)
            for key in keys:
                fields = await redis.hgetall(key)
                if not fields:
                    continue
                parsed: dict[str, Any] = {}
                for k, v in fields.items():
                    try:
                        parsed[k] = json.loads(v)
                    except Exception:
                        parsed[k] = v
                last_seen = int(parsed.get("last_seen") or 0)
                if now - last_seen >= 60:
                    continue
                parsed.pop("websocket_id", None)
                result.append(parsed)
            if cursor == 0:
                break
        return result

    async def acquire_cell_lock(self, workspace_id: str, cell_id: str, user: User) -> tuple[bool, dict[str, Any]]:
        redis = await get_redis()
        lock_info = {
            "cell_id": cell_id,
            "workspace_id": workspace_id,
            "locked_by_user_id": user.id,
            "locked_by_name": user.full_name or user.email,
            "locked_at": int(time.time()),
        }
        acquired = await redis.set(self._lock_key(cell_id), json.dumps(lock_info), ex=30, nx=True)
        if acquired:
            await ws_manager.broadcast_to_workspace(
                workspace_id,
                {"type": "cell_locked", "data": lock_info},
            )
            return True, lock_info
        existing = await redis.get(self._lock_key(cell_id))
        try:
            existing_info = json.loads(existing) if existing else {}
        except Exception:
            existing_info = {}
        return False, existing_info

    async def release_cell_lock(self, workspace_id: str, cell_id: str, user_id: str) -> bool:
        redis = await get_redis()
        key = self._lock_key(cell_id)
        raw = await redis.get(key)
        if not raw:
            return False
        try:
            lock_info = json.loads(raw)
        except Exception:
            return False
        if lock_info.get("locked_by_user_id") != user_id:
            return False
        await redis.delete(key)
        await ws_manager.broadcast_to_workspace(
            workspace_id,
            {"type": "cell_unlocked", "data": {"cell_id": cell_id}},
        )
        return True

    async def refresh_cell_lock(self, cell_id: str, user_id: str) -> None:
        redis = await get_redis()
        key = self._lock_key(cell_id)
        raw = await redis.get(key)
        if not raw:
            return
        try:
            lock_info = json.loads(raw)
        except Exception:
            return
        if lock_info.get("locked_by_user_id") != user_id:
            return
        await redis.expire(key, 30)

    async def get_active_locks(self, workspace_id: str) -> list[dict[str, Any]]:
        redis = await get_redis()
        cursor = 0
        result: list[dict[str, Any]] = []
        while True:
            cursor, keys = await redis.scan(cursor=cursor, match=self._lock_pattern(), count=200)
            for key in keys:
                raw = await redis.get(key)
                if not raw:
                    continue
                try:
                    lock_info = json.loads(raw)
                except Exception:
                    continue
                if lock_info.get("workspace_id") == workspace_id:
                    result.append(lock_info)
            if cursor == 0:
                break
        return result

    async def _release_all_locks_for_user(self, workspace_id: str, user_id: str) -> None:
        redis = await get_redis()
        cursor = 0
        while True:
            cursor, keys = await redis.scan(cursor=cursor, match=self._lock_pattern(), count=200)
            for key in keys:
                raw = await redis.get(key)
                if not raw:
                    continue
                try:
                    lock_info = json.loads(raw)
                except Exception:
                    continue
                if (
                    lock_info.get("workspace_id") == workspace_id
                    and lock_info.get("locked_by_user_id") == user_id
                ):
                    await redis.delete(key)
                    await ws_manager.broadcast_to_workspace(
                        workspace_id,
                        {"type": "cell_unlocked", "data": {"cell_id": lock_info.get("cell_id")}},
                    )


presence_service = PresenceService()

