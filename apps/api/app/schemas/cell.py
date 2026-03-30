"""Cell Pydantic schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.cell import CellLanguage, CellType


class CellCreate(BaseModel):
    cell_type: CellType = CellType.code
    language: CellLanguage = CellLanguage.python
    content: str = ""
    position_x: int = Field(default=0, ge=0)
    position_y: int = Field(default=0, ge=0)
    width: int = Field(default=800, ge=1, le=5000)
    height: int = Field(default=300, ge=1, le=5000)


class CellUpdate(BaseModel):
    content: str | None = None
    position_x: int | None = Field(default=None, ge=0)
    position_y: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, ge=1, le=5000)
    height: int | None = Field(default=None, ge=1, le=5000)
    language: CellLanguage | None = None
    cell_type: CellType | None = None


class CellOutput(BaseModel):
    """Structured cell execution output."""

    status: str  # "ok" | "error"
    output_type: str | None = None  # "stream" | "display_data" | "execute_result" | "error"
    text: str | None = None
    data: dict[str, Any] | None = None  # mime-type keyed (text/html, image/png, etc.)
    ename: str | None = None  # error class name
    evalue: str | None = None  # error message
    traceback: list[str] | None = None
    execution_count: int | None = None


class CellRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    cell_type: str
    language: str
    content: str
    output: dict[str, Any] | None
    position_x: int
    position_y: int
    width: int
    height: int
    kernel_id: str | None
    last_executed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ExecuteRequest(BaseModel):
    """Request body for POST /workspaces/{ws_id}/cells/{cell_id}/execute."""

    source: str | None = None  # override content; if None, execute cell.content
    kernel_id: str | None = None  # reuse an existing Jupyter kernel


class ExecuteResponse(BaseModel):
    cell_id: str
    output: CellOutput
    kernel_id: str
