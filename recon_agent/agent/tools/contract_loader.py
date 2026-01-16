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

    # Extract fee information - handle multiple contract formats
    fee_lookup: Dict[str, Any] = {}

    # Format 1: Single "fees_and_rates" array or nested dict
    if 'fees_and_rates' in data:
        fees_and_rates = data.get('fees_and_rates', [])

        # Check if it's a list (Format 1A) or dict (Format 1B/1C - nested)
        if isinstance(fees_and_rates, list):
            # Format 1A: Array of fee objects
            for fee in fees_and_rates:
                fee_name = fee.get('fee_name', '').lower()
                fee_lookup[fee_name] = fee
        elif isinstance(fees_and_rates, dict):
            # Check what's in the dictionary - nested dicts or arrays
            for category_key, category_value in fees_and_rates.items():
                if isinstance(category_value, list):
                    # Format 1C: Dictionary of arrays (e.g., SKINVEX)
                    # Structure: fees_and_rates > {processing_fees: [...], reserve_requirements: [...]}
                    for fee in category_value:
                        if isinstance(fee, dict):
                            fee_name = fee.get('fee_name', fee.get('limit_name', '')).lower()
                            if fee_name:
                                fee_lookup[fee_name] = fee
                elif isinstance(category_value, dict):
                    # Format 1B: Nested dictionary structure (e.g., QUANTESSA, RENAMESTRA)
                    # Structure: fees_and_rates > category > fee_name > data
                    for fee_key, fee_data in category_value.items():
                        if isinstance(fee_data, dict):
                            # Use fee_name if available, otherwise use the key itself
                            if 'fee_name' in fee_data:
                                fee_name = fee_data.get('fee_name', '').lower()
                            else:
                                # Use the dictionary key as the fee name (RENAMESTRA format)
                                fee_name = fee_key.lower()
                            fee_lookup[fee_name] = fee_data

    # Format 2: Separate arrays for each fee type
    else:
        # Merge all fee arrays into lookup
        for key in ['payment_processing_fees', 'processing_fees', 'chargeback_fees',
                    'refund_fees', 'rolling_reserve', 'limits_and_thresholds',
                    'payment_processing']:
            if key in data:
                for fee in data[key]:
                    fee_name = fee.get('fee_name', '').lower()
                    if not fee_name:
                        fee_name = fee.get('limit_type', '').lower()
                    fee_lookup[fee_name] = fee

    if not fee_lookup:
        raise ValueError("No fee information found in contract")

    # Extract specific fees
    remuneration = _find_fee(fee_lookup, [
        'remuneration', 'processing', 'commission', 'payment processing', 'internet acquiring', 'acquiring'
    ])
    chargeback = _find_fee(fee_lookup, ['chargeback'])
    refund = _find_fee(fee_lookup, ['refund'])
    rolling_reserve = _find_fee(fee_lookup, ['rolling reserve', 'rolling_reserve', 'rr'])

    # Check if chargeback/refund are nested in remuneration (QUANTESSA format)
    # Only use nested values if we don't have a valid amount already
    if remuneration:
        # Check if chargeback has a valid amount, if not, look in remuneration
        if not chargeback or ('amount' not in chargeback and 'amount_decimal' not in chargeback and 'percentage' not in chargeback):
            if 'charge_back_fee' in remuneration:
                chargeback = {'amount': remuneration['charge_back_fee']}
            elif 'chargeback_fee' in remuneration:
                chargeback = {'amount': remuneration['chargeback_fee']}

        # Check if refund has a valid amount, if not, look in remuneration
        if not refund or ('amount' not in refund and 'amount_decimal' not in refund and 'percentage' not in refund):
            if 'refund_fee' in remuneration:
                refund = {'amount': remuneration['refund_fee']}

    # Extract payment methods and currencies - handle different formats
    supported_cards = []
    currencies = []

    # Extract supported cards
    if 'payment_methods' in data:
        if isinstance(data['payment_methods'], dict):
            # Format: payment_methods: {supported_cards: [...]}
            supported_cards = data['payment_methods'].get('supported_cards', [])
        elif isinstance(data['payment_methods'], list):
            # Check if list contains dictionaries with 'method' or 'card_types' field
            payment_methods_list = data['payment_methods']
            if payment_methods_list and isinstance(payment_methods_list[0], dict):
                # Extract 'card_types' if available (SKINVEX), otherwise 'method' (SKINRIFF)
                supported_cards = []
                for pm in payment_methods_list:
                    if isinstance(pm, dict):
                        if 'card_types' in pm:
                            # SKINVEX format: payment_methods: [{card_types: [...]}]
                            supported_cards.extend(pm['card_types'])
                        else:
                            # SKINRIFF format: payment_methods: [{method: "..."}]
                            supported_cards.append(pm.get('method', pm.get('type', str(pm))))
            else:
                # Format: payment_methods: [...] (simple string list)
                supported_cards = payment_methods_list

    # Check security_requirements for card types as fallback
    if not supported_cards and 'security_requirements' in data:
        security = data['security_requirements']
        if isinstance(security, dict):
            supported_cards = security.get('card_types', [])

    # Extract currencies
    if 'payment_methods' in data and isinstance(data['payment_methods'], dict):
        # Format 1: payment_methods: {currencies: [...]}
        currencies = data['payment_methods'].get('currencies', [])
    elif 'supported_currencies' in data:
        supported_curr = data['supported_currencies']
        if isinstance(supported_curr, list):
            # Check if it's a list of strings or list with a dictionary
            if supported_curr and isinstance(supported_curr[0], dict):
                # Format: supported_currencies: [{authorization_currencies: [...]}] (SKINVEX)
                currencies = supported_curr[0].get('authorization_currencies',
                                                   supported_curr[0].get('currencies', []))
            else:
                # Format 2: supported_currencies: [...]
                currencies = supported_curr
        elif isinstance(supported_curr, dict):
            # Format 3: supported_currencies: {authorization_currencies: [...]}
            currencies = supported_curr.get('authorization_currencies', [])
            if not currencies:
                currencies = supported_curr.get('currencies', [])

    # Check nested locations for supported_currencies (QUANTESSA format)
    if not currencies and 'fees_and_rates' in data and isinstance(data['fees_and_rates'], dict):
        if 'settlement_details' in data['fees_and_rates']:
            settlement = data['fees_and_rates']['settlement_details']
            if isinstance(settlement, dict) and 'supported_currencies' in settlement:
                currencies = settlement['supported_currencies']

        # Check approved_terms for currencies (RENAMESTRA format)
        if not currencies and 'approved_terms' in data['fees_and_rates']:
            approved_terms = data['fees_and_rates']['approved_terms']
            if isinstance(approved_terms, dict) and 'currencies' in approved_terms:
                currencies = approved_terms['currencies']

    # Extract limits from transaction_limits or payment_conditions if present
    minimum_payment_value = 1
    monthly_card_limit_value = 5000

    # Check payment_conditions for minimum_payment
    if 'payment_conditions' in data:
        payment_cond = data['payment_conditions']
        if isinstance(payment_cond, dict):
            minimum_payment_value = payment_cond.get('minimum_payment', 1)

    # Check transaction_limits for monthly_limit_per_card
    if 'transaction_limits' in data:
        tx_limits = data['transaction_limits']
        if isinstance(tx_limits, dict):
            monthly_card_limit_value = tx_limits.get('monthly_limit_per_card', 5000)

    # Build contract model with parsed amounts
    contract_data = {
        'remuneration_rate': _parse_fee_amount(remuneration) if remuneration else 0.038,
        'chargeback_cost': _parse_fee_amount(chargeback) if chargeback else 50,
        'refund_cost': _parse_fee_amount(refund) if refund else 5,
        'rolling_reserve_rate': _parse_fee_amount(rolling_reserve) if rolling_reserve else 0.1,
        'rolling_reserve_days': _parse_rr_days(rolling_reserve) if rolling_reserve else 180,
        'rolling_reserve_cap': _parse_rr_cap(rolling_reserve) if rolling_reserve else 37500,
        'chargeback_limit': _parse_fee_amount(_find_fee(fee_lookup, ['chargeback limit'])) if _find_fee(fee_lookup, ['chargeback limit']) else 0.005,
        'minimum_payment': minimum_payment_value,
        'monthly_card_limit': monthly_card_limit_value,
        'supported_cards': supported_cards,
        'currencies': currencies,
    }

    try:
        return DintaresContract(**contract_data)
    except Exception as e:
        raise ValueError(f"Failed to create contract model: {e}")


