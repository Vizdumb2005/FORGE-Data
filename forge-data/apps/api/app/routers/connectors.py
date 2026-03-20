"""Connectors router — test connectivity, introspect schema, upload, connect, query, versioning, quality."""

import contextlib
import json
import logging
import tempfile
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.core.data_quality import DataQualityEngine
from app.core.data_versioning import DataVersionManager
from app.core.exceptions import ServiceUnavailableException
from app.core.query_engine import QueryError
from app.core.security import encrypt_field
from app.dependencies import CurrentUser, DBSession, QueryEngine
from app.models.dataset import Dataset, SourceType
from app.schemas.dataset import DatasetRead
from app.schemas.query import (
    DatasetConnectRequest,
    DatasetProfile,
    DatasetWithProfile,
    DatasetWithSchema,
    QueryErrorResponse,
    QueryRequest,
    QueryResult,
)
from app.schemas.versioning import (
    QualityCheckRequest,
    QualityReportRead,
    RulesetRead,
    RulesetSaveRequest,
    VersionDiff,
    VersionRead,
)
from app.services import audit_service, dataset_service, workspace_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level singletons (stateless — safe to share)
_version_manager = DataVersionManager()
_quality_engine = DataQualityEngine()


# ═════════════════════════════════════════════════════════════════════════════
# Existing endpoints — connectivity testing and schema introspection
# ═════════════════════════════════════════════════════════════════════════════


class ConnectionConfig(BaseModel):
    type: Literal["postgres", "mysql", "snowflake", "bigquery", "rest", "s3"]
    host: str | None = None
    port: int | None = None
    database: str | None = None
    username: str | None = None
    password: str | None = None
    # Snowflake / BigQuery specific
    account: str | None = None
    project_id: str | None = None
    credentials_json: dict | None = None
    # S3 / MinIO
    endpoint_url: str | None = None
    bucket: str | None = None
    access_key: str | None = None
    secret_key: str | None = None
    # REST API
    url: str | None = None
    headers: dict[str, str] | None = None


class TestConnectionResponse(BaseModel):
    success: bool
    message: str
    latency_ms: float | None = None


class ColumnInfo(BaseModel):
    name: str
    dtype: str
    nullable: bool


class TableInfo(BaseModel):
    schema_name: str | None
    name: str
    columns: list[ColumnInfo]


@router.post("/test", response_model=TestConnectionResponse, summary="Test a connection config")
async def test_connection(
    config: ConnectionConfig,
    current_user: CurrentUser,
) -> TestConnectionResponse:
    """
    Attempt to connect to the data source and return success/failure + latency.
    Credentials are used in-request only — never persisted at this endpoint.
    """
    import time

    start = time.perf_counter()
    if config.type in ("postgres", "mysql"):
        result = await _test_sql_connection(config)
    elif config.type == "rest":
        result = await _test_rest_connection(config)
    elif config.type == "s3":
        result = await _test_s3_connection(config)
    else:
        result = (False, f"Connector type '{config.type}' test not yet implemented")

    latency_ms = (time.perf_counter() - start) * 1000
    return TestConnectionResponse(
        success=result[0],
        message=result[1],
        latency_ms=round(latency_ms, 1),
    )


@router.post(
    "/schema",
    response_model=list[TableInfo],
    summary="Introspect schema for a connection",
)
async def get_schema(
    config: ConnectionConfig,
    current_user: CurrentUser,
) -> list[TableInfo]:
    """Return the list of tables and their columns for the given connection."""
    if config.type == "postgres":
        return await _introspect_postgres(config)
    if config.type == "mysql":
        return await _introspect_mysql(config)
    return []


# ═════════════════════════════════════════════════════════════════════════════
# New endpoints — DuckDB-powered upload, connect, query, list, get, delete
# ═════════════════════════════════════════════════════════════════════════════


