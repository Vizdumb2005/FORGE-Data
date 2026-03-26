"""Pydantic schemas for Orion workflow APIs."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    is_active: bool = True
    schedule_cron: str | None = None
    schedule_timezone: str = "UTC"
    trigger_type: str = Field(
        default="manual",
        pattern="^(manual|schedule|dataset_event|webhook)$",
    )
    webhook_secret: str | None = None


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    is_active: bool | None = None
    schedule_cron: str | None = None
    schedule_timezone: str | None = None
    trigger_type: str | None = Field(
        default=None,
        pattern="^(manual|schedule|dataset_event|webhook)$",
    )
    webhook_secret: str | None = None


class WorkflowNodeCreate(BaseModel):
    node_type: str = Field(
        pattern=(
            "^(code_cell|sql_query|api_call|email_notify|dataset_upload|"
            "model_retrain|dashboard_publish|conditional|wait)$"
        )
    )
    label: str = Field(min_length=1, max_length=255)
    config: dict[str, Any] = Field(default_factory=dict)
    position_x: int = 0
    position_y: int = 0
    on_success_node_id: str | None = None
    on_failure_node_id: str | None = None
    retry_count: int = Field(default=0, ge=0, le=20)
    retry_delay_seconds: int = Field(default=60, ge=0, le=86400)
    timeout_seconds: int = Field(default=300, ge=1, le=86400)


class WorkflowNodeUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=255)
    config: dict[str, Any] | None = None
    position_x: int | None = None
    position_y: int | None = None
    on_success_node_id: str | None = None
    on_failure_node_id: str | None = None
    retry_count: int | None = Field(default=None, ge=0, le=20)
    retry_delay_seconds: int | None = Field(default=None, ge=0, le=86400)
    timeout_seconds: int | None = Field(default=None, ge=1, le=86400)


class WorkflowEdgeCreate(BaseModel):
    source_node_id: str
    target_node_id: str
    condition: str = Field(default="always", pattern="^(always|on_success|on_failure)$")


class WorkflowTriggerRequest(BaseModel):
    run_metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowTemplateInstantiateRequest(BaseModel):
    template_key: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    config_overrides: dict[str, Any] = Field(default_factory=dict)


class WorkflowNodeSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workflow_id: str
    node_type: str
    label: str
    config: dict[str, Any]
    position_x: int
    position_y: int
    on_success_node_id: str | None
    on_failure_node_id: str | None
    retry_count: int
    retry_delay_seconds: int
    timeout_seconds: int


class WorkflowEdgeSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workflow_id: str
    source_node_id: str
    target_node_id: str
    condition: str


class WorkflowNodeRunSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workflow_run_id: str
    node_id: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    output: dict[str, Any] | None
    logs: str | None
    error_message: str | None


class WorkflowRunSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workflow_id: str
    triggered_by: str
    triggered_by_user_id: str | None
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
    run_metadata: dict[str, Any]
    created_at: datetime


class WorkflowSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    name: str
    description: str | None
    is_active: bool
    schedule_cron: str | None
    schedule_timezone: str
    trigger_type: str
    webhook_secret: str | None
    created_by: str | None
    created_at: datetime
    updated_at: datetime


class WorkflowListItemSchema(WorkflowSchema):
    last_run_status: str | None = None
    run_count: int = 0


class WorkflowDetailSchema(WorkflowSchema):
    nodes: list[WorkflowNodeSchema]
    edges: list[WorkflowEdgeSchema]
    recent_runs: list[WorkflowRunSchema]


class WorkflowRunDetailSchema(WorkflowRunSchema):
    node_runs: list[WorkflowNodeRunSchema]
