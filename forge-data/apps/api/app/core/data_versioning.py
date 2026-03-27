"""Delta-style data versioning — Parquet snapshots stored in MinIO."""

import io
import logging
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.event_bus import event_bus
from app.core.exceptions import NotFoundException, ServiceUnavailableException
from app.models.dataset import Dataset
from app.models.dataset_version import DatasetVersion

logger = logging.getLogger(__name__)


class DataVersionManager:
    """Lightweight Delta-style versioning for uploaded datasets.

    Each version is stored as a Parquet snapshot in MinIO under
    ``versions/{dataset_id}/v{n}.parquet`` and tracked in the
    ``dataset_versions`` table.
    """

    # ── Create version ────────────────────────────────────────────────────

    async def create_version(
        self,
        db: AsyncSession,
        workspace_id: str,
        dataset_id: str,
        file_bytes: bytes,
        filename: str,
        user_id: str,
        message: str = "",
    ) -> DatasetVersion:
        """Ingest *file_bytes* as a new versioned Parquet snapshot."""
        dataset = await _get_dataset(db, workspace_id, dataset_id)

        # Parse to DataFrame
        df = _parse_file(file_bytes, filename)

        # Determine next version number
        next_version = (dataset.version or 0) + 1

        # Convert to Parquet bytes
        parquet_bytes = _dataframe_to_parquet(df)

        # Upload to MinIO
        parquet_path = f"versions/{dataset_id}/v{next_version}.parquet"
        await _upload_to_minio(parquet_path, parquet_bytes)

        # Build schema snapshot
        schema = _build_schema_snapshot(df)

        # Create version record
        version = DatasetVersion(
            dataset_id=dataset_id,
            version_number=next_version,
            message=message,
            schema_snapshot=schema,
            row_count=len(df),
            size_bytes=len(parquet_bytes),
            parquet_path=parquet_path,
            created_by=user_id,
        )
        db.add(version)

        # Update the parent dataset
        dataset.version = next_version
        dataset.row_count = len(df)
        dataset.column_count = len(df.columns)
        dataset.size_bytes = len(parquet_bytes)
        dataset.schema_snapshot = schema

        await db.flush()
        await event_bus.publish(
            "dataset.version_created",
            {
                "workspace_id": workspace_id,
                "dataset_id": dataset_id,
                "version_number": next_version,
                "created_by": user_id,
                "message": message,
            },
        )
        logger.info(
            "Created version %d for dataset %s (%d rows)",
            next_version,
            dataset_id,
            len(df),
        )
        return version

    # ── Get version as DataFrame ──────────────────────────────────────────

    async def get_version(
        self,
        db: AsyncSession,
        workspace_id: str,
        dataset_id: str,
        version_number: int,
    ) -> pd.DataFrame:
        """Fetch a specific version's Parquet from MinIO as a DataFrame."""
        version = await _get_version(db, workspace_id, dataset_id, version_number)
        data = await _download_from_minio(version.parquet_path)
        return pd.read_parquet(io.BytesIO(data))

    # ── List versions ─────────────────────────────────────────────────────

    async def list_versions(
        self,
        db: AsyncSession,
        workspace_id: str,
        dataset_id: str,
    ) -> list[DatasetVersion]:
        """Return all versions for a dataset, ordered by version_number desc."""
        # Verify dataset exists in workspace
        await _get_dataset(db, workspace_id, dataset_id)

        result = await db.execute(
            select(DatasetVersion)
            .where(DatasetVersion.dataset_id == dataset_id)
            .order_by(DatasetVersion.version_number.desc())
        )
        return list(result.scalars().all())

    # ── Diff versions ─────────────────────────────────────────────────────

    async def diff_versions(
        self,
        db: AsyncSession,
        workspace_id: str,
        dataset_id: str,
        v1: int,
        v2: int,
    ) -> dict[str, Any]:
        """Compare two versions and return a structured diff."""
        ver1 = await _get_version(db, workspace_id, dataset_id, v1)
        ver2 = await _get_version(db, workspace_id, dataset_id, v2)

        # Load both DataFrames
        data1 = await _download_from_minio(ver1.parquet_path)
        data2 = await _download_from_minio(ver2.parquet_path)
        df1 = pd.read_parquet(io.BytesIO(data1))
        df2 = pd.read_parquet(io.BytesIO(data2))

        # Schema changes
        cols1 = set(df1.columns)
        cols2 = set(df2.columns)
        added_columns = sorted(cols2 - cols1)
        removed_columns = sorted(cols1 - cols2)
        common_columns = sorted(cols1 & cols2)

        # Type changes
        type_changes = []
        for col in common_columns:
            t1 = str(df1[col].dtype)
            t2 = str(df2[col].dtype)
            if t1 != t2:
                type_changes.append({"column": col, "from": t1, "to": t2})

        # Row count delta
        row_delta = len(df2) - len(df1)

        # Statistical summary delta for common numeric columns
        stat_changes = []
        for col in common_columns:
            if pd.api.types.is_numeric_dtype(df1[col]) and pd.api.types.is_numeric_dtype(df2[col]):
                s1 = _column_stats(df1[col])
                s2 = _column_stats(df2[col])
                stat_changes.append(
                    {
                        "column": col,
                        "v1": s1,
                        "v2": s2,
                        "mean_delta": _safe_sub(s2.get("mean"), s1.get("mean")),
                        "null_pct_delta": _safe_sub(s2.get("null_pct"), s1.get("null_pct")),
                    }
                )

        return {
            "v1": v1,
            "v2": v2,
            "row_count_v1": len(df1),
            "row_count_v2": len(df2),
            "row_delta": row_delta,
            "added_columns": added_columns,
            "removed_columns": removed_columns,
            "type_changes": type_changes,
            "stat_changes": stat_changes,
        }

    # ── Rollback ──────────────────────────────────────────────────────────

    async def rollback(
        self,
        db: AsyncSession,
        workspace_id: str,
        dataset_id: str,
        target_version: int,
        user_id: str,
    ) -> DatasetVersion:
        """Roll back to *target_version* by creating a NEW version from the target's snapshot."""
        target = await _get_version(db, workspace_id, dataset_id, target_version)
        dataset = await _get_dataset(db, workspace_id, dataset_id)

        # Load the target version's Parquet
        data = await _download_from_minio(target.parquet_path)

        next_version = (dataset.version or 0) + 1
        new_path = f"versions/{dataset_id}/v{next_version}.parquet"

        # Copy to new version path
        await _upload_to_minio(new_path, data)

        # Create new version record
        version = DatasetVersion(
            dataset_id=dataset_id,
            version_number=next_version,
            message=f"Rollback to v{target_version}",
            schema_snapshot=target.schema_snapshot,
            row_count=target.row_count,
            size_bytes=target.size_bytes,
            parquet_path=new_path,
            created_by=user_id,
        )
        db.add(version)

        # Update parent dataset
        dataset.version = next_version
        dataset.row_count = target.row_count
        dataset.schema_snapshot = target.schema_snapshot

        await db.flush()
        logger.info(
            "Rolled back dataset %s to v%d (new v%d)",
            dataset_id,
            target_version,
            next_version,
        )
        return version


