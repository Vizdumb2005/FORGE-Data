"""Workflow ORM models for Orion automation DAGs and run execution."""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.workspace import Workspace


class WorkflowTriggerType(str, Enum):
    manual = "manual"
    schedule = "schedule"
    dataset_event = "dataset_event"
    webhook = "webhook"


class WorkflowNodeType(str, Enum):
    code_cell = "code_cell"
    sql_query = "sql_query"
    api_call = "api_call"
    email_notify = "email_notify"
    dataset_upload = "dataset_upload"
    model_retrain = "model_retrain"
    dashboard_publish = "dashboard_publish"
    conditional = "conditional"
    wait = "wait"


class WorkflowEdgeCondition(str, Enum):
    always = "always"
    on_success = "on_success"
    on_failure = "on_failure"


class WorkflowRunTriggeredBy(str, Enum):
    manual = "manual"
    schedule = "schedule"
    webhook = "webhook"
    dataset_event = "dataset_event"


class WorkflowRunStatus(str, Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"
    cancelled = "cancelled"


class WorkflowNodeRunStatus(str, Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"
    skipped = "skipped"


class Workflow(Base):
    __tablename__ = "workflows"

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
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    schedule_cron: Mapped[str | None] = mapped_column(String(120), nullable=True)
    schedule_timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    trigger_type: Mapped[str] = mapped_column(
        String(32), default=WorkflowTriggerType.manual.value, nullable=False
    )
    webhook_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
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

    workspace: Mapped["Workspace"] = relationship("Workspace")
    creator: Mapped["User | None"] = relationship("User")
    nodes: Mapped[list["WorkflowNode"]] = relationship(
        "WorkflowNode",
        back_populates="workflow",
        cascade="all, delete-orphan",
    )
    edges: Mapped[list["WorkflowEdge"]] = relationship(
        "WorkflowEdge",
        back_populates="workflow",
        cascade="all, delete-orphan",
    )
    runs: Mapped[list["WorkflowRun"]] = relationship(
        "WorkflowRun",
        back_populates="workflow",
        cascade="all, delete-orphan",
    )


class WorkflowNode(Base):
    __tablename__ = "workflow_nodes"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    workflow_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_type: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    position_x: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    position_y: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    on_success_node_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("workflow_nodes.id", ondelete="SET NULL"),
        nullable=True,
    )
    on_failure_node_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("workflow_nodes.id", ondelete="SET NULL"),
        nullable=True,
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retry_delay_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)

    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="nodes")
    on_success_node: Mapped["WorkflowNode | None"] = relationship(
        "WorkflowNode",
        foreign_keys=[on_success_node_id],
        remote_side=[id],
    )
    on_failure_node: Mapped["WorkflowNode | None"] = relationship(
        "WorkflowNode",
        foreign_keys=[on_failure_node_id],
        remote_side=[id],
    )


class WorkflowEdge(Base):
    __tablename__ = "workflow_edges"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    workflow_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_node_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("workflow_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_node_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("workflow_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    condition: Mapped[str] = mapped_column(
        String(32), default=WorkflowEdgeCondition.always.value, nullable=False
    )

    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="edges")
    source_node: Mapped["WorkflowNode"] = relationship("WorkflowNode", foreign_keys=[source_node_id])
    target_node: Mapped["WorkflowNode"] = relationship("WorkflowNode", foreign_keys=[target_node_id])


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    workflow_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    triggered_by: Mapped[str] = mapped_column(String(32), nullable=False)
    triggered_by_user_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32), default=WorkflowRunStatus.pending.value, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="runs")
    triggered_by_user: Mapped["User | None"] = relationship("User")
    node_runs: Mapped[list["WorkflowNodeRun"]] = relationship(
        "WorkflowNodeRun",
        back_populates="workflow_run",
        cascade="all, delete-orphan",
    )


class WorkflowNodeRun(Base):
    __tablename__ = "workflow_node_runs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    workflow_run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("workflow_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32), default=WorkflowNodeRunStatus.pending.value, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    logs: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    workflow_run: Mapped["WorkflowRun"] = relationship("WorkflowRun", back_populates="node_runs")
    node: Mapped["WorkflowNode"] = relationship("WorkflowNode")
