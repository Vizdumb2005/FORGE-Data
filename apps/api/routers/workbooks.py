from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class Cell(BaseModel):
    id: str
    type: str  # "python" | "sql" | "markdown" | "ai"
    source: str
    output: dict | None = None


class WorkbookBase(BaseModel):
    name: str
    cells: list[Cell] = []


class WorkbookRead(WorkbookBase):
    id: str
    owner_id: str
    created_at: str
    updated_at: str


class ExecuteCellRequest(BaseModel):
    cell_id: str
    source: str
    kernel_id: str | None = None


class ExecuteCellResponse(BaseModel):
    cell_id: str
    output: dict
    kernel_id: str


@router.get("/", response_model=list[WorkbookRead])
async def list_workbooks() -> list[WorkbookRead]:
    """List all workbooks for the current user."""
    return []


@router.post("/", response_model=WorkbookRead, status_code=201)
async def create_workbook(payload: WorkbookBase) -> WorkbookRead:
    """Create a new workbook."""
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.get("/{workbook_id}", response_model=WorkbookRead)
async def get_workbook(workbook_id: str) -> WorkbookRead:
    """Retrieve a single workbook by ID."""
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.put("/{workbook_id}", response_model=WorkbookRead)
async def update_workbook(workbook_id: str, payload: WorkbookBase) -> WorkbookRead:
    """Save updates to a workbook."""
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.delete("/{workbook_id}", status_code=204)
async def delete_workbook(workbook_id: str) -> None:
    """Delete a workbook."""
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.post("/{workbook_id}/execute", response_model=ExecuteCellResponse)
async def execute_cell(workbook_id: str, payload: ExecuteCellRequest) -> ExecuteCellResponse:
    """Execute a cell in the Jupyter kernel and return the output."""
    # TODO: connect to Jupyter Kernel Gateway, forward execution
    raise HTTPException(status_code=501, detail="Not implemented yet")