@router.post(
    "/workspaces/{workspace_id}/datasets/upload",
    response_model=DatasetWithProfile,
    status_code=201,
    summary="Upload a file and register it in the query engine",
)
async def upload_dataset(
    workspace_id: str,
    file: UploadFile,
    current_user: CurrentUser,
    db: DBSession,
    engine: QueryEngine,
    request: Request,
) -> DatasetWithProfile:
    """
    Accept multipart file upload (CSV, Excel, Parquet, JSON).
    Saves to MinIO, registers in DuckDB, profiles the data, and returns both.
    """
    await workspace_service.get_workspace(db, workspace_id, current_user.id)

    filename = file.filename or "upload.csv"
    contents = await file.read()

    # Determine source type from extension
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "csv"
    source_type_map = {
        "csv": SourceType.csv,
        "parquet": SourceType.parquet,
        "xlsx": SourceType.excel,
        "xls": SourceType.excel,
        "json": SourceType.json,
    }
    source_type = source_type_map.get(ext, SourceType.csv)
    dataset_name = filename.rsplit(".", 1)[0] if "." in filename else filename

    # Create Dataset record
    from app.schemas.dataset import DatasetCreate

    dataset = await dataset_service.create_dataset(
        db,
        workspace_id,
        DatasetCreate(name=dataset_name, source_type=source_type),
        current_user.id,
    )

    # Ingest file (uploads to MinIO, extracts schema + stats)
    dataset = await dataset_service.ingest_file(db, workspace_id, dataset.id, contents, filename)

    # Register in DuckDB — write contents to a temp file so DuckDB can read it
    tmp_path = await _write_temp_file(contents, filename)
    try:
        read_type = "parquet" if ext == "parquet" else "csv"
        await engine.register_source(
            current_user.id,
            dataset_name,
            {"type": read_type, "file_path": tmp_path},
        )

        # Profile the dataset via DuckDB
        profile_data = await engine.profile_dataset(current_user.id, dataset_name)
    except Exception as exc:
        logger.warning("DuckDB registration/profiling failed: %s", exc)
        profile_data = {
            "row_count": dataset.row_count or 0,
            "column_count": dataset.column_count or 0,
            "columns": [],
        }
    finally:
        # Clean up the temp file — DuckDB has already loaded the data into memory
        import os

        with contextlib.suppress(OSError):
            os.unlink(tmp_path)

    # Store profile on the dataset record
    dataset = await dataset_service.update_profile(db, workspace_id, dataset.id, profile_data)

    await audit_service.log_event(
        db,
        action=audit_service.AuditAction.DATASET_UPLOAD,
        user_id=current_user.id,
        workspace_id=workspace_id,
        resource_type="dataset",
        resource_id=dataset.id,
        ip_address=request.client.host if request.client else None,
        metadata={"filename": filename, "size_bytes": len(contents)},
    )

    return DatasetWithProfile(
        dataset=DatasetRead.from_orm_safe(dataset),
        profile=DatasetProfile(**profile_data),
    )


@router.post(
    "/workspaces/{workspace_id}/datasets/connect",
    response_model=DatasetWithSchema,
    status_code=201,
    summary="Connect an external data source",
)
async def connect_dataset(
    workspace_id: str,
    payload: DatasetConnectRequest,
    current_user: CurrentUser,
    db: DBSession,
    engine: QueryEngine,
    request: Request,
) -> DatasetWithSchema:
    """
    Register an external database (Postgres, MySQL, Snowflake, S3) as a dataset.
    Encrypts connection config, registers in DuckDB, and fetches schema.
    """
    await workspace_service.get_workspace(db, workspace_id, current_user.id)

    config_dict = payload.connection_config.model_dump(exclude_none=True)

    # Build DuckDB-specific config
    duckdb_config = _build_duckdb_config(payload.source_type, config_dict)

    # Create Dataset record with encrypted connection config
    encrypted_config = {"__encrypted__": encrypt_field(json.dumps(config_dict))}
    dataset = Dataset(
        workspace_id=workspace_id,
        created_by=current_user.id,
        name=payload.name,
        source_type=payload.source_type.value,
        connection_config=encrypted_config,
    )
    db.add(dataset)
    await db.flush()

    # Register in DuckDB and fetch schema
    schema_info: list[dict[str, Any]] = []
    try:
        registration = await engine.register_source(current_user.id, payload.name, duckdb_config)
        schema_info = registration.get("columns", [])
        dataset.schema_snapshot = schema_info
        dataset.row_count = registration.get("row_count")
        dataset.column_count = len(schema_info)
        await db.flush()
    except Exception as exc:
        logger.warning("DuckDB source registration failed: %s", exc)

    await audit_service.log_event(
        db,
        action=audit_service.AuditAction.DATASET_CONNECT,
        user_id=current_user.id,
        workspace_id=workspace_id,
        resource_type="dataset",
        resource_id=dataset.id,
        ip_address=request.client.host if request.client else None,
        metadata={"source_type": payload.source_type.value, "name": payload.name},
    )

    return DatasetWithSchema(
        dataset=DatasetRead.from_orm_safe(dataset),
        schema_info=schema_info,
    )


@router.get(
    "/workspaces/{workspace_id}/datasets",
    response_model=list[DatasetRead],
    summary="List datasets in a workspace (with profile summary)",
)
async def list_datasets(
    workspace_id: str,
    current_user: CurrentUser,
    db: DBSession,
) -> list[DatasetRead]:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    datasets = await dataset_service.list_datasets(db, workspace_id)
    return [DatasetRead.from_orm_safe(d) for d in datasets]


