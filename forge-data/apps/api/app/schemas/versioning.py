"""Pydantic schemas for data versioning and data quality endpoints."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ── Versioning schemas ────────────────────────────────────────────────────────


class VersionCreate(BaseModel):
    """Optional body fields for POST .../versions (file is multipart)."""

    message: str = Field(default="", max_length=500)


class VersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    dataset_id: str
    version_number: int
    message: str | None
    schema_snapshot: list[dict[str, Any]] | None
    row_count: int | None
    size_bytes: int | None
    parquet_path: str
    created_by: str | None
    created_at: datetime


class VersionDiff(BaseModel):
    v1: int
    v2: int
    row_count_v1: int
    row_count_v2: int
    row_delta: int
    added_columns: list[str]
    removed_columns: list[str]
    type_changes: list[dict[str, str]]
    stat_changes: list[dict[str, Any]]


# ── Data quality schemas ──────────────────────────────────────────────────────


class QualityRule(BaseModel):
    """A single quality rule definition."""

    type: str = Field(
        description="Rule type: not_null, unique, min_value, max_value, regex_match, accepted_values, row_count_gte"
    )
    column: str | None = Field(
        default=None, description="Target column (not needed for row_count_gte)"
    )
    threshold: float | None = Field(
        default=None, description="Numeric threshold for min/max/row_count rules"
    )
    pattern: str | None = Field(default=None, description="Regex pattern for regex_match rule")
    values: list[Any] | None = Field(
        default=None, description="Accepted values list for accepted_values rule"
    )


class QualityCheckRequest(BaseModel):
    """Body for POST .../quality/check."""

    rules: list[QualityRule] = Field(min_length=1)


class QualityCheckResult(BaseModel):
    rule_type: str
    column: str | None
    status: str  # "passed" | "failed"
    message: str
    failing_rows_sample: list[Any] = Field(default_factory=list)


class QualityReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    dataset_id: str
    version_number: int | None
    passed: int
    failed: int
    results: list[dict[str, Any]]
    ruleset_id: str | None
    created_by: str | None
    created_at: datetime


class RulesetSaveRequest(BaseModel):
    """Body for POST .../quality/ruleset."""

    name: str = Field(default="default", min_length=1, max_length=255)
    rules: list[QualityRule] = Field(min_length=1)


class RulesetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    dataset_id: str
    name: str
    rules: list[dict[str, Any]]
    created_by: str | None
    created_at: datetime
    updated_at: datetime