# ── Private helpers ───────────────────────────────────────────────────────────


async def _get_dataset(db: AsyncSession, workspace_id: str, dataset_id: str) -> Dataset:
    result = await db.execute(
        select(Dataset).where(
            Dataset.id == dataset_id,
            Dataset.workspace_id == workspace_id,
        )
    )
    dataset = result.scalar_one_or_none()
    if dataset is None:
        raise NotFoundException("Dataset", dataset_id)
    return dataset


async def _get_version(
    db: AsyncSession, workspace_id: str, dataset_id: str, version_number: int
) -> DatasetVersion:
    # Verify dataset exists in workspace
    await _get_dataset(db, workspace_id, dataset_id)

    result = await db.execute(
        select(DatasetVersion).where(
            DatasetVersion.dataset_id == dataset_id,
            DatasetVersion.version_number == version_number,
        )
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise NotFoundException("DatasetVersion", f"v{version_number}")
    return version


def _parse_file(file_bytes: bytes, filename: str) -> pd.DataFrame:
    buf = io.BytesIO(file_bytes)
    lower = filename.lower()
    if lower.endswith(".parquet"):
        return pd.read_parquet(buf)
    if lower.endswith((".xlsx", ".xls")):
        return pd.read_excel(buf)
    if lower.endswith(".json"):
        return pd.read_json(buf)
    return pd.read_csv(buf)


def _dataframe_to_parquet(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, engine="pyarrow")
    return buf.getvalue()


def _build_schema_snapshot(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [
        {
            "name": col,
            "dtype": str(df[col].dtype),
            "nullable": bool(df[col].isna().any()),
            "sample_values": [
                v if not pd.isna(v) else None for v in df[col].dropna().head(3).tolist()
            ],
        }
        for col in df.columns
    ]


def _column_stats(series: pd.Series) -> dict[str, Any]:
    total = len(series)
    null_count = int(series.isna().sum())
    return {
        "mean": round(float(series.mean()), 4) if total - null_count > 0 else None,
        "std": round(float(series.std()), 4) if total - null_count > 1 else None,
        "min": float(series.min()) if total - null_count > 0 else None,
        "max": float(series.max()) if total - null_count > 0 else None,
        "null_pct": round(null_count / total * 100, 2) if total > 0 else 0,
    }


def _safe_sub(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return round(a - b, 4)


async def _upload_to_minio(object_name: str, data: bytes) -> None:
    try:
        from minio import Minio

        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_use_ssl,
        )
        client.put_object(
            settings.minio_bucket,
            object_name,
            io.BytesIO(data),
            length=len(data),
        )
    except Exception as exc:
        raise ServiceUnavailableException("MinIO storage") from exc


async def _download_from_minio(object_name: str) -> bytes:
    try:
        from minio import Minio

        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_use_ssl,
        )
        response = client.get_object(settings.minio_bucket, object_name)
        return response.read()
    except Exception as exc:
        raise ServiceUnavailableException("MinIO storage") from exc