@router.get(
    "/workspaces/{workspace_id}/datasets/{dataset_id}",
    response_model=DatasetRead,
    summary="Get a dataset with full schema and profile",
)
async def get_dataset(
    workspace_id: str,
    dataset_id: str,
    current_user: CurrentUser,
    db: DBSession,
) -> DatasetRead:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    dataset = await dataset_service.get_dataset(db, workspace_id, dataset_id)
    return DatasetRead.from_orm_safe(dataset)


@router.post(
    "/workspaces/{workspace_id}/query",
    summary="Execute SQL against registered datasets",
)
async def execute_query(
    workspace_id: str,
    payload: QueryRequest,
    current_user: CurrentUser,
    db: DBSession,
    engine: QueryEngine,
    request: Request,
):
    """
    Execute a SQL query against the user's DuckDB connection.
    All datasets previously registered (via upload or connect) are available.
    Returns JSON for small results, streaming NDJSON for large results.
    """
    await workspace_service.get_workspace(db, workspace_id, current_user.id)

    try:
        query_result = await engine.execute_query(current_user.id, payload.sql)
    except QueryError as exc:
        await audit_service.log_event(
            db,
            action=audit_service.AuditAction.QUERY_EXECUTE,
            user_id=current_user.id,
            workspace_id=workspace_id,
            resource_type="query",
            ip_address=request.client.host if request.client else None,
            metadata={"sql": payload.sql[:500], "error": exc.error},
        )
        return QueryErrorResponse(
            error=exc.error,
            line=exc.line,
            column=exc.column,
            execution_time_ms=exc.execution_time_ms,
        )

    await audit_service.log_event(
        db,
        action=audit_service.AuditAction.QUERY_EXECUTE,
        user_id=current_user.id,
        workspace_id=workspace_id,
        resource_type="query",
        ip_address=request.client.host if request.client else None,
        metadata={
            "sql": payload.sql[:500],
            "row_count": query_result["row_count"],
            "execution_time_ms": query_result["execution_time_ms"],
        },
    )

    # Stream large results as NDJSON
    if query_result["row_count"] > 5000:
        return StreamingResponse(
            _stream_ndjson(query_result),
            media_type="application/x-ndjson",
            headers={
                "X-Row-Count": str(query_result["row_count"]),
                "X-Execution-Time-Ms": str(query_result["execution_time_ms"]),
            },
        )

    return QueryResult(**query_result)


@router.delete(
    "/workspaces/{workspace_id}/datasets/{dataset_id}",
    status_code=204,
    summary="Delete a dataset and clean up resources",
)
async def delete_dataset(
    workspace_id: str,
    dataset_id: str,
    current_user: CurrentUser,
    db: DBSession,
    engine: QueryEngine,
    request: Request,
) -> None:
    """Remove dataset from DB, unregister from DuckDB, and delete from MinIO if file-backed."""
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    dataset = await dataset_service.get_dataset(db, workspace_id, dataset_id)

    # Unregister from DuckDB (best-effort)
    with contextlib.suppress(Exception):
        await engine.unregister_source(current_user.id, dataset.name)

    # Delete file from MinIO if it's a file-backed dataset
    if dataset.storage_path:
        try:
            await _delete_from_minio(dataset.storage_path)
        except Exception as exc:
            logger.warning("MinIO delete failed for %s: %s", dataset.storage_path, exc)

    await dataset_service.delete_dataset(db, workspace_id, dataset_id)

    await audit_service.log_event(
        db,
        action=audit_service.AuditAction.DATASET_DELETE,
        user_id=current_user.id,
        workspace_id=workspace_id,
        resource_type="dataset",
        resource_id=dataset_id,
        ip_address=request.client.host if request.client else None,
    )


# ═════════════════════════════════════════════════════════════════════════════
# Versioning endpoints — Delta-style Parquet snapshots
# ═════════════════════════════════════════════════════════════════════════════


@router.post(
    "/workspaces/{workspace_id}/datasets/{dataset_id}/versions",
    response_model=VersionRead,
    status_code=201,
    summary="Upload a new version of a dataset",
)
async def create_version(
    workspace_id: str,
    dataset_id: str,
    file: UploadFile,
    current_user: CurrentUser,
    db: DBSession,
    message: str = "",
) -> VersionRead:
    """Upload a new file version for an existing dataset (Delta-style append)."""
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    contents = await file.read()
    filename = file.filename or "version.csv"

    version = await _version_manager.create_version(
        db=db,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        file_bytes=contents,
        filename=filename,
        user_id=current_user.id,
        message=message,
    )
    return VersionRead.model_validate(version)


