"""Dataset ORM model."""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.data_quality import DataQualityReport, DataQualityRuleset
    from app.models.dataset_version import DatasetVersion
    from app.models.user import User
    from app.models.workspace import Workspace


class SourceType(str, Enum):
    csv = "csv"
    excel = "excel"
    postgres = "postgres"
    mysql = "mysql"
    snowflake = "snowflake"
    bigquery = "bigquery"
    s3 = "s3"
    api = "api"
    parquet = "parquet"
    json = "json"


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    workspace_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default=SourceType.csv.value
    )

    # Connection/file config — encrypted at application layer before storage
    connection_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Schema snapshot
    schema_snapshot: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Stats  (populated after ingestion)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    column_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Storage path in MinIO (for file-backed datasets)
    storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Profiling data (populated after ingestion / DuckDB registration)
    profile_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Versioning — incremented on each re-import
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

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
    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="datasets")
    creator: Mapped["User"] = relationship("User")
    versions: Mapped[list["DatasetVersion"]] = relationship(
        "DatasetVersion",
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="DatasetVersion.version_number",
    )
    quality_rulesets: Mapped[list["DataQualityRuleset"]] = relationship(
        "DataQualityRuleset",
        back_populates="dataset",
        cascade="all, delete-orphan",
    )
    quality_reports: Mapped[list["DataQualityReport"]] = relationship(
        "DataQualityReport",
        back_populates="dataset",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Dataset id={self.id!r} name={self.name!r} type={self.source_type!r}>"
