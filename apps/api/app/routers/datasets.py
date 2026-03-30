"""Datasets router — CRUD, file upload, and preview."""

from fastapi import APIRouter, Query, Request, UploadFile

from app.dependencies import CurrentUser, DBSession
from app.schemas.dataset import DatasetCreate, DatasetPreview, DatasetRead, DatasetUpdate
from app.services import audit_service, dataset_service, workspace_service

router = APIRouter()


@router.get(
    "/workspaces/{workspace_id}/datasets",
    response_model=list[DatasetRead],
    summary="List datasets in a workspace",
)
async def list_datasets(
    workspace_id: str, current_user: CurrentUser, db: DBSession
) -> list[DatasetRead]:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    datasets = await dataset_service.list_datasets(db, workspace_id)
    return [DatasetRead.from_orm_safe(d) for d in datasets]


@router.post(
    "/workspaces/{workspace_id}/datasets",
    response_model=DatasetRead,
    status_code=201,
    summary="Create a dataset record",
)
async def create_dataset(
    workspace_id: str,
    payload: DatasetCreate,
    current_user: CurrentUser,
    db: DBSession,
    request: Request,
) -> DatasetRead:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    dataset = await dataset_service.create_dataset(db, workspace_id, payload, current_user.id)
    await audit_service.log_event(
        db,
        action=audit_service.AuditAction.DATASET_CREATE,
        user_id=current_user.id,
        workspace_id=workspace_id,
        resource_type="dataset",
        resource_id=dataset.id,
        ip_address=request.client.host if request.client else None,
    )
    return DatasetRead.from_orm_safe(dataset)


@router.get(
    "/workspaces/{workspace_id}/datasets/{dataset_id}",
    response_model=DatasetRead,
    summary="Get a dataset",
)
async def get_dataset(
    workspace_id: str, dataset_id: str, current_user: CurrentUser, db: DBSession
) -> DatasetRead:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    dataset = await dataset_service.get_dataset(db, workspace_id, dataset_id)
    return DatasetRead.from_orm_safe(dataset)


@router.patch(
    "/workspaces/{workspace_id}/datasets/{dataset_id}",
    response_model=DatasetRead,
    summary="Update a dataset",
)
async def update_dataset(
    workspace_id: str,
    dataset_id: str,
    payload: DatasetUpdate,
    current_user: CurrentUser,
    db: DBSession,
) -> DatasetRead:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    dataset = await dataset_service.update_dataset(db, workspace_id, dataset_id, payload)
    return DatasetRead.from_orm_safe(dataset)


@router.delete(
    "/workspaces/{workspace_id}/datasets/{dataset_id}",
    status_code=200,
    summary="Delete a dataset",
)
async def delete_dataset(
    workspace_id: str,
    dataset_id: str,
    current_user: CurrentUser,
    db: DBSession,
    request: Request,
) -> None:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
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


@router.post(
    "/workspaces/{workspace_id}/datasets/{dataset_id}/upload",
    response_model=DatasetRead,
    summary="Upload a file (CSV / Excel / Parquet) and ingest into the dataset",
)
async def upload_file(
    workspace_id: str,
    dataset_id: str,
    file: UploadFile,
    current_user: CurrentUser,
    db: DBSession,
    request: Request,
) -> DatasetRead:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    contents = await file.read()
    dataset = await dataset_service.ingest_file(
        db, workspace_id, dataset_id, contents, file.filename or "upload"
    )
    await audit_service.log_event(
        db,
        action=audit_service.AuditAction.DATASET_UPLOAD,
        user_id=current_user.id,
        workspace_id=workspace_id,
        resource_type="dataset",
        resource_id=dataset_id,
        ip_address=request.client.host if request.client else None,
        metadata={"filename": file.filename, "size_bytes": len(contents)},
    )
    return DatasetRead.from_orm_safe(dataset)


@router.get(
    "/workspaces/{workspace_id}/datasets/{dataset_id}/preview",
    response_model=DatasetPreview,
    summary="Preview first N rows of a dataset",
)
async def preview_dataset(
    workspace_id: str,
    dataset_id: str,
    current_user: CurrentUser,
    db: DBSession,
    n: int = Query(default=100, ge=1, le=10000),
) -> DatasetPreview:
    await workspace_service.get_workspace(db, workspace_id, current_user.id)
    return await dataset_service.get_preview(db, workspace_id, dataset_id, n)
