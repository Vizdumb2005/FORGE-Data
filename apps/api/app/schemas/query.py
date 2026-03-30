"""Query and connector Pydantic schemas."""

from typing import Any

from pydantic import BaseModel, Field

from app.models.dataset import SourceType
from app.schemas.dataset import DatasetRead

# ── Connection config (client → server) ──────────────────────────────────────


class ConnectionConfigInput(BaseModel):
    """Polymorphic connection configuration accepted from the client."""

    # SQL databases (Postgres / MySQL)
    host: str | None = None
    port: int | None = None
    database: str | None = None
    username: str | None = None
    password: str | None = None
    schema_name: str | None = Field(default=None, description="DB schema (e.g. 'public')")

    # Snowflake
    account: str | None = None
    warehouse: str | None = None

    # S3 / MinIO
    bucket: str | None = None
    prefix: str | None = None
    aws_access_key: str | None = None
    aws_secret_key: str | None = None
    region: str | None = None
    file_format: str | None = Field(default=None, description="parquet or csv")
    endpoint_url: str | None = Field(
        default=None, description="S3-compatible endpoint (e.g. MinIO)"
    )

    # Snowflake table to pull
    table: str | None = None


# ── Requests ─────────────────────────────────────────────────────────────────


class DatasetConnectRequest(BaseModel):
    """Body for POST /workspaces/{workspace_id}/datasets/connect."""

    name: str = Field(min_length=1, max_length=255)
    source_type: SourceType
    connection_config: ConnectionConfigInput


class QueryRequest(BaseModel):
    """Body for POST /workspaces/{workspace_id}/query."""

    sql: str = Field(min_length=1, max_length=50000)
    dataset_ids: list[str] | None = None


# ── Responses ────────────────────────────────────────────────────────────────


class QueryResult(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    execution_time_ms: float


class QueryErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    line: int | None = None
    column: int | None = None
    execution_time_ms: float | None = None


class ColumnProfile(BaseModel):
    name: str
    dtype: str
    distinct_count: int
    null_count: int
    min: Any | None = None
    max: Any | None = None
    avg: float | None = None
    sample_values: list[Any] | None = None


class DatasetProfile(BaseModel):
    row_count: int
    column_count: int
    columns: list[ColumnProfile]


class DatasetWithProfile(BaseModel):
    dataset: DatasetRead
    profile: DatasetProfile


class DatasetWithSchema(BaseModel):
    dataset: DatasetRead
    schema_info: list[dict[str, Any]]
