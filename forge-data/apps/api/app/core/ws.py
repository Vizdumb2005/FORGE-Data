"""Workspace websocket broadcast helpers."""

from __future__ import annotations

from typing import Any

from app.core.realtime import realtime_manager


class WorkspaceWebSocketManager:
    async def broadcast_to_workspace(self, workspace_id: str, message: dict[str, Any]) -> None:
        event_type = str(message.get("type") or "").strip()
        if not event_type:
            return
        payload = message.get("data") or {}
        await realtime_manager.broadcast_to_workspace(workspace_id, event_type, payload)


ws_manager = WorkspaceWebSocketManager()

