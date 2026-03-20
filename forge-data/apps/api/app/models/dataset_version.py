"""DatasetVersion model — tracks Parquet snapshots for Delta-style versioning."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.dataset import Dataset
    from app.models.user import User


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    dataset_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Schema at this version (list of {name, dtype, nullable, ...})
    schema_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # MinIO path: versions/{dataset_id}/v{n}.parquet
    parquet_path: Mapped[str] = mapped_column(String(1024), nullable=False)

    created_by: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── Relationships ──────────────────────────────────────────────────────
    dataset: Mapped[Dataset] = relationship("Dataset", back_populates="versions")
    creator: Mapped[User] = relationship("User")

    def __repr__(self) -> str:
        return f"<DatasetVersion dataset={self.dataset_id!r} " f"v{self.version_number}>"
