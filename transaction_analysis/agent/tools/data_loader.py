"""Data loading tools for contract and transaction data."""

import json
import pandas as pd
from typing import Dict, List, Optional


def load_contract_data(file_path: str) -> Dict:
    """
    Load and parse contract JSON file.

    Args:
        file_path: Path to contract JSON file

    Returns:
        Dictionary with contract data including:
        - raw_data: Complete contract data
        - card_fees: Card payment fee structures
        - apm_fees: Alternative payment method fees
        - outgoing_fees: Payout/withdrawal fees
        - currencies: List of supported currencies
        - regions: List of covered regions
        - payment_methods: List of payment methods
    """
    with open(file_path, 'r') as f:
        data = json.load(f)

    # Extract metadata
    currencies = set()
    regions = set()
    payment_methods = set()

    # Parse card fees
    for key, value in data.get("card_fees", {}).items():
        if isinstance(value, dict):
            currencies.add(value.get("currency"))
            regions.add(value.get("region"))
            payment_methods.add("card")

    # Parse APM fees
    for key, value in data.get("apm_open_banking_fees", {}).items():
        if isinstance(value, dict) and "currency" in value:
            currencies.add(value.get("currency"))
            regions.add(value.get("region"))
            # Extract payment method from key
            method = key.split("_")[0]
            payment_methods.add(method)

    # Parse outgoing fees
    for category, methods in data.get("outgoing_fees", {}).items():
        if isinstance(methods, dict):
            payment_methods.add(category)
            for method, details in methods.items():
                if isinstance(details, dict) and "currency" in details:
                    currencies.add(details.get("currency"))
                    regions.add(details.get("region"))

    return {
        "raw_data": data,
        "card_fees": data.get("card_fees", {}),
        "apm_fees": data.get("apm_open_banking_fees", {}),
        "outgoing_fees": data.get("outgoing_fees", {}),
        "settlement_fees": data.get("settlement_fees", {}),
        "crypto_fees": data.get("incoming_fees", {}).get("crypto", {}),
        "excessive_cb_fees": data.get("excessive_chargeback_fees", {}),
        "fx_fees": data.get("currency_exchange_fees", {}),
        "currencies": sorted([c for c in currencies if c]),
        "regions": sorted([r for r in regions if r]),
        "payment_methods": sorted(list(payment_methods))
    }


def load_transaction_data(
    file_path: str,
    limit: Optional[int] = None,
    offset: int = 0,
    filters: Optional[Dict] = None
) -> Dict:
    """
    Load transaction data from CSV with optional filtering.

    Args:
        file_path: Path to CSV file
        limit: Maximum number of rows to load (optional)
        offset: Number of rows to skip
        filters: Dictionary of column filters, e.g., {"status": "approved"}

    Returns:
        Dictionary with:
        - transactions: List of transaction records
        - total_count: Total number of transactions loaded
        - columns: List of column names
        - has_more: Boolean indicating if more data available
    """
    # Read CSV with chunking for large files
    try:
        if limit:
            df = pd.read_csv(file_path, skiprows=range(1, offset + 1) if offset > 0 else None, nrows=limit)
        else:
            df = pd.read_csv(file_path, skiprows=range(1, offset + 1) if offset > 0 else None)
    except Exception as e:
        return {
            "error": f"Failed to load CSV: {str(e)}",
            "transactions": [],
            "total_count": 0,
            "columns": [],
            "has_more": False
        }

    # Apply filters
    if filters:
        for column, value in filters.items():
            if column in df.columns:
                df = df[df[column] == value]

    # Convert to list of dicts, handling NaN values
    transactions = df.fillna("").to_dict('records')

    return {
        "transactions": transactions,
        "total_count": len(transactions),
        "columns": list(df.columns),
        "has_more": limit is not None and len(df) == limit
    }


def get_transaction_batch(
    file_path: str,
    batch_size: int = 100,
    batch_number: int = 0
) -> Dict:
    """
    Get a specific batch of transactions.

    Args:
        file_path: Path to CSV file
        batch_size: Number of transactions per batch
        batch_number: Which batch to retrieve (0-indexed)

    Returns:
        Same format as load_transaction_data
    """
    offset = batch_number * batch_size
    return load_transaction_data(file_path, limit=batch_size, offset=offset)
