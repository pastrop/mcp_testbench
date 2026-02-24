"""API route definitions."""

import logging
from fastapi import APIRouter, HTTPException, Path, Query
from typing import Any, Dict

from app.core.config import settings

# Configure logging
logger = logging.getLogger(__name__)
from app.schemas.component_spec import UIComponentSpec
from app.schemas.contract import ContractData, ContractListResponse
from app.services.ai_service import AIService
from app.services.contract_service import ContractService
from app.services.demo_specs import DEMO_SPEC

router = APIRouter()

# Initialize services
contract_service = ContractService()
ai_service = AIService()


@router.get("/contracts", response_model=ContractListResponse)
async def list_contracts() -> ContractListResponse:
    """
    List all available contract files.

    Returns:
        List of contract filenames and count
    """
    return contract_service.list_contracts()


@router.get("/contracts/{filename}", response_model=ContractData)
async def get_contract(
    filename: str = Path(..., description="Contract filename")
) -> ContractData:
    """
    Get raw contract data by filename.

    Args:
        filename: Name of the contract JSON file

    Returns:
        Contract data with filename and parsed JSON

    Raises:
        HTTPException: 404 if contract not found, 400 if invalid JSON
    """
    try:
        return contract_service.load_contract(filename)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Contract not found: {filename}")
    except ValueError as e:
        logger.error(f"Failed to load contract {filename}: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/contracts/{filename}/data", response_model=Dict[str, Any])
async def get_contract_data(
    filename: str = Path(..., description="Contract filename")
) -> Dict[str, Any]:
    """
    Get raw contract JSON data only.

    Args:
        filename: Name of the contract JSON file

    Returns:
        Raw contract JSON data

    Raises:
        HTTPException: 404 if contract not found
    """
    try:
        return contract_service.get_contract_data(filename)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Contract not found: {filename}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/generate-ui", response_model=UIComponentSpec)
async def generate_ui_specification(
    filename: str = Query(..., description="Contract filename to generate UI for")
) -> UIComponentSpec:
    """
    Generate UI component specification for a contract using AI.

    Args:
        filename: Name of the contract JSON file

    Returns:
        Generated UIComponentSpec with component structure

    Raises:
        HTTPException: 404 if contract not found, 500 if generation fails
    """
    try:
        # Load contract data
        contract_data = contract_service.get_contract_data(filename)

        # Use demo mode if enabled (for testing without API credits)
        if settings.demo_mode:
            spec_dict = {**DEMO_SPEC, "contract_id": filename}
            return UIComponentSpec(**spec_dict)

        # Generate UI spec using AI
        ui_spec = ai_service.generate_ui_spec_sync(contract_data, filename)

        return ui_spec

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Contract not found: {filename}")
    except ValueError as e:
        logger.error(f"UI generation failed for {filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"UI generation failed: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during UI generation for {filename}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Unexpected error during UI generation: {e}"
        )


@router.get("/health")
async def health_check() -> Dict[str, str]:
    """
    Health check endpoint.

    Returns:
        Status message
    """
    return {"status": "healthy", "service": "ui-renderer-backend"}
