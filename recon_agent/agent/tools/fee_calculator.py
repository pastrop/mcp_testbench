from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional, Any
from agent.models.contract import DintaresContract


def calculate_remuneration(
    amount: Decimal,
    rate: Decimal = Decimal("0.038")
) -> Dict[str, any]:
    """
    Calculate remuneration fee (3.8% of transaction amount).

    Args:
        amount: Transaction amount
        rate: Remuneration rate (default: 0.038 = 3.8%)

    Returns:
        Dictionary with:
        {
            "fee": Decimal,
            "breakdown": {
                "amount": Decimal,
                "rate": Decimal,
                "calculation": str
            }
        }
    """
    fee = (amount * rate).quantize(Decimal("0.01"), ROUND_HALF_UP)

    return {
        "fee": fee,
        "breakdown": {
            "amount": amount,
            "rate": rate,
            "calculation": f"{amount} × {rate} = {fee}"
        }
    }


def calculate_chargeback_fee(
    is_chargeback: bool,
    cost: Decimal = Decimal("50.00")
) -> Dict[str, any]:
    """
    Calculate chargeback fee (flat €50 if chargeback occurred).

    Args:
        is_chargeback: Whether this transaction has a chargeback
        cost: Chargeback cost (default: €50)

    Returns:
        Dictionary with fee and breakdown
    """
    fee = cost if is_chargeback else Decimal("0.00")

    return {
        "fee": fee,
        "breakdown": {
            "is_chargeback": is_chargeback,
            "cost": cost,
            "calculation": f"Chargeback: {'Yes' if is_chargeback else 'No'} → {fee}"
        }
    }


def calculate_refund_fee(
    is_refund: bool,
    cost: Decimal = Decimal("5.00")
) -> Dict[str, any]:
    """
    Calculate refund fee (flat €5 if refund occurred).

    Args:
        is_refund: Whether this transaction has a refund
        cost: Refund cost (default: €5)

    Returns:
        Dictionary with fee and breakdown
    """
    fee = cost if is_refund else Decimal("0.00")

    return {
        "fee": fee,
        "breakdown": {
            "is_refund": is_refund,
            "cost": cost,
            "calculation": f"Refund: {'Yes' if is_refund else 'No'} → {fee}"
        }
    }


def calculate_expected_fees(
    transaction: Dict[str, Any],
    contract: DintaresContract,
    detected_columns: Dict[str, Optional[str]],
    confidence_scores: Dict[str, float] = None
) -> Dict[str, any]:
    """
    Calculate all expected fees for a transaction.

    Args:
        transaction: Transaction dictionary with column values
        contract: DintaresContract with fee rates
        detected_columns: Mapping of field types to actual column names

    Returns:
        Dictionary with:
        {
            "remuneration": Decimal,
            "chargeback": Decimal,
            "refund": Decimal,
            "total_fees": Decimal,
            "breakdown": {
                "remuneration": {...},
                "chargeback": {...},
                "refund": {...}
            },
            "missing_data": List[str]
        }
    """
    from agent.tools.excel_loader import parse_decimal

    missing_data = []
    breakdown = {}

    # Get amount column
    amount_col = detected_columns.get("amount")
    if not amount_col or amount_col not in transaction:
        missing_data.append("amount")
        return {
            "remuneration": Decimal("0.00"),
            "chargeback": Decimal("0.00"),
            "refund": Decimal("0.00"),
            "total_fees": Decimal("0.00"),
            "breakdown": {},
            "missing_data": missing_data
        }

    # Parse amount
    amount = parse_decimal(transaction.get(amount_col))
    if amount is None:
        missing_data.append("amount (invalid value)")
        return {
            "remuneration": Decimal("0.00"),
            "chargeback": Decimal("0.00"),
            "refund": Decimal("0.00"),
            "total_fees": Decimal("0.00"),
            "breakdown": {},
            "missing_data": missing_data
        }

    # Calculate remuneration (always applicable)
    remuneration_result = calculate_remuneration(amount, contract.remuneration_rate)
    remuneration_fee = remuneration_result["fee"]
    breakdown["remuneration"] = remuneration_result["breakdown"]

    # Check for chargeback (only if column found with high confidence)
    chargeback_col = detected_columns.get("chargeback_fee")
    chargeback_confidence = confidence_scores.get("chargeback_fee", 0.0) if confidence_scores else 0.0
    is_chargeback = False

    if chargeback_col and chargeback_confidence >= 0.7 and chargeback_col in transaction:
        chargeback_value = transaction.get(chargeback_col)
        # Check if chargeback occurred (non-zero value, or status indicates it)
        if chargeback_value is not None and chargeback_value != 0:
            is_chargeback = True

    chargeback_result = calculate_chargeback_fee(is_chargeback, contract.chargeback_cost)
    chargeback_fee = chargeback_result["fee"]
    breakdown["chargeback"] = chargeback_result["breakdown"]

    # Check for refund (only if column found with high confidence)
    refund_col = detected_columns.get("refund_fee")
    refund_confidence = confidence_scores.get("refund_fee", 0.0) if confidence_scores else 0.0
    is_refund = False

    if refund_col and refund_confidence >= 0.7 and refund_col in transaction:
        refund_value = transaction.get(refund_col)
        if refund_value is not None and refund_value != 0:
            is_refund = True

    refund_result = calculate_refund_fee(is_refund, contract.refund_cost)
    refund_fee = refund_result["fee"]
    breakdown["refund"] = refund_result["breakdown"]

    # Calculate total
    total_fees = remuneration_fee + chargeback_fee + refund_fee

    return {
        "remuneration": remuneration_fee,
        "chargeback": chargeback_fee,
        "refund": refund_fee,
        "total_fees": total_fees,
        "breakdown": breakdown,
        "missing_data": missing_data
    }


def parse_transaction_amount(
    transaction: Dict[str, Any],
    detected_columns: Dict[str, Optional[str]]
) -> Optional[Decimal]:
    """
    Extract and parse transaction amount from transaction data.

    Args:
        transaction: Transaction dictionary
        detected_columns: Detected column mappings

    Returns:
        Decimal amount or None if not found/invalid
    """
    from agent.tools.excel_loader import parse_decimal

    amount_col = detected_columns.get("amount")
    if not amount_col or amount_col not in transaction:
        return None

    return parse_decimal(transaction.get(amount_col))
