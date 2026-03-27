"""Realtime collaboration manager using Socket.IO + Redis."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from http.cookies import SimpleCookie
from typing import Any

import socketio
from sqlalchemy import select

from app.core.redis import get_redis
from app.core.security import verify_token
from app.database import AsyncSessionLocal
from app.models.cell import Cell
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    logger=False,
)

COLORS = [
    "#00e5ff",
    "#ffb347",
    "#39ff8a",
    "#c084fc",
    "#ff4f6d",
    "#fbbf24",
    "#34d399",
    "#818cf8",
]


@dataclass
class SessionInfo:
    user_id: str
    user_name: str
    color: str
    workspace_id: str
    role: str


class RealtimeManager:
    """
    Manages realtime workspace collaboration.

    Redis keys:
      - forge:presence:{workspace_id} -> Hash { user_id: json payload }
      - forge:cell_lock:{cell_id} -> user_id (TTL 30s)
    """

    def __init__(self) -> None:
        self._session_by_sid: dict[str, SessionInfo] = {}
        self._sid_by_user_workspace: dict[tuple[str, str], str] = {}
        self._save_task_by_cell: dict[str, Any] = {}
        self._save_fn: Callable[[str, str, str, str], Awaitable[None]] = self._default_save_cell_content

    @staticmethod
    def room_name(workspace_id: str) -> str:
        return f"workspace_{workspace_id}"

    @staticmethod
    def _presence_key(workspace_id: str) -> str:
        return f"forge:presence:{workspace_id}"

    @staticmethod
    def _lock_key(cell_id: str) -> str:
        return f"forge:cell_lock:{cell_id}"

    @staticmethod
    def _color_for_user(user_id: str) -> str:
        digest = hashlib.sha256(user_id.encode()).hexdigest()
        idx = int(digest[:8], 16) % len(COLORS)
        return COLORS[idx]

    async def on_connect(self, sid: str, environ: dict[str, Any], auth: dict[str, Any] | None):
        if not auth:
            return False
        token = auth.get("token") or _extract_cookie_token(environ)
        workspace_id = auth.get("workspace_id")
        if not token or not workspace_id:
            return False

        payload = verify_token(token)
        if payload is None:
            return False
        user_id = payload.get("sub")
        if not user_id:
            return False

        async with AsyncSessionLocal() as db:
            workspace = await db.get(Workspace, workspace_id)
            if workspace is None:
                return False

            role = await self._resolve_workspace_role(db, workspace_id, user_id, workspace.owner_id)
            if role is None:
                return False

            user = await db.get(User, user_id)
            if user is None:
                return False

            info = SessionInfo(
                user_id=user_id,
                user_name=user.full_name or user.email,
                color=self._color_for_user(user_id),
                workspace_id=workspace_id,
                role=role,
            )
            self._session_by_sid[sid] = info
            self._sid_by_user_workspace[(user_id, workspace_id)] = sid

            await sio.enter_room(sid, self.room_name(workspace_id))
            await self._upsert_presence(info)
            await self._emit_presence(workspace_id)

        return True

    async def on_disconnect(self, sid: str):
        info = self._session_by_sid.pop(sid, None)
        if info is None:
            return

        self._sid_by_user_workspace.pop((info.user_id, info.workspace_id), None)
        redis = await get_redis()
        await redis.hdel(self._presence_key(info.workspace_id), info.user_id)
        await self._release_all_locks_for_user(info.user_id)
        await self._emit_presence(info.workspace_id)

    async def on_cursor_move(self, sid: str, data: dict[str, Any]):
        info = self._session_by_sid.get(sid)
        if info is None:
            return

        workspace_id = str(data.get("workspace_id") or info.workspace_id)
        cell_id = str(data.get("cell_id") or "")
        if not cell_id:
            return

        await self._upsert_presence(info, cursor_cell_id=cell_id)
        await sio.emit(
            "cursor_update",
            {"user_id": info.user_id, "user_name": info.user_name, "color": info.color, "cell_id": cell_id},
            room=self.room_name(workspace_id),
            skip_sid=sid,
        )

    async def on_cell_focus(self, sid: str, data: dict[str, Any]):
        info = self._session_by_sid.get(sid)
        if info is None:
            return
        if info.role not in {"editor", "admin"}:
            await sio.emit("cell_locked_by", {"error": "insufficient_role"}, to=sid)
            return

        workspace_id = str(data.get("workspace_id") or info.workspace_id)
        cell_id = str(data.get("cell_id") or "")
        if not cell_id:
            return

        redis = await get_redis()
        acquired = await redis.set(self._lock_key(cell_id), info.user_id, ex=30, nx=True)
        if acquired:
            await sio.emit(
                "cell_locked",
                {"cell_id": cell_id, "user_id": info.user_id, "user_name": info.user_name, "color": info.color},
                room=self.room_name(workspace_id),
            )
            return

        locker_id = await redis.get(self._lock_key(cell_id))
        if locker_id == info.user_id:
            await redis.expire(self._lock_key(cell_id), 30)
            await sio.emit(
                "cell_locked",
                {"cell_id": cell_id, "user_id": info.user_id, "user_name": info.user_name, "color": info.color},
                room=self.room_name(workspace_id),
            )
            return
        locker = await self._presence_user(workspace_id, locker_id) if locker_id else None
        await sio.emit(
            "cell_locked_by",
            {
                "cell_id": cell_id,
                "user_id": locker_id,
                "user_name": locker.get("name") if locker else None,
                "color": locker.get("color") if locker else None,
            },
            to=sid,
        )

    async def on_cell_blur(self, sid: str, data: dict[str, Any]):
        info = self._session_by_sid.get(sid)
        if info is None:
            return

        workspace_id = str(data.get("workspace_id") or info.workspace_id)
        cell_id = str(data.get("cell_id") or "")
        if not cell_id:
            return

        released = await self._release_lock_if_owner(cell_id, info.user_id)
        if released:
            await sio.emit("cell_unlocked", {"cell_id": cell_id}, room=self.room_name(workspace_id))

    async def on_cell_content_change(self, sid: str, data: dict[str, Any]):
        info = self._session_by_sid.get(sid)
        if info is None:
            return
        if info.role not in {"editor", "admin"}:
            return

        workspace_id = str(data.get("workspace_id") or info.workspace_id)
        cell_id = str(data.get("cell_id") or "")
        content = data.get("content")
        if not cell_id or not isinstance(content, str):
            return

        redis = await get_redis()
        lock_owner = await redis.get(self._lock_key(cell_id))
        if lock_owner != info.user_id:
            await sio.emit("cell_locked_by", {"cell_id": cell_id, "user_id": lock_owner}, to=sid)
            return

        await redis.expire(self._lock_key(cell_id), 30)
        await sio.emit(
            "cell_content_update",
            {"cell_id": cell_id, "content": content, "user_id": info.user_id},
            room=self.room_name(workspace_id),
            skip_sid=sid,
        )
        self._schedule_debounced_save(workspace_id, cell_id, info.user_id, content)

    async def broadcast_cell_executed(self, workspace_id: str, cell_id: str, output: dict):
        await sio.emit(
            "cell_executed",
            {"cell_id": cell_id, "output": output},
            room=self.room_name(workspace_id),
        )

    async def broadcast_to_workspace(self, workspace_id: str, event: str, payload: dict[str, Any]) -> None:
        await sio.emit(event, payload, room=self.room_name(workspace_id))

    def _schedule_debounced_save(self, workspace_id: str, cell_id: str, user_id: str, content: str) -> None:
        task = self._save_task_by_cell.get(cell_id)
        if task is not None and not task.done():
            task.cancel()

        async def _save_later():
            import asyncio

            await asyncio.sleep(0.5)
            await self._save_fn(workspace_id, cell_id, user_id, content)

        import asyncio

        self._save_task_by_cell[cell_id] = asyncio.create_task(_save_later())

    async def _default_save_cell_content(
        self,
        workspace_id: str,
        cell_id: str,
        user_id: str,
        content: str,
    ) -> None:
        async with AsyncSessionLocal() as db:
            role = await self._resolve_workspace_role(db, workspace_id, user_id)
            if role not in {"editor", "admin"}:
                return
            result = await db.execute(
                select(Cell).where(
                    Cell.id == cell_id,
                    Cell.workspace_id == workspace_id,
                )
            )
            cell = result.scalar_one_or_none()
            if cell is None:
                return
            cell.content = content
            await db.commit()

    async def _upsert_presence(self, info: SessionInfo, cursor_cell_id: str | None = None) -> None:
        redis = await get_redis()
        payload = {
            "user_id": info.user_id,
            "name": info.user_name,
            "color": info.color,
            "cursor_cell_id": cursor_cell_id,
            "last_seen": int(time.time()),
        }
        await redis.hset(self._presence_key(info.workspace_id), info.user_id, json.dumps(payload))

    async def _emit_presence(self, workspace_id: str) -> None:
        redis = await get_redis()
        raw = await redis.hgetall(self._presence_key(workspace_id))
        entries: list[dict[str, Any]] = []
        for value in raw.values():
            try:
                entries.append(json.loads(value))
            except Exception:
                continue
        await sio.emit("presence_update", {"workspace_id": workspace_id, "users": entries}, room=self.room_name(workspace_id))

    async def _presence_user(self, workspace_id: str, user_id: str | None) -> dict[str, Any] | None:
        if not user_id:
            return None
        redis = await get_redis()
        payload = await redis.hget(self._presence_key(workspace_id), user_id)
        if not payload:
            return None
        try:
            return json.loads(payload)
        except Exception:
            return None

    async def _release_lock_if_owner(self, cell_id: str, user_id: str) -> bool:
        redis = await get_redis()
        key = self._lock_key(cell_id)
        owner = await redis.get(key)
        if owner != user_id:
            return False
        await redis.delete(key)
        return True

    async def _release_all_locks_for_user(self, user_id: str) -> None:
        redis = await get_redis()
        cursor = 0
        while True:
            cursor, keys = await redis.scan(cursor=cursor, match="forge:cell_lock:*", count=200)
            for key in keys:
                owner = await redis.get(key)
                if owner == user_id:
                    await redis.delete(key)
            if cursor == 0:
                break

    @staticmethod
    async def _resolve_workspace_role(
        db,
        workspace_id: str,
        user_id: str,
        owner_id: str | None = None,
    ) -> str | None:
        if owner_id is None:
            ws = await db.get(Workspace, workspace_id)
            owner_id = ws.owner_id if ws else None
        if owner_id == user_id:
            return "admin"
        member_result = await db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )
        member = member_result.scalar_one_or_none()
        return member.role if member else None


realtime_manager = RealtimeManager()


@sio.event
async def connect(sid: str, environ: dict[str, Any], auth: dict[str, Any] | None):
    return await realtime_manager.on_connect(sid, environ, auth)


@sio.event
async def disconnect(sid: str):
    await realtime_manager.on_disconnect(sid)


@sio.on("cursor_move")
async def cursor_move(sid: str, data: dict[str, Any]):
    await realtime_manager.on_cursor_move(sid, data)


@sio.on("cell_focus")
async def cell_focus(sid: str, data: dict[str, Any]):
    await realtime_manager.on_cell_focus(sid, data)


@sio.on("cell_blur")
async def cell_blur(sid: str, data: dict[str, Any]):
    await realtime_manager.on_cell_blur(sid, data)


@sio.on("cell_content_change")
async def cell_content_change(sid: str, data: dict[str, Any]):
    await realtime_manager.on_cell_content_change(sid, data)


def _extract_cookie_token(environ: dict[str, Any]) -> str | None:
    cookie_header = environ.get("HTTP_COOKIE")
    if not cookie_header:
        return None
    cookie = SimpleCookie()
    cookie.load(cookie_header)
    token = cookie.get("forge_access_token")
    return token.value if token else None
