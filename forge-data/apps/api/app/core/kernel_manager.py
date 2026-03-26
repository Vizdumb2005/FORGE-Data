"""KernelManager — manages Jupyter kernels via Kernel Gateway REST/WebSocket API.

Each workspace gets one shared kernel (created on first execution, evicted after
2 hours of inactivity).  Kernel IDs are cached in Redis with a TTL so that
restarts of the API process can reconnect to running kernels.
"""

import asyncio
import contextlib
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import websockets

from app.config import settings
from app.core.exceptions import JupyterUnavailableException
from app.core.forge_helpers import build_bootstrap_code
from app.core.security import create_kernel_token

logger = logging.getLogger(__name__)

_KERNEL_IDLE_TTL_SECONDS = 7200  # 2 hours
_EXECUTE_TIMEOUT_SECONDS = 120  # per-cell execution cap
_WS_RECV_TIMEOUT = 5  # seconds between WS message reads
_REDIS_KEY_PREFIX = "forge:kernel:"


@dataclass
class ExecutionResult:
    """Aggregated output from a single code execution."""

    outputs: list[dict[str, Any]] = field(default_factory=list)
    execution_count: int | None = None
    execution_time_ms: float = 0
    status: str = "ok"  # "ok" | "error"


class KernelManager:
    """Manages Jupyter kernels for workspace execution sessions."""

    def __init__(self) -> None:
        self._gateway = settings.jupyter_gateway_url.rstrip("/")
        self._token = settings.jupyter_token
        # In-memory cache: workspace_id → (kernel_id, last_used_timestamp)
        self._kernels: dict[str, tuple[str, float]] = {}

    # ── Public API ────────────────────────────────────────────────────────

    async def get_or_create_kernel(
        self,
        workspace_id: str,
        kernel_name: str = "python3",
    ) -> str:
        """Return an active kernel_id for *workspace_id*, creating one if needed."""
        # Check in-memory cache
        if workspace_id in self._kernels:
            kernel_id, _ = self._kernels[workspace_id]
            if await self._is_kernel_alive(kernel_id):
                self._kernels[workspace_id] = (kernel_id, time.time())
                return kernel_id
            # Dead kernel — remove from cache
            del self._kernels[workspace_id]

        # Check Redis (survives API restarts)
        kernel_id = await self._redis_get_kernel(workspace_id)
        if kernel_id and await self._is_kernel_alive(kernel_id):
            self._kernels[workspace_id] = (kernel_id, time.time())
            return kernel_id

        # Create new kernel
        kernel_id = await self._create_kernel(kernel_name)
        self._kernels[workspace_id] = (kernel_id, time.time())
        await self._redis_set_kernel(workspace_id, kernel_id)
        logger.info("Created kernel %s for workspace %s", kernel_id, workspace_id)
        return kernel_id

    async def execute_code(
        self,
        workspace_id: str,
        code: str,
        on_output: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> ExecutionResult:
        """Execute *code* in the workspace kernel and stream output via *on_output*."""
        kernel_id = await self.get_or_create_kernel(workspace_id)
        start = time.perf_counter()

        ws_url = self._ws_url(kernel_id)
        msg_id = str(uuid.uuid4())
        execute_msg = self._build_execute_request(msg_id, code)

        result = ExecutionResult()

        try:
            async with websockets.connect(ws_url, open_timeout=10) as ws:
                await ws.send(json.dumps(execute_msg))

                deadline = _EXECUTE_TIMEOUT_SECONDS
                while deadline > 0:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=_WS_RECV_TIMEOUT)
                    except TimeoutError:
                        deadline -= _WS_RECV_TIMEOUT
                        continue

                    msg = json.loads(raw)

                    # Only process messages for our request
                    if msg.get("parent_header", {}).get("msg_id") != msg_id:
                        continue

                    msg_type = msg.get("msg_type", "")
                    content = msg.get("content", {})
                    output_event = self._process_message(msg_type, content, result)

                    if output_event and on_output:
                        await on_output(output_event)

                    if msg_type == "execute_reply":
                        if content.get("status") == "error":
                            result.status = "error"
                        break

        except websockets.exceptions.WebSocketException as exc:
            logger.error("WebSocket error for kernel %s: %s", kernel_id, exc)
            raise JupyterUnavailableException() from exc
        except Exception as exc:
            logger.error("Kernel execution error: %s", exc)
            raise JupyterUnavailableException() from exc

        result.execution_time_ms = round((time.perf_counter() - start) * 1000, 1)
        # Update last-used timestamp
        self._kernels[workspace_id] = (kernel_id, time.time())
        return result

    async def inject_context(
        self,
        workspace_id: str,
    ) -> None:
        """Inject the FORGE bootstrap code into the workspace kernel."""
        # Use the internal API URL so the kernel (running inside Docker) calls
        # the API via the Docker network, not via the public-facing URL.
        api_base = settings.internal_api_url.rstrip("/")
        kernel_token = create_kernel_token(workspace_id)
        code = build_bootstrap_code(api_base, workspace_id, kernel_token)
        # Execute silently (don't stream output)
        await self.execute_code(workspace_id, code, on_output=None)

    async def interrupt_kernel(self, workspace_id: str) -> None:
        """Send interrupt (SIGINT) to the workspace kernel."""
        kernel_id = self._kernels.get(workspace_id, (None,))[0]
        if not kernel_id:
            return
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    f"{self._gateway}/api/kernels/{kernel_id}/interrupt",
                    headers=self._headers(),
                )
        except Exception as exc:
            logger.warning("Kernel interrupt failed: %s", exc)

    async def restart_kernel(self, workspace_id: str) -> None:
        """Restart the workspace kernel (preserves kernel_id, resets state)."""
        kernel_id = self._kernels.get(workspace_id, (None,))[0]
        if not kernel_id:
            return
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    f"{self._gateway}/api/kernels/{kernel_id}/restart",
                    headers=self._headers(),
                )
            # Re-inject context after restart
            logger.info("Restarted kernel %s for workspace %s", kernel_id, workspace_id)
        except Exception as exc:
            logger.warning("Kernel restart failed: %s", exc)

    async def shutdown_kernel(self, workspace_id: str) -> None:
        """Shut down the workspace kernel and remove from caches."""
        entry = self._kernels.pop(workspace_id, None)
        if not entry:
            return
        kernel_id = entry[0]
        await self._delete_kernel(kernel_id)
        await self._redis_del_kernel(workspace_id)
        logger.info("Shut down kernel %s for workspace %s", kernel_id, workspace_id)

    async def get_kernel_status(self, workspace_id: str) -> dict[str, Any]:
        """Return the status of the workspace kernel."""
        entry = self._kernels.get(workspace_id)
        if not entry:
            kernel_id = await self._redis_get_kernel(workspace_id)
            if kernel_id and await self._is_kernel_alive(kernel_id):
                self._kernels[workspace_id] = (kernel_id, time.time())
                entry = self._kernels[workspace_id]
            else:
                # Kernel has not been lazily created yet
                return {"status": "idle", "kernel_id": None}

        kernel_id = entry[0]
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(
                    f"{self._gateway}/api/kernels/{kernel_id}",
                    headers=self._headers(),
                )
                if r.status_code == 200:
                    data = r.json()
                    return {
                        "status": data.get("execution_state", "idle"),
                        "kernel_id": kernel_id,
                    }
        except Exception:
            pass
        return {"status": "dead", "kernel_id": kernel_id}

    async def cleanup_idle(self) -> int:
        """Shut down kernels idle for more than the TTL. Returns count cleaned."""
        now = time.time()
        to_remove = [
            wid
            for wid, (_, last_used) in self._kernels.items()
            if now - last_used > _KERNEL_IDLE_TTL_SECONDS
        ]
        for wid in to_remove:
            with contextlib.suppress(Exception):
                await self.shutdown_kernel(wid)
        if to_remove:
            logger.info("Cleaned up %d idle kernels", len(to_remove))
        return len(to_remove)

    async def shutdown_all(self) -> None:
        """Shut down all managed kernels (called during app shutdown)."""
        workspace_ids = list(self._kernels.keys())
        for wid in workspace_ids:
            with contextlib.suppress(Exception):
                await self.shutdown_kernel(wid)

    # ── Private helpers ───────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if self._token:
            h["Authorization"] = f"token {self._token}"
        return h

    def _ws_url(self, kernel_id: str) -> str:
        ws_base = self._gateway.replace("http://", "ws://").replace("https://", "wss://")
        url = f"{ws_base}/api/kernels/{kernel_id}/channels"
        if self._token:
            url += f"?token={self._token}"
        return url

    async def _is_kernel_alive(self, kernel_id: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(
                    f"{self._gateway}/api/kernels/{kernel_id}",
                    headers=self._headers(),
                )
                return r.status_code == 200
        except Exception:
            return False

    async def _create_kernel(self, kernel_name: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(
                    f"{self._gateway}/api/kernels",
                    json={"name": kernel_name},
                    headers=self._headers(),
                )
                r.raise_for_status()
                return r.json()["id"]
        except Exception as exc:
            raise JupyterUnavailableException() from exc

    async def _delete_kernel(self, kernel_id: str) -> None:
        with contextlib.suppress(Exception):
            async with httpx.AsyncClient(timeout=5) as client:
                await client.delete(
                    f"{self._gateway}/api/kernels/{kernel_id}",
                    headers=self._headers(),
                )

    @staticmethod
    def _build_execute_request(msg_id: str, code: str) -> dict[str, Any]:
        return {
            "header": {
                "msg_id": msg_id,
                "username": "forge",
                "session": str(uuid.uuid4()),
                "msg_type": "execute_request",
                "version": "5.3",
            },
            "parent_header": {},
            "metadata": {},
            "content": {
                "code": code,
                "silent": False,
                "store_history": True,
                "user_expressions": {},
                "allow_stdin": False,
            },
        }

    @staticmethod
    def _process_message(
        msg_type: str,
        content: dict[str, Any],
        result: ExecutionResult,
    ) -> dict[str, Any] | None:
        """Process a Jupyter wire protocol message into a structured output event."""
        if msg_type == "stream":
            event = {
                "type": "stream",
                "name": content.get("name", "stdout"),
                "text": content.get("text", ""),
            }
            result.outputs.append(event)
            return event

        if msg_type == "execute_result":
            result.execution_count = content.get("execution_count")
            data = content.get("data", {})
            event = {"type": "execute_result", "data": data}
            result.outputs.append(event)
            return event

        if msg_type == "display_data":
            data = content.get("data", {})
            event_type = "image" if "image/png" in data else "result"
            event = {"type": event_type, "data": data}
            result.outputs.append(event)
            return event

        if msg_type == "error":
            result.status = "error"
            event = {
                "type": "error",
                "ename": content.get("ename", "Error"),
                "evalue": content.get("evalue", ""),
                "traceback": content.get("traceback", []),
            }
            result.outputs.append(event)
            return event

        return None

    # ── Redis persistence (optional — graceful degradation) ───────────────

    @staticmethod
    async def _redis_get_kernel(workspace_id: str) -> str | None:
        try:
            from app.core.redis import get_redis

            r = await get_redis()
            return await r.get(f"{_REDIS_KEY_PREFIX}{workspace_id}")
        except Exception:
            return None

    @staticmethod
    async def _redis_set_kernel(workspace_id: str, kernel_id: str) -> None:
        try:
            from app.core.redis import get_redis

            r = await get_redis()
            await r.set(
                f"{_REDIS_KEY_PREFIX}{workspace_id}",
                kernel_id,
                ex=_KERNEL_IDLE_TTL_SECONDS,
            )
        except Exception:
            pass

    @staticmethod
    async def _redis_del_kernel(workspace_id: str) -> None:
        try:
            from app.core.redis import get_redis

            r = await get_redis()
            await r.delete(f"{_REDIS_KEY_PREFIX}{workspace_id}")
        except Exception:
            pass