@router.get(
    "/workspaces/{workspace_id}/datasets/{dataset_id}/versions",
    response_model=list[VersionRead],
    summary="List all versions of a dataset",
)
async def list_versions(
    workspace_id: str,
    dataset_id: str,
    current_user: CurrentUser,
    db: DBSession,
) -> list[VersionRead]:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    versions = await _version_manager.list_versions(db, workspace_id, dataset_id)
    return [VersionRead.model_validate(v) for v in versions]


@router.get(
    "/workspaces/{workspace_id}/datasets/{dataset_id}/versions/diff",
    response_model=VersionDiff,
    summary="Diff two versions of a dataset",
)
async def diff_versions(
    workspace_id: str,
    dataset_id: str,
    current_user: CurrentUser,
    db: DBSession,
    v1: int = Query(..., description="First version number"),
    v2: int = Query(..., description="Second version number"),
) -> VersionDiff:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    diff = await _version_manager.diff_versions(db, workspace_id, dataset_id, v1, v2)
    return VersionDiff(**diff)


@router.post(
    "/workspaces/{workspace_id}/datasets/{dataset_id}/versions/{version_number}/rollback",
    response_model=VersionRead,
    summary="Rollback to a previous version",
)
async def rollback_version(
    workspace_id: str,
    dataset_id: str,
    version_number: int,
    current_user: CurrentUser,
    db: DBSession,
) -> VersionRead:
    """Roll back by creating a NEW version from the target version's snapshot."""
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    version = await _version_manager.rollback(
        db=db,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        target_version=version_number,
        user_id=current_user.id,
    )
    return VersionRead.model_validate(version)


# ═════════════════════════════════════════════════════════════════════════════
# Data quality endpoints — rule-based validation
# ═════════════════════════════════════════════════════════════════════════════


@router.post(
    "/workspaces/{workspace_id}/datasets/{dataset_id}/quality/check",
    response_model=QualityReportRead,
    status_code=201,
    summary="Run data quality checks on a dataset",
)
async def run_quality_check(
    workspace_id: str,
    dataset_id: str,
    payload: QualityCheckRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> QualityReportRead:
    """Run quality rules against the latest version of the dataset."""
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    rules_dicts = [r.model_dump(exclude_none=True) for r in payload.rules]
    report = await _quality_engine.run_checks(
        db=db,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        user_id=current_user.id,
        rules=rules_dicts,
    )
    return QualityReportRead.model_validate(report)


@router.post(
    "/workspaces/{workspace_id}/datasets/{dataset_id}/quality/ruleset",
    response_model=RulesetRead,
    status_code=201,
    summary="Save a quality ruleset for a dataset",
)
async def save_ruleset(
    workspace_id: str,
    dataset_id: str,
    payload: RulesetSaveRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> RulesetRead:
    """Save or update a named ruleset. Runs automatically on new versions."""
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    rules_dicts = [r.model_dump(exclude_none=True) for r in payload.rules]
    ruleset = await _quality_engine.save_ruleset(
        db=db,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        user_id=current_user.id,
        name=payload.name,
        rules=rules_dicts,
    )
    return RulesetRead.model_validate(ruleset)


@router.get(
    "/workspaces/{workspace_id}/datasets/{dataset_id}/quality/reports",
    response_model=list[QualityReportRead],
    summary="Get quality report history for a dataset",
)
async def get_quality_reports(
    workspace_id: str,
    dataset_id: str,
    current_user: CurrentUser,
    db: DBSession,
) -> list[QualityReportRead]:
    """Return the last 20 quality reports for a dataset."""
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    reports = await _quality_engine.get_report_history(
        db=db,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
    )
    return [QualityReportRead.model_validate(r) for r in reports]


# ═════════════════════════════════════════════════════════════════════════════
# Private helpers
# ═════════════════════════════════════════════════════════════════════════════


def _build_duckdb_config(source_type: SourceType, config: dict[str, Any]) -> dict[str, Any]:
    """Transform a ConnectionConfigInput dict to the format the query engine expects."""
    st = source_type.value

    if st in ("postgres", "mysql"):
        return {
            "type": st,
            "host": config.get("host", "localhost"),
            "port": config.get("port", 5432 if st == "postgres" else 3306),
            "database": config.get("database", ""),
            "username": config.get("username", ""),
            "password": config.get("password", ""),
            "schema_name": config.get("schema_name", "public" if st == "postgres" else ""),
        }

    if st == "s3":
        s3_path = f"s3://{config.get('bucket', '')}/{config.get('prefix', '')}".rstrip("/")
        file_format = config.get("file_format", "parquet")
        if not s3_path.endswith(f".{file_format}"):
            s3_path = f"{s3_path}/*.{file_format}"
        return {
            "type": "s3",
            "s3_path": s3_path,
            "aws_config": {
                "region": config.get("region", "us-east-1"),
                "aws_access_key": config.get("aws_access_key", ""),
                "aws_secret_key": config.get("aws_secret_key", ""),
                "endpoint": config.get("endpoint_url", ""),
            },
        }

    if st == "snowflake":
        return {
            "type": "snowflake",
            "account": config.get("account", ""),
            "username": config.get("username", ""),
            "password": config.get("password", ""),
            "warehouse": config.get("warehouse", ""),
            "database": config.get("database", ""),
            "schema_name": config.get("schema_name", "PUBLIC"),
            "table": config.get("table", ""),
        }

    return {"type": st, **config}


async def _write_temp_file(data: bytes, filename: str) -> str:
    """Write upload data to a temp file and return its path (for DuckDB to read)."""
    import asyncio

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "csv"

    def _write() -> str:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}", prefix="forge_") as tmp:
            tmp.write(data)
            return tmp.name

    return await asyncio.to_thread(_write)


async def _stream_ndjson(result: dict[str, Any]):
    """Yield NDJSON lines for streaming large query results."""
    columns = result["columns"]
    yield (
        json.dumps(
            {
                "type": "metadata",
                "columns": columns,
                "row_count": result["row_count"],
                "execution_time_ms": result["execution_time_ms"],
            }
        )
        + "\n"
    )
    for row in result["rows"]:
        yield json.dumps({"type": "row", "data": row}) + "\n"


async def _delete_from_minio(object_name: str) -> None:
    """Delete an object from MinIO."""
    try:
        from minio import Minio

        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_use_ssl,
        )
        client.remove_object(settings.minio_bucket, object_name)
    except Exception as exc:
        raise ServiceUnavailableException("MinIO storage") from exc


