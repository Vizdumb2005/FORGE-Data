"""Cells router — CRUD for cells within a workspace."""

from fastapi import APIRouter
from sqlalchemy import select

from app.dependencies import CurrentUser, DBSession
from app.models.cell import Cell
from app.schemas.cell import CellCreate, CellRead, CellUpdate
from app.services import workspace_service

router = APIRouter()


@router.get(
    "/{workspace_id}/cells",
    response_model=list[CellRead],
    summary="List all cells in a workspace",
)
async def list_cells(workspace_id: str, current_user: CurrentUser, db: DBSession) -> list[CellRead]:
    await workspace_service.get_workspace_for_user(db, workspace_id, current_user.id)
    result = await db.execute(
        select(Cell)
        .where(Cell.workspace_id == workspace_id)
        .order_by(Cell.position_y, Cell.position_x)
    )
    return [CellRead.model_validate(c) for c in result.scalars().all()]


@router.post(
    "/{workspace_id}/cells",
    response_model=CellRead,
    status_code=201,
    summary="Create a new cell",
)
async def create_cell(
    workspace_id: str,
    payload: CellCreate,
    current_user: CurrentUser,
    db: DBSession,
) -> CellRead:
    await workspace_service.get_workspace_for_user(db, workspace_id, current_user.id)
    cell = Cell(
        workspace_id=workspace_id,
        cell_type=payload.cell_type.value,
        language=payload.language.value,
        content=payload.content,
        position_x=payload.position_x,
        position_y=payload.position_y,
        width=payload.width,
        height=payload.height,
    )
    db.add(cell)
    await db.flush()
    await db.refresh(cell)
    return CellRead.model_validate(cell)


@router.get(
    "/{workspace_id}/cells/{cell_id}",
    response_model=CellRead,
    summary="Get a single cell",
)
async def get_cell(
    workspace_id: str, cell_id: str, current_user: CurrentUser, db: DBSession
) -> CellRead:
    await workspace_service.get_workspace_for_user(db, workspace_id, current_user.id)
    cell = await _get_cell_or_404(db, workspace_id, cell_id)
    return CellRead.model_validate(cell)


@router.patch(
    "/{workspace_id}/cells/{cell_id}",
    response_model=CellRead,
    summary="Update cell content or layout",
)
async def update_cell(
    workspace_id: str,
    cell_id: str,
    payload: CellUpdate,
    current_user: CurrentUser,
    db: DBSession,
) -> CellRead:
    await workspace_service.get_workspace_for_user(db, workspace_id, current_user.id)
    cell = await _get_cell_or_404(db, workspace_id, cell_id)

    if payload.content is not None:
        cell.content = payload.content
    if payload.position_x is not None:
        cell.position_x = payload.position_x
    if payload.position_y is not None:
        cell.position_y = payload.position_y
    if payload.width is not None:
        cell.width = payload.width
    if payload.height is not None:
        cell.height = payload.height
    if payload.language is not None:
        cell.language = payload.language.value
    if payload.cell_type is not None:
        cell.cell_type = payload.cell_type.value

    await db.flush()
    await db.refresh(cell)
    return CellRead.model_validate(cell)


@router.delete(
    "/{workspace_id}/cells/{cell_id}",
    status_code=204,
    summary="Delete a cell",
)
async def delete_cell(
    workspace_id: str, cell_id: str, current_user: CurrentUser, db: DBSession
) -> None:
    await workspace_service.get_workspace_for_user(db, workspace_id, current_user.id)
    cell = await _get_cell_or_404(db, workspace_id, cell_id)
    await db.delete(cell)
    await db.flush()


async def _get_cell_or_404(db: DBSession, workspace_id: str, cell_id: str) -> Cell:
    from app.core.exceptions import NotFoundException

    result = await db.execute(
        select(Cell).where(Cell.id == cell_id, Cell.workspace_id == workspace_id)
    )
    cell = result.scalar_one_or_none()
    if cell is None:
        raise NotFoundException("Cell", cell_id)
    return cell
