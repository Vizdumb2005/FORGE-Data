"""Dataset service — upload, parse, preview and manage datasets."""

import io
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import NotFoundException, ServiceUnavailableException
from app.core.pii_detector import PIIDetector
from app.core.security import decrypt_field, encrypt_field
from app.models.dataset import Dataset, SourceType
from app.schemas.dataset import DatasetCreate, DatasetPreview, DatasetUpdate

_pii_detector = PIIDetector()

async def list_datasets(db: AsyncSession, workspace_id: str) -> list[Dataset]:
    result = await db.execute(
        select(Dataset)
        .where(Dataset.workspace_id == workspace_id)
        .order_by(Dataset.created_at.desc())
    )
    return list(result.scalars().all())


async def get_dataset(db: AsyncSession, workspace_id: str, dataset_id: str) -> Dataset:
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


async def create_dataset(
    db: AsyncSession,
    workspace_id: str,
    payload: DatasetCreate,
    creator_id: str,
) -> Dataset:
    # Encrypt connection config before storage
    encrypted_config: dict | None = None
    if payload.connection_config:
        import json

        raw = json.dumps(payload.connection_config)
        encrypted_config = {"__encrypted__": encrypt_field(raw)}

    dataset = Dataset(
        workspace_id=workspace_id,
        created_by=creator_id,
        name=payload.name,
        description=payload.description,
        source_type=payload.source_type.value,
        connection_config=encrypted_config,
    )
    db.add(dataset)
    await db.flush()
    await db.refresh(dataset)
    return dataset


async def update_dataset(
    db: AsyncSession,
    workspace_id: str,
    dataset_id: str,
    payload: DatasetUpdate,
) -> Dataset:
    dataset = await get_dataset(db, workspace_id, dataset_id)

    if payload.name is not None:
        dataset.name = payload.name
    if payload.description is not None:
        dataset.description = payload.description
    if payload.connection_config is not None:
        import json

        raw = json.dumps(payload.connection_config)
        dataset.connection_config = {"__encrypted__": encrypt_field(raw)}
        dataset.version = (dataset.version or 1) + 1

    await db.flush()
    return dataset


async def delete_dataset(db: AsyncSession, workspace_id: str, dataset_id: str) -> None:
    dataset = await get_dataset(db, workspace_id, dataset_id)
    await db.delete(dataset)
    await db.flush()


async def ingest_file(
    db: AsyncSession,
    workspace_id: str,
    dataset_id: str,
    file_bytes: bytes,
    filename: str,
) -> Dataset:
    """
    Upload a CSV/Excel/Parquet file to MinIO and extract schema + stats.
    Updates the Dataset record with row_count, column_count, size_bytes, and schema_snapshot.
    """
    import pandas as pd

    dataset = await get_dataset(db, workspace_id, dataset_id)

    # Parse file
    buf = io.BytesIO(file_bytes)
    if filename.endswith(".parquet"):
        df = pd.read_parquet(buf)
    elif filename.endswith((".xlsx", ".xls")):
        df = pd.read_excel(buf)
    else:
        df = pd.read_csv(buf)

    # Build schema snapshot
    pii_columns = await _pii_detector.scan_dataframe(df)
    schema = [
        {
            "name": col,
            "dtype": str(df[col].dtype),
            "nullable": bool(df[col].isna().any()),
            "sample_values": df[col].dropna().head(3).tolist(),
            "pii_types": pii_columns.get(str(col), []),
        }
        for col in df.columns
    ]

    # Upload to MinIO
    storage_path = await _upload_to_minio(
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        data=file_bytes,
        filename=filename,
    )

    # Update record
    dataset.row_count = len(df)
    dataset.column_count = len(df.columns)
    dataset.size_bytes = len(file_bytes)
    dataset.schema_snapshot = schema
    dataset.storage_path = storage_path
    dataset.source_type = SourceType.parquet.value  # store as parquet after ingestion
    dataset.metadata_info = {
        **(dataset.metadata_info or {}),
        "pii_columns": pii_columns,
        "pii_detected": bool(pii_columns),
    }

    await db.flush()
    await db.refresh(dataset)
    return dataset


async def get_preview(
    db: AsyncSession,
    workspace_id: str,
    dataset_id: str,
    n_rows: int = 100,
) -> DatasetPreview:
    """Return the first *n_rows* rows from a dataset stored in MinIO."""
    import pandas as pd

    dataset = await get_dataset(db, workspace_id, dataset_id)

    if not dataset.storage_path:
        raise NotFoundException("Dataset file", dataset_id)

    data = await _download_from_minio(dataset.storage_path)
    if dataset.storage_path.endswith(".parquet"):
        df = pd.read_parquet(io.BytesIO(data))
    else:
        df = pd.read_csv(io.BytesIO(data))

    total = len(df)
    sample = df.head(n_rows)
    return DatasetPreview(
        columns=list(sample.columns),
        rows=sample.values.tolist(),
        total_rows=total,
        truncated=total > n_rows,
    )