def _parse_rr_days(fee_data: Dict[str, Any]) -> int:
    """
    Parse rolling reserve holding period from various formats.

    Checks:
    - 'holding_period_days' field (numeric)
    - 'duration' field (string like "180 days" or numeric)
    - 'holding_period' field (string like "180 days" or numeric)

    Args:
        fee_data: Rolling reserve fee dictionary

    Returns:
        Days as integer (default: 180)
    """
    # Check for numeric holding_period_days field
    if 'holding_period_days' in fee_data:
        return int(fee_data['holding_period_days'])

    # Check for duration or holding_period fields (may be string or number)
    for field_name in ['duration', 'holding_period']:
        if field_name in fee_data:
            field_value = fee_data[field_name]

            # If it's already a number
            if isinstance(field_value, (int, float)):
                return int(field_value)

            # If it's a string, parse it
            if isinstance(field_value, str):
                # Extract numeric value from strings like "180 days"
                import re
                match = re.search(r'(\d+)', field_value)
                if match:
                    return int(match.group(1))

    # Default
    return 180


def _parse_rr_cap(fee_data: Dict[str, Any]) -> float:
    """
    Parse rolling reserve cap from various formats.

    Checks:
    - 'maximum_cap' field
    - 'max_cap' field
    - 'maximum_amount' field
    - 'maximum_reserve' field
    - 'conditions' field for "maximum X EUR" pattern

    Args:
        fee_data: Rolling reserve fee dictionary

    Returns:
        Cap amount as float (default: 37500)
    """
    # Check for explicit cap fields - use _parse_fee_amount for consistent parsing
    if 'maximum_cap' in fee_data:
        cap_value = fee_data['maximum_cap']
        # If it's a string with currency/comma, parse it
        if isinstance(cap_value, str):
            return _parse_fee_amount({'amount': cap_value})
        return float(cap_value)
    if 'max_cap' in fee_data:
        cap_value = fee_data['max_cap']
        if isinstance(cap_value, str):
            return _parse_fee_amount({'amount': cap_value})
        return float(cap_value)
    if 'maximum_amount' in fee_data:
        cap_value = fee_data['maximum_amount']
        if isinstance(cap_value, str):
            return _parse_fee_amount({'amount': cap_value})
        return float(cap_value)
    if 'maximum_reserve' in fee_data:
        cap_value = fee_data['maximum_reserve']
        if isinstance(cap_value, str):
            return _parse_fee_amount({'amount': cap_value})
        return float(cap_value)

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
    - Decimal values in 'amount_decimal', 'rate_decimal', 'percentage', 'amount_percentage' fields
    - Percentage strings: "3.8%" → 0.038
    - Currency strings: "50 EUR" → 50
    - Numbers with comma separators: "37,500 EUR" → 37500
    - Plain numbers: 50 → 50

    Args:
        fee_data: Fee dictionary with 'amount', 'rate', 'amount_decimal', 'rate_decimal', 'percentage', or 'amount_percentage'

    Returns:
        Parsed amount as float
    """
    # Prefer decimal fields if available (already as numbers)
    if 'amount_decimal' in fee_data:
        return float(fee_data['amount_decimal'])

    if 'rate_decimal' in fee_data:
        return float(fee_data['rate_decimal'])

    if 'amount_percentage' in fee_data:
        return float(fee_data['amount_percentage'])

    if 'percentage' in fee_data:
        percentage_value = fee_data['percentage']
        if isinstance(percentage_value, (int, float)):
            return float(percentage_value)

    # Parse string fields (amount or rate)
    # Check for 'rate' field first (RENAMESTRA format), then 'amount'
    if 'rate' in fee_data:
        amount_str = str(fee_data['rate'])
    elif 'amount' in fee_data:
        amount_str = str(fee_data['amount'])
    else:
        amount_str = '0'

    # Remove common symbols and spaces
    cleaned = (amount_str.strip()
               .replace('EUR', '')
               .replace('GBP', '')
               .replace('USD', '')
               .replace('AUD', '')
               .replace('NOK', '')
               .replace(',', '')  # Remove comma separators
               .strip())

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
