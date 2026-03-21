"""Federated query engine — DuckDB-backed multi-source analytical layer."""

import asyncio
import contextlib
import logging
import re
import threading
import time
from typing import Any

import duckdb

logger = logging.getLogger(__name__)

# Numeric DuckDB types that support AVG aggregation
_NUMERIC_TYPES = frozenset(
    {
        "TINYINT",
        "SMALLINT",
        "INTEGER",
        "BIGINT",
        "HUGEINT",
        "FLOAT",
        "DOUBLE",
        "DECIMAL",
        "REAL",
        "NUMERIC",
        "UTINYINT",
        "USMALLINT",
        "UINTEGER",
        "UBIGINT",
    }
)

_LIMIT_RE = re.compile(r"\bLIMIT\s+\d+", re.IGNORECASE)

_QUERY_TIMEOUT_SECONDS = 30


def _sanitize_name(name: str) -> str:
    """Ensure a source name is a safe SQL identifier."""
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    if not clean or clean[0].isdigit():
        clean = f"ds_{clean}"
    return clean.lower()


class FederatedQueryEngine:
    """Per-user isolated DuckDB instances for cross-source analytical queries.

    Each user gets their own in-memory DuckDB connection. Sources (CSV files,
    Parquet, Postgres, etc.) are registered into the user's connection and can
    then be queried together with standard SQL.
    """

    def __init__(self) -> None:
        # user_id -> (connection, last_used_timestamp)
        self._connections: dict[str, tuple[duckdb.DuckDBPyConnection, float]] = {}
        self._lock = threading.Lock()

    # ── Connection management ────────────────────────────────────────────────

    async def get_connection(self, user_id: str) -> duckdb.DuckDBPyConnection:
        """Return or create an isolated DuckDB connection for *user_id*."""

        def _get_or_create() -> duckdb.DuckDBPyConnection:
            with self._lock:
                if user_id in self._connections:
                    conn, _ = self._connections[user_id]
                    self._connections[user_id] = (conn, time.time())
                    return conn
                conn = duckdb.connect(":memory:")
                # Enable httpfs for S3/HTTP sources
                conn.execute("INSTALL httpfs; LOAD httpfs;")
                self._connections[user_id] = (conn, time.time())
                logger.info("Created DuckDB connection for user %s", user_id)
                return conn

        return await asyncio.to_thread(_get_or_create)

    async def close_connection(self, user_id: str) -> None:
        """Close and remove a user's DuckDB connection."""

        def _close() -> None:
            with self._lock:
                entry = self._connections.pop(user_id, None)
            if entry:
                with contextlib.suppress(Exception):
                    entry[0].close()
                logger.info("Closed DuckDB connection for user %s", user_id)

        await asyncio.to_thread(_close)

    async def close_all(self) -> None:
        """Close every connection — called on application shutdown."""

        def _close_all() -> None:
            with self._lock:
                entries = list(self._connections.items())
                self._connections.clear()
            for uid, (conn, _) in entries:
                with contextlib.suppress(Exception):
                    conn.close()
                logger.debug("Closed DuckDB connection for user %s", uid)

        await asyncio.to_thread(_close_all)

    async def cleanup_idle(self, max_idle_seconds: int = 1800) -> int:
        """Evict connections idle for longer than *max_idle_seconds*. Returns count evicted."""

        def _cleanup() -> int:
            now = time.time()
            to_evict: list[str] = []
            with self._lock:
                for uid, (_, last_used) in self._connections.items():
                    if now - last_used > max_idle_seconds:
                        to_evict.append(uid)
                evicted = []
                for uid in to_evict:
                    entry = self._connections.pop(uid, None)
                    if entry:
                        evicted.append(entry[0])
            for conn in evicted:
                with contextlib.suppress(Exception):
                    conn.close()
            if to_evict:
                logger.info("Evicted %d idle DuckDB connections", len(to_evict))
            return len(to_evict)

        return await asyncio.to_thread(_cleanup)

    # ── Source registration ──────────────────────────────────────────────────

    async def register_source(
        self, user_id: str, source_name: str, source_config: dict[str, Any]
    ) -> dict[str, Any]:
        """Register a data source into the user's DuckDB connection.

        Returns ``{"source_name": ..., "columns": [...], "row_count": ...}``.
        """
        conn = await self.get_connection(user_id)
        safe_name = _sanitize_name(source_name)
        source_type = source_config.get("type", "csv")

        register_fn = {
            "csv": self._register_csv,
            "parquet": self._register_parquet,
            "excel": self._register_csv,  # pandas converts to CSV-like, stored as parquet
            "json": self._register_csv,
            "postgres": self._register_postgres,
            "mysql": self._register_mysql,
            "s3": self._register_s3_parquet,
            "snowflake": self._register_snowflake,
        }.get(source_type)

        if register_fn is None:
            raise ValueError(f"Unsupported source type: {source_type}")

        await register_fn(conn, safe_name, source_config)

        # Fetch column info
        columns = await self._describe_table(conn, safe_name)
        row_count = await self._count_rows(conn, safe_name)

        return {"source_name": safe_name, "columns": columns, "row_count": row_count}

    async def _register_csv(
        self, conn: duckdb.DuckDBPyConnection, name: str, config: dict[str, Any]
    ) -> None:
        file_path = config["file_path"]
        # Validate path contains no SQL-special characters before interpolation
        if not re.match(r"^[\w/\\:. -]+$", file_path):
            raise ValueError(f"Unsafe file path: {file_path!r}")

        def _do() -> None:
            conn.execute(
                f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM read_csv_auto(?)',
                [file_path],
            )

        await asyncio.to_thread(_do)

    async def _register_parquet(
        self, conn: duckdb.DuckDBPyConnection, name: str, config: dict[str, Any]
    ) -> None:
        file_path = config["file_path"]
        if not re.match(r"^[\w/\\:. -]+$", file_path):
            raise ValueError(f"Unsafe file path: {file_path!r}")

        def _do() -> None:
            conn.execute(
                f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM read_parquet(?)',
                [file_path],
            )

        await asyncio.to_thread(_do)

    async def _register_postgres(
        self, conn: duckdb.DuckDBPyConnection, name: str, config: dict[str, Any]
    ) -> None:
        host = config.get("host", "")
        port = config.get("port", 5432)
        database = config.get("database", "")
        username = config.get("username", "")
        password = config.get("password", "")
        schema_name = config.get("schema_name", "public")
        # Escape single quotes in credential values to prevent connection string injection
        def _esc(v: str) -> str:
            return str(v).replace("'", "''")
        conn_str = (
            f"host={_esc(host)} port={int(port)} dbname={_esc(database)} "
            f"user={_esc(username)} password={_esc(password)}"
        )

        def _do() -> None:
            conn.execute("INSTALL postgres; LOAD postgres;")
            with contextlib.suppress(Exception):
                conn.execute(f'DETACH IF EXISTS "{name}"')
            conn.execute(
                f"ATTACH '{conn_str}' AS \"{name}\" (TYPE postgres, SCHEMA '{_esc(schema_name)}')"
            )

        await asyncio.to_thread(_do)

    async def _register_mysql(
        self, conn: duckdb.DuckDBPyConnection, name: str, config: dict[str, Any]
    ) -> None:
        host = config.get("host", "")
        port = config.get("port", 3306)
        database = config.get("database", "")
        username = config.get("username", "")
        password = config.get("password", "")
        def _esc(v: str) -> str:
            return str(v).replace("'", "''")
        conn_str = (
            f"host={_esc(host)} port={int(port)} database={_esc(database)} "
            f"user={_esc(username)} password={_esc(password)}"
        )

        def _do() -> None:
            conn.execute("INSTALL mysql; LOAD mysql;")
            with contextlib.suppress(Exception):
                conn.execute(f'DETACH IF EXISTS "{name}"')
            conn.execute(f"ATTACH '{conn_str}' AS \"{name}\" (TYPE mysql)")

        await asyncio.to_thread(_do)

    async def _register_s3_parquet(
        self, conn: duckdb.DuckDBPyConnection, name: str, config: dict[str, Any]
    ) -> None:
        s3_path = config.get("s3_path", "")
        aws_config = config.get("aws_config", {})
        region = aws_config.get("region", "us-east-1")
        access_key = aws_config.get("aws_access_key", "")
        secret_key = aws_config.get("aws_secret_key", "")
        endpoint = aws_config.get("endpoint", "")

        # Validate credential characters to prevent SET statement injection
        _cred_re = re.compile(r"^[A-Za-z0-9+/=_\-]*$")
        if not _cred_re.match(access_key):
            raise ValueError("Invalid S3 access key format")
        if not _cred_re.match(secret_key):
            raise ValueError("Invalid S3 secret key format")
        if not re.match(r"^[a-z0-9-]*$", region):
            raise ValueError("Invalid S3 region format")

        def _do() -> None:
            conn.execute(f"SET s3_region='{region}';")
            conn.execute(f"SET s3_access_key_id='{access_key}';")
            conn.execute(f"SET s3_secret_access_key='{secret_key}';")
            if endpoint:
                conn.execute(f"SET s3_endpoint='{endpoint}';")
                conn.execute("SET s3_url_style='path';")
                conn.execute("SET s3_use_ssl=false;")
            conn.execute(
                f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM read_parquet(?)',
                [s3_path],
            )

        await asyncio.to_thread(_do)

    async def _register_snowflake(
        self, conn: duckdb.DuckDBPyConnection, name: str, config: dict[str, Any]
    ) -> None:
        """Register a Snowflake source.

        DuckDB doesn't have a native Snowflake extension, so we use the
        snowflake-connector-python to pull data into a local DuckDB table.
        """
        account = config.get("account", "")
        username = config.get("username", "")
        password = config.get("password", "")
        warehouse = config.get("warehouse", "")
        database = config.get("database", "")
        schema_name = config.get("schema_name", "PUBLIC")
        table = config.get("table", "")
        # Validate table is a safe SQL identifier before interpolation
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_.]*$", table):
            raise ValueError(f"Invalid Snowflake table identifier: {table!r}")

        def _do() -> None:
            import snowflake.connector

            sf_conn = snowflake.connector.connect(
                account=account,
                user=username,
                password=password,
                warehouse=warehouse,
                database=database,
                schema=schema_name,
            )
            try:
                cursor = sf_conn.cursor()
                cursor.execute("SELECT * FROM IDENTIFIER(%s)", (table,))
                try:
                    arrow_table = cursor.fetch_arrow_all()  # noqa: F841
                    conn.execute(
                        f'CREATE OR REPLACE TABLE "{name}" AS ' "SELECT * FROM arrow_table"
                    )
                except Exception:
                    df = cursor.fetch_pandas_all()  # noqa: F841
                    conn.execute(f'CREATE OR REPLACE TABLE "{name}" AS ' "SELECT * FROM df")
            finally:
                sf_conn.close()

        await asyncio.to_thread(_do)

    # ── Query execution ──────────────────────────────────────────────────────

    async def execute_query(self, user_id: str, sql: str, limit: int = 10000) -> dict[str, Any]:
        """Execute *sql* against the user's DuckDB connection.

        Returns ``{"columns": [...], "rows": [[...], ...], "row_count": N,
        "execution_time_ms": M}``.

        Enforces a row LIMIT and a 30-second timeout.
        """
        conn = await self.get_connection(user_id)

        # Inject LIMIT if not already present
        trimmed = sql.strip().rstrip(";")
        if not _LIMIT_RE.search(trimmed):
            trimmed = f"{trimmed} LIMIT {limit}"

        def _execute() -> dict[str, Any]:
            start = time.perf_counter()
            try:
                result = conn.execute(trimmed)
                columns = [desc[0] for desc in result.description]
                rows = result.fetchall()
                elapsed = (time.perf_counter() - start) * 1000
                serialised_rows = [list(row) for row in rows]
                return {
                    "columns": columns,
                    "rows": serialised_rows,
                    "row_count": len(serialised_rows),
                    "execution_time_ms": round(elapsed, 1),
                }
            except duckdb.Error as exc:
                elapsed = (time.perf_counter() - start) * 1000
                error_msg = str(exc)
                line_match = re.search(r"LINE (\d+)", error_msg)
                col_match = re.search(r"COL (\d+)", error_msg)
                raise QueryError(
                    error=error_msg,
                    execution_time_ms=round(elapsed, 1),
                    line=int(line_match.group(1)) if line_match else None,
                    column=int(col_match.group(1)) if col_match else None,
                ) from exc

        try:
            return await asyncio.wait_for(
                asyncio.to_thread(_execute),
                timeout=_QUERY_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            with contextlib.suppress(Exception):
                conn.interrupt()
            raise QueryError(
                error="Query timed out",
                execution_time_ms=_QUERY_TIMEOUT_SECONDS * 1000,
            ) from exc

    # ── Schema introspection ─────────────────────────────────────────────────

    async def get_schema(self, user_id: str, source_name: str) -> list[dict[str, Any]]:
        """Return column definitions for *source_name*."""
        conn = await self.get_connection(user_id)
        safe_name = _sanitize_name(source_name)

        def _describe() -> list[dict[str, Any]]:
            result = conn.execute(f'DESCRIBE "{safe_name}"')
            return [
                {
                    "name": row[0],
                    "type": row[1],
                    "nullable": row[2] == "YES" if len(row) > 2 else True,
                }
                for row in result.fetchall()
            ]

        return await asyncio.to_thread(_describe)

    # ── Dataset profiling ────────────────────────────────────────────────────

    async def profile_dataset(self, user_id: str, source_name: str) -> dict[str, Any]:
        """Run profiling queries and return structured statistics."""
        conn = await self.get_connection(user_id)
        safe_name = _sanitize_name(source_name)

        def _profile() -> dict[str, Any]:
            row_count = conn.execute(f'SELECT COUNT(*) FROM "{safe_name}"').fetchone()[0]

            desc_result = conn.execute(f'DESCRIBE "{safe_name}"')
            col_defs = desc_result.fetchall()

            column_profiles = []
            for col_row in col_defs:
                col_name = col_row[0]
                col_type = col_row[1]
                quoted_col = f'"{col_name}"'

                stats = conn.execute(
                    f"SELECT COUNT(DISTINCT {quoted_col}), "
                    f"SUM(CASE WHEN {quoted_col} IS NULL THEN 1 ELSE 0 END) "
                    f'FROM "{safe_name}"'
                ).fetchone()
                distinct_count = stats[0] or 0
                null_count = stats[1] or 0

                profile_entry: dict[str, Any] = {
                    "name": col_name,
                    "dtype": col_type,
                    "distinct_count": distinct_count,
                    "null_count": null_count,
                }

                base_type = col_type.split("(")[0].upper().strip()
                if base_type in _NUMERIC_TYPES:
                    num_stats = conn.execute(
                        f"SELECT MIN({quoted_col}), MAX({quoted_col}), "
                        f'AVG({quoted_col}) FROM "{safe_name}"'
                    ).fetchone()
                    profile_entry["min"] = _to_json_safe(num_stats[0])
                    profile_entry["max"] = _to_json_safe(num_stats[1])
                    profile_entry["avg"] = (
                        round(float(num_stats[2]), 4) if num_stats[2] is not None else None
                    )
                else:
                    try:
                        str_stats = conn.execute(
                            f"SELECT MIN({quoted_col}), MAX({quoted_col}) " f'FROM "{safe_name}"'
                        ).fetchone()
                        profile_entry["min"] = _to_json_safe(str_stats[0])
                        profile_entry["max"] = _to_json_safe(str_stats[1])
                    except Exception:
                        profile_entry["min"] = None
                        profile_entry["max"] = None
                    profile_entry["avg"] = None

                try:
                    samples = conn.execute(
                        f'SELECT DISTINCT {quoted_col} FROM "{safe_name}" '
                        f"WHERE {quoted_col} IS NOT NULL LIMIT 5"
                    ).fetchall()
                    profile_entry["sample_values"] = [_to_json_safe(s[0]) for s in samples]
                except Exception:
                    profile_entry["sample_values"] = []

                column_profiles.append(profile_entry)

            return {
                "row_count": row_count,
                "column_count": len(col_defs),
                "columns": column_profiles,
            }

        return await asyncio.to_thread(_profile)

    # ── Internal helpers ─────────────────────────────────────────────────────

    async def _describe_table(
        self, conn: duckdb.DuckDBPyConnection, name: str
    ) -> list[dict[str, str]]:
        def _do() -> list[dict[str, str]]:
            result = conn.execute(f'DESCRIBE "{name}"')
            return [{"name": r[0], "type": r[1]} for r in result.fetchall()]

        return await asyncio.to_thread(_do)

    async def _count_rows(self, conn: duckdb.DuckDBPyConnection, name: str) -> int:
        def _do() -> int:
            return conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]

        return await asyncio.to_thread(_do)

    async def unregister_source(self, user_id: str, source_name: str) -> None:
        """Drop a registered table/view from the user's DuckDB connection."""
        conn = await self.get_connection(user_id)
        safe_name = _sanitize_name(source_name)

        def _drop() -> None:
            with contextlib.suppress(Exception):
                conn.execute(f'DROP TABLE IF EXISTS "{safe_name}"')
            with contextlib.suppress(Exception):
                conn.execute(f'DETACH IF EXISTS "{safe_name}"')

        await asyncio.to_thread(_drop)


class QueryError(Exception):
    """Structured error raised when a DuckDB query fails."""

    def __init__(
        self,
        error: str,
        execution_time_ms: float = 0,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        self.error = error
        self.execution_time_ms = execution_time_ms
        self.line = line
        self.column = column
        super().__init__(error)


def _to_json_safe(value: Any) -> Any:
    """Convert DuckDB values to JSON-serialisable Python types."""
    if value is None:
        return None
    if isinstance(value, int | float | str | bool):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)