async def update_profile(
    db: AsyncSession, workspace_id: str, dataset_id: str, profile_data: dict
) -> Dataset:
    """Store profiling results on the Dataset record."""
    dataset = await get_dataset(db, workspace_id, dataset_id)
    dataset.profile_data = profile_data
    dataset.row_count = profile_data.get("row_count", dataset.row_count)
    dataset.column_count = profile_data.get("column_count", dataset.column_count)
    await db.flush()
    await db.refresh(dataset)
    return dataset


async def mask_detected_pii(
    db: AsyncSession,
    workspace_id: str,
    dataset_id: str,
) -> Dataset:
    import pandas as pd

    dataset = await get_dataset(db, workspace_id, dataset_id)
    if not dataset.storage_path:
        raise NotFoundException("Dataset file", dataset_id)

    pii_columns = ((dataset.metadata_info or {}).get("pii_columns") or {})
    if not isinstance(pii_columns, dict) or not pii_columns:
        return dataset

    data = await _download_from_minio(dataset.storage_path)
    if dataset.storage_path.endswith(".parquet"):
        df = pd.read_parquet(io.BytesIO(data))
        original_format = "parquet"
    else:
        df = pd.read_csv(io.BytesIO(data))
        original_format = "csv"

    for column_name, pii_types in pii_columns.items():
        if not isinstance(pii_types, list) or not pii_types:
            continue
        if column_name not in df.columns:
            continue
        # Apply first detected type per column for deterministic masking output
        df = await _pii_detector.mask_column(df, str(column_name), str(pii_types[0]))

    if original_format == "parquet":
        out_buf = io.BytesIO()
        df.to_parquet(out_buf, index=False)
        masked_bytes = out_buf.getvalue()
    else:
        out_buf = io.StringIO()
        df.to_csv(out_buf, index=False)
        masked_bytes = out_buf.getvalue().encode("utf-8")

    filename = dataset.storage_path.split("/")[-1] if dataset.storage_path else f"{dataset.name}.csv"
    storage_path = await _upload_to_minio(
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        data=masked_bytes,
        filename=filename,
    )

    dataset.storage_path = storage_path
    dataset.row_count = len(df)
    dataset.column_count = len(df.columns)
    dataset.size_bytes = len(masked_bytes)
    dataset.version = (dataset.version or 1) + 1
    dataset.metadata_info = {
        **(dataset.metadata_info or {}),
        "pii_masked": True,
    }
    await db.flush()
    await db.refresh(dataset)
    return dataset


async def acknowledge_pii(
    db: AsyncSession,
    workspace_id: str,
    dataset_id: str,
    user_id: str,
) -> Dataset:
    dataset = await get_dataset(db, workspace_id, dataset_id)
    metadata_info = dataset.metadata_info or {}
    acknowledged_by = metadata_info.get("pii_acknowledged_by") or []
    if user_id not in acknowledged_by:
        acknowledged_by.append(user_id)
    metadata_info["pii_acknowledged_by"] = acknowledged_by
    metadata_info["pii_acknowledged"] = True
    dataset.metadata_info = metadata_info
    await db.flush()
    await db.refresh(dataset)
    return dataset


def get_decrypted_connection_config(dataset: Dataset) -> dict[str, Any] | None:
    """Return the plaintext connection config dict, or None if not set."""
    if not dataset.connection_config:
        return None
    if "__encrypted__" in dataset.connection_config:
        import json

        return json.loads(decrypt_field(dataset.connection_config["__encrypted__"]))
    return dataset.connection_config  # legacy unencrypted


# ── Private helpers ────────────────────────────────────────────────────────────


async def _upload_to_minio(workspace_id: str, dataset_id: str, data: bytes, filename: str) -> str:
    """Upload *data* to MinIO and return the object path."""
    try:
        from minio import Minio

        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_use_ssl,
        )
        object_name = f"datasets/{workspace_id}/{dataset_id}/{filename}"
        client.put_object(
            settings.minio_bucket,
            object_name,
            io.BytesIO(data),
            length=len(data),
        )
        return object_name
    except Exception as exc:
        raise ServiceUnavailableException("MinIO storage") from exc


async def _download_from_minio(object_name: str) -> bytes:
    """Download an object from MinIO and return its bytes."""
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
