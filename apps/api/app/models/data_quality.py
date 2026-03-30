"""Data quality models — rulesets and quality check reports."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.dataset import Dataset
    from app.models.user import User


class DataQualityRuleset(Base):
    __tablename__ = "data_quality_rulesets"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    dataset_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="default")

    # List of rule dicts: [{"type": "not_null", "column": "age"}, ...]
    rules: Mapped[dict] = mapped_column(JSONB, nullable=False)

    created_by: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Relationships ──────────────────────────────────────────────────────
    dataset: Mapped[Dataset] = relationship("Dataset", back_populates="quality_rulesets")
    creator: Mapped[User] = relationship("User")

    def __repr__(self) -> str:
        return f"<DataQualityRuleset id={self.id!r} dataset={self.dataset_id!r}>"


class DataQualityReport(Base):
    __tablename__ = "data_quality_reports"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    dataset_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Number of checks that passed / failed
    passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Full results: [{rule, status, message, failing_rows_sample}, ...]
    results: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Optional link to the ruleset that was used
    ruleset_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("data_quality_rulesets.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_by: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── Relationships ──────────────────────────────────────────────────────
    dataset: Mapped[Dataset] = relationship("Dataset", back_populates="quality_reports")
    ruleset: Mapped[DataQualityRuleset | None] = relationship("DataQualityRuleset")
    creator: Mapped[User] = relationship("User")

    def __repr__(self) -> str:
        return f"<DataQualityReport id={self.id!r} " f"passed={self.passed} failed={self.failed}>"
