"""Realtime collaboration manager using Socket.IO + Redis-backed services."""

from __future__ import annotations

from dataclasses import dataclass
from http.cookies import SimpleCookie
from typing import Any

import socketio
from sqlalchemy import select

from app.config import settings
from app.core.security import verify_token
from app.database import AsyncSessionLocal
from app.models.user import User
from app.services.chat_service import chat_service
from app.services.presence_service import presence_service
from app.services.workspace_service import check_workspace_role

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=settings.cors_origin_list,
    logger=False,
)


@dataclass
class SessionInfo:
    user_id: str
    user_name: str
    workspace_id: str


class RealtimeManager:
    def __init__(self) -> None:
        self._session_by_sid: dict[str, SessionInfo] = {}

    @staticmethod
    def room_name(workspace_id: str) -> str:
        return f"workspace_{workspace_id}"

    async def on_connect(self, sid: str, environ: dict[str, Any], auth: dict[str, Any] | None):
        token = (auth or {}).get("token") or _extract_cookie_token(environ)
        workspace_id = str((auth or {}).get("workspace_id") or "")
        if not token or not workspace_id:
            return False
        payload = verify_token(token)
        user_id = str(payload.get("sub")) if payload else ""
        if not user_id:
            return False

        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            if user is None:
                return False
            try:
                await check_workspace_role(db, workspace_id, user_id, ("viewer", "analyst", "editor", "admin"))
            except Exception:
                return False

            self._session_by_sid[sid] = SessionInfo(
                user_id=user.id,
                user_name=user.full_name or user.email,
                workspace_id=workspace_id,
            )
            await sio.enter_room(sid, self.room_name(workspace_id))

            presence = await presence_service.join_workspace(workspace_id, user, sid)
            recent = await chat_service.get_messages(db, workspace_id, limit=50)
            active_locks = await presence_service.get_active_locks(workspace_id)
            await sio.emit(
                "workspace_state",
                {
                    "presence": presence,
                    "recent_messages": [chat_service.serialize_message(m) for m in recent],
                    "active_locks": active_locks,
                },
                to=sid,
            )
            await db.commit()
        return True

    async def on_disconnect(self, sid: str) -> None:
        info = self._session_by_sid.pop(sid, None)
        if info is None:
            return
        await presence_service.leave_workspace(info.workspace_id, info.user_id)

    async def on_cursor_update(self, sid: str, data: dict[str, Any]) -> None:
        info = self._session_by_sid.get(sid)
        if info is None:
            return
        await presence_service.update_cursor(
            workspace_id=info.workspace_id,
            user_id=info.user_id,
            x=float(data.get("cursor_x") or 0),
            y=float(data.get("cursor_y") or 0),
            cell_id=data.get("active_cell_id"),
        )

    async def on_request_lock(self, sid: str, data: dict[str, Any]) -> None:
        info = self._session_by_sid.get(sid)
        if info is None:
            return
        cell_id = str(data.get("cell_id") or "")
        if not cell_id:
            return
        async with AsyncSessionLocal() as db:
            user = await db.get(User, info.user_id)
            if user is None:
                return
            acquired, lock_info = await presence_service.acquire_cell_lock(info.workspace_id, cell_id, user)
            await sio.emit(
                "lock_result",
                {"type": "lock_result", "acquired": acquired, "lock_info": lock_info},
                to=sid,
            )

    async def on_release_lock(self, sid: str, data: dict[str, Any]) -> None:
        info = self._session_by_sid.get(sid)
        if info is None:
            return
        cell_id = str(data.get("cell_id") or "")
        if not cell_id:
            return
        await presence_service.release_cell_lock(info.workspace_id, cell_id, info.user_id)

    async def on_refresh_lock(self, sid: str, data: dict[str, Any]) -> None:
        info = self._session_by_sid.get(sid)
        if info is None:
            return
        cell_id = str(data.get("cell_id") or "")
        if not cell_id:
            return
        await presence_service.refresh_cell_lock(cell_id, info.user_id)

    async def on_chat_message(self, sid: str, data: dict[str, Any]) -> None:
        info = self._session_by_sid.get(sid)
        if info is None:
            return
        async with AsyncSessionLocal() as db:
            user = await db.get(User, info.user_id)
            if user is None:
                return
            await chat_service.send_message(
                db,
                info.workspace_id,
                user,
                content=str(data.get("content") or ""),
                content_type=str(data.get("content_type") or "text"),
                metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
            )
            await db.commit()

    async def on_typing_state(self, sid: str, data: dict[str, Any], is_typing: bool) -> None:
        info = self._session_by_sid.get(sid)
        if info is None:
            return
        await sio.emit(
            "user_typing",
            {
                "user_id": info.user_id,
                "full_name": info.user_name,
                "context": data.get("context"),
                "is_typing": is_typing,
            },
            room=self.room_name(info.workspace_id),
            skip_sid=sid,
        )

    async def broadcast_cell_executed(self, workspace_id: str, cell_id: str, output: dict):
        await sio.emit(
            "cell_executed",
            {"cell_id": cell_id, "output": output},
            room=self.room_name(workspace_id),
        )

    async def broadcast_to_workspace(self, workspace_id: str, event: str, payload: dict[str, Any]) -> None:
        await sio.emit(event, payload, room=self.room_name(workspace_id))


