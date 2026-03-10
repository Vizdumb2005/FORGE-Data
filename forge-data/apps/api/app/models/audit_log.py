"""AuditLog ORM model — append-only record of every mutating API action."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # Nullable because some events may be unauthenticated (e.g. failed login)
    user_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Nullable — some events are not tied to a specific workspace
    workspace_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        nullable=True,
        index=True,
    )

    # e.g. "workspace.create", "dataset.delete", "auth.login"
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # e.g. "workspace", "dataset", "cell"
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # UUID of the affected resource
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # HTTP method + path, request body summary, diff, etc.
    metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Client IP extracted from X-Forwarded-For or request.client.host
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # ── Relationships ──────────────────────────────────────────────────────
    user: Mapped["User | None"] = relationship("User", back_populates="audit_logs")

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id!r} action={self.action!r} "
            f"user={self.user_id!r} ts={self.created_at!r}>"
        )
