"""Dataset Pydantic schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.dataset import SourceType


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    source_type: SourceType = SourceType.csv
    # Connection config is encrypted before storage — accept raw dict from client
    connection_config: dict[str, Any] | None = None


class DatasetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    connection_config: dict[str, Any] | None = None


class SchemaColumn(BaseModel):
    name: str
    dtype: str
    nullable: bool = True
    sample_values: list[Any] | None = None


class SchemaTable(BaseModel):
    columns: list[SchemaColumn]
    row_count: int | None = None


class DatasetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    created_by: str | None
    name: str
    description: str | None
    source_type: str
    row_count: int | None
    column_count: int | None
    size_bytes: int | None
    storage_path: str | None
    version: int
    # Never expose raw connection_config (may contain passwords)
    has_connection_config: bool = False
    schema_snapshot: list | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_safe(cls, dataset) -> "DatasetRead":
        return cls(
            id=dataset.id,
            workspace_id=dataset.workspace_id,
            created_by=dataset.created_by,
            name=dataset.name,
            description=dataset.description,
            source_type=dataset.source_type,
            row_count=dataset.row_count,
            column_count=dataset.column_count,
            size_bytes=dataset.size_bytes,
            storage_path=dataset.storage_path,
            version=dataset.version,
            has_connection_config=bool(dataset.connection_config),
            schema_snapshot=dataset.schema_snapshot,
            created_at=dataset.created_at,
            updated_at=dataset.updated_at,
        )


class DatasetPreview(BaseModel):
    """First N rows of a dataset for quick inspection."""

    columns: list[str]
    rows: list[list[Any]]
    total_rows: int
    truncated: bool
