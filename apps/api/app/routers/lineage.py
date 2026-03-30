"""Lineage router — workspace lineage DAG endpoints."""

from fastapi import APIRouter

from app.core.lineage_tracker import LineageTracker
from app.dependencies import CurrentUser, DBSession
from app.services import workspace_service

router = APIRouter()
_lineage_tracker = LineageTracker()


@router.get(
    "/workspaces/{workspace_id}/lineage",
    summary="Get workspace lineage graph",
)
async def get_workspace_lineage(
    workspace_id: str,
    current_user: CurrentUser,
    db: DBSession,
) -> dict:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    return await _lineage_tracker.get_workspace_lineage(db, workspace_id)

