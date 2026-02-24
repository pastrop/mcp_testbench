"""Contract data schemas."""

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ContractData(BaseModel):
    """Raw contract data from JSON file."""

    filename: str = Field(..., description="Original filename")
    data: Dict[str, Any] = Field(..., description="Parsed contract JSON data")


class ContractListResponse(BaseModel):
    """Response for listing available contracts."""

    contracts: List[str] = Field(..., description="List of available contract filenames")
    count: int = Field(..., description="Total number of contracts")
