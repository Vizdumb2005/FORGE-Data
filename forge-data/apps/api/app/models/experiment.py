"""Experiment and ExperimentRun ORM models — mirrors MLflow experiment metadata locally."""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class RunStatus(str, Enum):
    running = "running"
    scheduled = "scheduled"
    finished = "finished"
    failed = "failed"
    killed = "killed"


class Experiment(Base):
    """Local mirror of an MLflow experiment record."""

    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # MLflow experiment ID (integer string) — null until synced
    mlflow_experiment_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_location: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    owner_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    tags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    owner: Mapped["User"] = relationship("User")
    runs: Mapped[list["ExperimentRun"]] = relationship(
        "ExperimentRun", back_populates="experiment", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Experiment id={self.id!r} name={self.name!r}>"


class ExperimentRun(Base):
    """Local mirror of an MLflow run."""

    __tablename__ = "experiment_runs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    experiment_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    mlflow_run_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )

    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=RunStatus.running.value, nullable=False)

    # Snapshot of key metrics/params at end of run
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Duration in seconds (populated at run end)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    experiment: Mapped["Experiment"] = relationship("Experiment", back_populates="runs")

    def __repr__(self) -> str:
        return f"<ExperimentRun id={self.id!r} status={self.status!r}>"