# ── Original connectivity testing helpers ────────────────────────────────────


async def _test_sql_connection(config: ConnectionConfig) -> tuple[bool, str]:
    try:
        import connectorx as cx

        driver = "postgresql" if config.type == "postgres" else "mysql"
        conn_str = (
            f"{driver}://{config.username}:{config.password}"
            f"@{config.host}:{config.port or 5432}/{config.database}"
        )
        cx.read_sql(conn_str, "SELECT 1")
        return True, "Connection successful"
    except Exception as exc:
        return False, str(exc)


async def _test_rest_connection(config: ConnectionConfig) -> tuple[bool, str]:
    if not config.url:
        return False, "URL is required for REST connector"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(config.url, headers=config.headers or {})
            return r.is_success, f"HTTP {r.status_code}"
    except Exception as exc:
        return False, str(exc)


async def _test_s3_connection(config: ConnectionConfig) -> tuple[bool, str]:
    try:
        import boto3

        kwargs: dict[str, Any] = {
            "aws_access_key_id": config.access_key,
            "aws_secret_access_key": config.secret_key,
        }
        if config.endpoint_url:
            kwargs["endpoint_url"] = config.endpoint_url
        s3 = boto3.client("s3", **kwargs)
        s3.head_bucket(Bucket=config.bucket or "")
        return True, "Bucket is accessible"
    except Exception as exc:
        return False, str(exc)


async def _introspect_postgres(config: ConnectionConfig) -> list[TableInfo]:
    import connectorx as cx

    conn_str = (
        f"postgresql://{config.username}:{config.password}"
        f"@{config.host}:{config.port or 5432}/{config.database}"
    )
    df = cx.read_sql(
        conn_str,
        """
        SELECT table_schema, table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY table_schema, table_name, ordinal_position
        """,
    )
    tables: dict[str, TableInfo] = {}
    for row in df.to_dicts() if hasattr(df, "to_dicts") else df.itertuples():
        key = f"{row['table_schema']}.{row['table_name']}"
        if key not in tables:
            tables[key] = TableInfo(
                schema_name=row["table_schema"],
                name=row["table_name"],
                columns=[],
            )
        tables[key].columns.append(
            ColumnInfo(
                name=row["column_name"],
                dtype=row["data_type"],
                nullable=row["is_nullable"] == "YES",
            )
        )
    return list(tables.values())


async def _introspect_mysql(config: ConnectionConfig) -> list[TableInfo]:
    return []