realtime_manager = RealtimeManager()


@sio.event
async def connect(sid: str, environ: dict[str, Any], auth: dict[str, Any] | None):
    return await realtime_manager.on_connect(sid, environ, auth)


@sio.event
async def disconnect(sid: str):
    await realtime_manager.on_disconnect(sid)


@sio.on("cursor_update")
async def cursor_update(sid: str, data: dict[str, Any]):
    await realtime_manager.on_cursor_update(sid, data)


@sio.on("request_lock")
async def request_lock(sid: str, data: dict[str, Any]):
    await realtime_manager.on_request_lock(sid, data)


@sio.on("release_lock")
async def release_lock(sid: str, data: dict[str, Any]):
    await realtime_manager.on_release_lock(sid, data)


@sio.on("refresh_lock")
async def refresh_lock(sid: str, data: dict[str, Any]):
    await realtime_manager.on_refresh_lock(sid, data)


@sio.on("chat_message")
async def chat_message(sid: str, data: dict[str, Any]):
    await realtime_manager.on_chat_message(sid, data)


@sio.on("typing_start")
async def typing_start(sid: str, data: dict[str, Any]):
    await realtime_manager.on_typing_state(sid, data, True)


@sio.on("typing_stop")
async def typing_stop(sid: str, data: dict[str, Any]):
    await realtime_manager.on_typing_state(sid, data, False)


# Backward compatibility handlers
@sio.on("cursor_move")
async def cursor_move(sid: str, data: dict[str, Any]):
    await realtime_manager.on_cursor_update(
        sid,
        {
            "cursor_x": data.get("cursor_x") or 0,
            "cursor_y": data.get("cursor_y") or 0,
            "active_cell_id": data.get("cell_id"),
        },
    )


@sio.on("cell_focus")
async def cell_focus(sid: str, data: dict[str, Any]):
    await realtime_manager.on_request_lock(sid, {"cell_id": data.get("cell_id")})


@sio.on("cell_blur")
async def cell_blur(sid: str, data: dict[str, Any]):
    await realtime_manager.on_release_lock(sid, {"cell_id": data.get("cell_id")})


@sio.on("cell_content_change")
async def cell_content_change(sid: str, data: dict[str, Any]):
    await realtime_manager.on_refresh_lock(sid, {"cell_id": data.get("cell_id")})


def _extract_cookie_token(environ: dict[str, Any]) -> str | None:
    cookie_header = environ.get("HTTP_COOKIE")
    if not cookie_header:
        return None
    cookie = SimpleCookie()
    cookie.load(cookie_header)
    token = cookie.get("forge_access_token")
    return token.value if token else None
