from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class ConnectorBase(BaseModel):
    name: str
    type: Literal["postgres", "mysql", "bigquery", "snowflake", "csv", "parquet", "rest"]
    config: dict  # encrypted at rest


class ConnectorRead(ConnectorBase):
    id: str
    owner_id: str


class SchemaTable(BaseModel):
    name: str
    columns: list[dict]


@router.get("/", response_model=list[ConnectorRead])
async def list_connectors() -> list[ConnectorRead]:
    """List all data connectors for the current user."""
    return []


@router.post("/", response_model=ConnectorRead, status_code=201)
async def create_connector(payload: ConnectorBase) -> ConnectorRead:
    """Register a new data connector."""
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.post("/{connector_id}/test")
async def test_connector(connector_id: str) -> dict:
    """Test connectivity for a registered connector."""
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.get("/{connector_id}/schema", response_model=list[SchemaTable])
async def get_schema(connector_id: str) -> list[SchemaTable]:
    """Return the schema (tables + columns) for a connector."""
    raise HTTPException(status_code=501, detail="Not implemented yet")


@router.delete("/{connector_id}", status_code=204)
async def delete_connector(connector_id: str) -> None:
    """Remove a connector."""
    raise HTTPException(status_code=501, detail="Not implemented yet")
