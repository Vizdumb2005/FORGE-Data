from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class AuditLog(BaseModel):
    id: str
    action: str
    resource_type: str | None
    resource_id: str | None
    ip_address: str | None
    created_at: datetime
    meta: dict


@router.get("", response_model=list[AuditLog])
@router.get("/", include_in_schema=False)
async def list_audit_logs(limit: int = 100):
    return []
