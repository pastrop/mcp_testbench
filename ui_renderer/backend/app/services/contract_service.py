"""Service for loading and managing contract data."""

import json
from pathlib import Path
from typing import Dict, List, Any

from app.core.config import settings
from app.schemas.contract import ContractData, ContractListResponse


class ContractService:
    """Service for contract data operations."""

    def __init__(self):
        """Initialize the contract service."""
        self.contracts_dir = settings.contracts_directory

    def list_contracts(self) -> ContractListResponse:
        """List all available contract files."""
        if not self.contracts_dir.exists():
            return ContractListResponse(contracts=[], count=0)

        contract_files = [
            f.name for f in self.contracts_dir.glob("*.json") if f.is_file()
        ]
        contract_files.sort()

        return ContractListResponse(contracts=contract_files, count=len(contract_files))

    def load_contract(self, filename: str) -> ContractData:
        """
        Load a specific contract by filename.

        Args:
            filename: Name of the contract JSON file

        Returns:
            ContractData with parsed JSON

        Raises:
            FileNotFoundError: If contract file doesn't exist
            ValueError: If JSON is invalid
        """
        file_path = self.contracts_dir / filename

        if not file_path.exists():
            raise FileNotFoundError(f"Contract file not found: {filename}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in contract file: {e}")

        return ContractData(filename=filename, data=data)

    def get_contract_data(self, filename: str) -> Dict[str, Any]:
        """
        Get raw contract data as dictionary.

        Args:
            filename: Name of the contract JSON file

        Returns:
            Dictionary with contract data
        """
        contract = self.load_contract(filename)
        return contract.data
