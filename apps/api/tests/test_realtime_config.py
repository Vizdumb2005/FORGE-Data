"""Security-focused tests for realtime server configuration."""

from app.config import settings
from app.core.realtime import sio


def test_realtime_cors_matches_settings() -> None:
    """Socket.IO CORS origins should match configured API CORS origins."""
    configured = sio.eio.cors_allowed_origins
    assert configured == settings.cors_origin_list
    assert configured != "*"

