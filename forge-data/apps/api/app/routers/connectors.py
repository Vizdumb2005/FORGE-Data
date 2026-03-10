"""Connectors router — test connectivity and introspect schema."""

from typing import Any, Literal

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from app.dependencies import CurrentUser

router = APIRouter()


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


# ── Private connector helpers ──────────────────────────────────────────────────

async def _test_sql_connection(config: ConnectionConfig) -> tuple[bool, str]:
    try:
        import connectorx as cx

        driver = "postgresql" if config.type == "postgres" else "mysql"
        conn_str = (
            f"{driver}://{config.username}:{config.password}"
            f"@{config.host}:{config.port or 5432}/{config.database}"
        )
        # Lightweight introspection query
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
    # Similar to _introspect_postgres but uses MySQL information_schema
    return []
