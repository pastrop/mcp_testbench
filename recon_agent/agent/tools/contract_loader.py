import json
from pathlib import Path
from decimal import Decimal
from typing import Dict, Any
from agent.models.contract import DintaresContract


def discover_contract_file(data_dir: str = "data") -> str:
    """
    Automatically discover contract JSON file in the data directory.

    Args:
        data_dir: Directory to search for contract files (default: "data")

    Returns:
        Path to the discovered contract file

    Raises:
        FileNotFoundError: If no contract files found
        ValueError: If multiple contract files found (user must specify)
    """
    data_path = Path(data_dir)

    if not data_path.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}/")

    # Find all JSON files in data directory
    json_files = list(data_path.glob("*.json"))

    if not json_files:
        raise FileNotFoundError(
            f"No JSON contract files found in {data_dir}/\n"
            f"Please add a contract JSON file or specify path with --contract"
        )

    if len(json_files) == 1:
        return str(json_files[0])

    # Multiple files - list them for user to choose
    file_list = "\n".join([f"  - {f.name}" for f in json_files])
    raise ValueError(
        f"Multiple contract files found in {data_dir}/:\n{file_list}\n"
        f"Please specify one using --contract <filename>"
    )


def load_contract(file_path: str) -> DintaresContract:
    """
    Load and parse DINTARES contract from JSON file.

    Args:
        file_path: Path to the contract JSON file

    Returns:
        DintaresContract: Parsed and validated contract

    Raises:
        FileNotFoundError: If contract file doesn't exist
        ValueError: If contract data is invalid or missing required fields
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Contract file not found: {file_path}")

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in contract file: {e}")

    # Extract fee information from the fees_and_rates array
    fees_and_rates = data.get('fees_and_rates', [])
    if not fees_and_rates:
        raise ValueError("No fees_and_rates found in contract")

    # Build fee lookup dictionary
    fee_lookup: Dict[str, Any] = {}
    for fee in fees_and_rates:
        fee_name = fee.get('fee_name', '').lower()
        fee_lookup[fee_name] = fee

    # Extract specific fees
    remuneration = _find_fee(fee_lookup, [
        'remuneration', 'processing', 'commission', 'payment processing'
    ])
    chargeback = _find_fee(fee_lookup, ['chargeback'])
    refund = _find_fee(fee_lookup, ['refund'])
    rolling_reserve = _find_fee(fee_lookup, ['rolling reserve', 'rolling_reserve', 'rr'])

    # Extract payment methods
    payment_methods = data.get('payment_methods', {})

    # Build contract model with parsed amounts
    contract_data = {
        'remuneration_rate': _parse_fee_amount(remuneration) if remuneration else 0.038,
        'chargeback_cost': _parse_fee_amount(chargeback) if chargeback else 50,
        'refund_cost': _parse_fee_amount(refund) if refund else 5,
        'rolling_reserve_rate': _parse_fee_amount(rolling_reserve) if rolling_reserve else 0.1,
        'rolling_reserve_days': rolling_reserve.get('holding_period_days', 180) if rolling_reserve else 180,
        'rolling_reserve_cap': _parse_rr_cap(rolling_reserve) if rolling_reserve else 37500,
        'chargeback_limit': _parse_fee_amount(_find_fee(fee_lookup, ['chargeback limit'])) if _find_fee(fee_lookup, ['chargeback limit']) else 0.005,
        'minimum_payment': _parse_fee_amount(_find_fee(fee_lookup, ['minimum payment', 'minimum'])) if _find_fee(fee_lookup, ['minimum payment', 'minimum']) else 1,
        'monthly_card_limit': _parse_fee_amount(_find_fee(fee_lookup, ['monthly card limit', 'monthly limit'])) if _find_fee(fee_lookup, ['monthly card limit', 'monthly limit']) else 5000,
        'supported_cards': payment_methods.get('supported_cards', []),
        'currencies': payment_methods.get('currencies', []),
    }

    try:
        return DintaresContract(**contract_data)
    except Exception as e:
        raise ValueError(f"Failed to create contract model: {e}")


def _parse_rr_cap(fee_data: Dict[str, Any]) -> float:
    """
    Parse rolling reserve cap from various formats.

    Checks:
    - 'maximum_cap' field
    - 'max_cap' field
    - 'conditions' field for "maximum X EUR" pattern

    Args:
        fee_data: Rolling reserve fee dictionary

    Returns:
        Cap amount as float (default: 37500)
    """
    # Check for explicit cap fields
    if 'maximum_cap' in fee_data:
        return float(fee_data['maximum_cap'])
    if 'max_cap' in fee_data:
        return float(fee_data['max_cap'])

    # Parse from conditions text
    conditions = str(fee_data.get('conditions', ''))

    # Look for patterns like "maximum 37,500 EUR" or "max 37500"
    import re
    patterns = [
        r'maximum\s+([\d,]+)',
        r'max\s+([\d,]+)',
        r'cap\s+([\d,]+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, conditions.lower())
        if match:
            # Remove commas and convert to float
            cap_str = match.group(1).replace(',', '')
            try:
                return float(cap_str)
            except ValueError:
                continue

    # Default cap
    return 37500.0


def _parse_fee_amount(fee_data: Dict[str, Any]) -> float:
    """
    Parse fee amount from various formats.

    Handles:
    - Decimal values in 'amount_decimal' field
    - Percentage strings: "3.8%" → 0.038
    - Currency strings: "50 EUR" → 50
    - Plain numbers: 50 → 50

    Args:
        fee_data: Fee dictionary with 'amount' or 'amount_decimal'

    Returns:
        Parsed amount as float
    """
    # Prefer amount_decimal if available
    if 'amount_decimal' in fee_data:
        return float(fee_data['amount_decimal'])

    # Parse amount string
    amount_str = str(fee_data.get('amount', 0))

    # Remove common symbols
    cleaned = amount_str.strip().replace('EUR', '').replace('GBP', '').replace('USD', '').replace('AUD', '').replace('NOK', '').strip()

    # Handle percentage
    if '%' in cleaned:
        # Remove % and divide by 100
        cleaned = cleaned.replace('%', '').strip()
        try:
            return float(cleaned) / 100.0
        except ValueError:
            return 0.0

    # Handle plain number
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _find_fee(fee_lookup: Dict[str, Any], search_terms: list[str]) -> Dict[str, Any]:
    """
    Find a fee by searching for any of the given terms.

    Args:
        fee_lookup: Dictionary of fees keyed by lowercase name
        search_terms: List of terms to search for

    Returns:
        Dict with fee data, or empty dict if not found
    """
    for term in search_terms:
        for fee_name, fee_data in fee_lookup.items():
            if term.lower() in fee_name.lower():
                return fee_data
    return {}


def validate_contract(contract: DintaresContract) -> tuple[bool, list[str]]:
    """
    Validate contract data for completeness and correctness.

    Args:
        contract: DintaresContract to validate

    Returns:
        Tuple of (is_valid: bool, errors: List[str])
    """
    errors = []

    # Check rates are within valid ranges
    if contract.remuneration_rate <= 0 or contract.remuneration_rate >= 1:
        errors.append(f"Invalid remuneration rate: {contract.remuneration_rate} (expected 0-1)")

    if contract.rolling_reserve_rate <= 0 or contract.rolling_reserve_rate >= 1:
        errors.append(f"Invalid rolling reserve rate: {contract.rolling_reserve_rate} (expected 0-1)")

    # Check costs are positive
    if contract.chargeback_cost <= 0:
        errors.append(f"Invalid chargeback cost: {contract.chargeback_cost} (expected > 0)")

    if contract.refund_cost <= 0:
        errors.append(f"Invalid refund cost: {contract.refund_cost} (expected > 0)")

    # Check RR cap is positive
    if contract.rolling_reserve_cap <= 0:
        errors.append(f"Invalid RR cap: {contract.rolling_reserve_cap} (expected > 0)")

    # Check RR days is reasonable
    if contract.rolling_reserve_days <= 0 or contract.rolling_reserve_days > 365:
        errors.append(f"Invalid RR days: {contract.rolling_reserve_days} (expected 1-365)")

    return (len(errors) == 0, errors)
