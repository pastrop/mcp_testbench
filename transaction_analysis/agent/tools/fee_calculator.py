"""Fee calculation and comparison tools."""

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional


def calculate_expected_fees(
    amount: float,
    contract_rule: Dict,
    transaction_type: str = "payment"
) -> Dict:
    """
    Calculate expected fees based on contract rule.

    Args:
        amount: Transaction amount
        contract_rule: Contract rule dictionary (must contain 'rule' key or be the rule itself)
        transaction_type: Type of transaction (payment, payout, refund, chargeback)

    Returns:
        Dictionary with:
        - breakdown: Fee components (percentage_fee, fixed_fee, total)
        - calculation_method: Explanation of calculation
        - applicable_rates: Rates used in calculation
    """
    # Handle both formats: {"rule": {...}} and direct rule dict
    rule = contract_rule.get("rule", contract_rule)

    # Use Decimal for precise calculations
    amount_decimal = Decimal(str(amount))

    # Initialize components
    percentage_fee = Decimal("0")
    fixed_fee = Decimal("0")

    # Calculate based on transaction type
    if transaction_type in ["payment", "sale"]:
        # Standard payment fee: (amount × wl_rate) + fixed_fee
        wl_rate = Decimal(str(rule.get("wl_rate", 0.0)))
        fixed_fee = Decimal(str(rule.get("fixed_fee", 0.0)))
        percentage_fee = amount_decimal * wl_rate

        calculation_method = f"Payment fee: ({amount} × {wl_rate}) + {fixed_fee}"

    elif transaction_type == "refund":
        # Refund fee is usually just the refund_fee
        fixed_fee = Decimal(str(rule.get("refund_fee", 0.0)))
        percentage_fee = Decimal("0")

        calculation_method = f"Refund fee: {fixed_fee} (flat)"

    elif transaction_type == "chargeback":
        # Chargeback fee
        fixed_fee = Decimal(str(rule.get("chb_fee", 0.0)))
        percentage_fee = Decimal("0")

        calculation_method = f"Chargeback fee: {fixed_fee} (flat)"

    elif transaction_type in ["payout", "withdrawal"]:
        # Outgoing transaction
        rate = Decimal(str(rule.get("rate", 0.0)))
        percentage_fee = amount_decimal * rate

        # Check for fixed payout fee
        if "payout_oct_fix" in rule:
            fixed_fee = Decimal(str(rule.get("payout_oct_fix", 0.0)))

        # Check for minimum payout fee
        if "payout_oct_min" in rule:
            min_fee = Decimal(str(rule.get("payout_oct_min", 0.0)))
            total_before_min = percentage_fee + fixed_fee
            if total_before_min < min_fee:
                fixed_fee = min_fee - percentage_fee

        calculation_method = f"Payout fee: ({amount} × {rate}) + {fixed_fee}"

    else:
        calculation_method = f"Unknown transaction type: {transaction_type}"

    # Calculate total
    total = percentage_fee + fixed_fee

    # Round to 2 decimal places (standard for currency)
    percentage_fee = float(percentage_fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    fixed_fee = float(fixed_fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    total = float(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    return {
        "breakdown": {
            "percentage_fee": percentage_fee,
            "fixed_fee": fixed_fee,
            "total": total,
            "components": {
                "wl_rate": rule.get("wl_rate"),
                "fixed_fee_rate": rule.get("fixed_fee"),
                "refund_fee": rule.get("refund_fee"),
                "chb_fee": rule.get("chb_fee"),
                "payout_rate": rule.get("rate")
            }
        },
        "calculation_method": calculation_method,
        "applicable_rates": {
            "wl_rate": rule.get("wl_rate", 0.0),
            "fixed_fee": rule.get("fixed_fee", 0.0),
            "rate": rule.get("rate", 0.0)
        }
    }


def compare_fees(
    actual_fee: float,
    expected_fee: float,
    tolerance: float = 0.01
) -> Dict:
    """
    Compare actual vs expected fees.

    Args:
        actual_fee: Fee that was actually charged
        expected_fee: Fee calculated from contract
        tolerance: Acceptable difference (default 0.01 = 1 cent)

    Returns:
        Dictionary with:
        - is_correct: Boolean indicating if within tolerance
        - difference_amount: Absolute difference
        - difference_percentage: Percentage difference
        - within_tolerance: Same as is_correct
        - status: CORRECT, OVERCHARGED, or UNDERCHARGED
    """
    difference = actual_fee - expected_fee

    # Calculate percentage difference
    if expected_fee != 0:
        diff_percentage = (difference / expected_fee) * 100
    else:
        diff_percentage = 0.0 if difference == 0 else float('inf')

    # Check if within tolerance
    within_tolerance = abs(difference) <= tolerance

    # Determine status
    if within_tolerance:
        status = "CORRECT"
    elif difference > 0:
        status = "OVERCHARGED"
    else:
        status = "UNDERCHARGED"

    return {
        "is_correct": within_tolerance,
        "difference_amount": round(difference, 2),
        "difference_percentage": round(diff_percentage, 2),
        "within_tolerance": within_tolerance,
        "status": status
    }


def calculate_confidence_score(
    payment_method_confidence: float,
    rule_match_confidence: float,
    data_completeness: float,
    ambiguity_count: int
) -> float:
    """
    Calculate overall confidence score for a verification decision.

    Args:
        payment_method_confidence: Confidence in payment method inference (0.0-1.0)
        rule_match_confidence: Confidence in contract rule matching (0.0-1.0)
        data_completeness: Fraction of required data present (0.0-1.0)
        ambiguity_count: Number of ambiguous decisions made

    Returns:
        Overall confidence score (0.0-1.0)
    """
    # Base confidence is minimum of the three factors
    base_confidence = min(
        payment_method_confidence,
        rule_match_confidence,
        data_completeness
    )

    # Reduce confidence for each ambiguity
    ambiguity_penalty = ambiguity_count * 0.05

    # Final confidence
    confidence = max(0.0, base_confidence - ambiguity_penalty)

    return round(confidence, 2)
