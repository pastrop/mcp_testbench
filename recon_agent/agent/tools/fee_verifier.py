from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional, Any, List


def compare_fees(
    actual: Optional[Decimal],
    expected: Decimal,
    tolerance: Decimal = Decimal("0.01")
) -> Dict[str, any]:
    """
    Compare actual vs expected fee with tolerance.

    Args:
        actual: Actual fee from transaction (can be None if missing)
        expected: Expected fee from calculation
        tolerance: Acceptable difference (default: €0.01)

    Returns:
        Dictionary with:
        {
            "status": str,           # "CORRECT", "OVERCHARGED", "UNDERCHARGED", "MISSING"
            "difference": Decimal,    # actual - expected
            "difference_pct": Decimal, # percentage difference
            "within_tolerance": bool
        }
    """
    # Handle missing actual value
    if actual is None:
        return {
            "status": "MISSING",
            "difference": None,
            "difference_pct": None,
            "within_tolerance": False
        }

    # Calculate difference
    difference = actual - expected

    # Calculate percentage difference
    if expected != 0:
        diff_pct = (difference / expected * 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
    else:
        diff_pct = Decimal("0.00") if difference == 0 else Decimal("100.00")

    # Determine status
    if abs(difference) <= tolerance:
        status = "CORRECT"
        within_tolerance = True
    elif difference > tolerance:
        status = "OVERCHARGED"
        within_tolerance = False
    else:  # difference < -tolerance
        status = "UNDERCHARGED"
        within_tolerance = False

    return {
        "status": status,
        "difference": difference,
        "difference_pct": diff_pct,
        "within_tolerance": within_tolerance
    }


def verify_transaction_fees(
    transaction: Dict[str, Any],
    expected_fees: Dict[str, Decimal],
    detected_columns: Dict[str, Optional[str]],
    confidence_scores: Dict[str, float],
    tolerance: Decimal = Decimal("0.01")
) -> Dict[str, any]:
    """
    Verify all fee types for a transaction.

    Args:
        transaction: Transaction dictionary with actual values
        expected_fees: Expected fees from calculator
        detected_columns: Mapping of field types to column names
        confidence_scores: Confidence scores for field detection
        tolerance: Acceptable difference for comparison

    Returns:
        Dictionary with:
        {
            "transaction_id": str,
            "verifications": {
                "remuneration": {...},
                "chargeback": {...},
                "refund": {...},
                "rolling_reserve": {...}
            },
            "overall_status": str,  # "CORRECT", "HAS_ERRORS", "QUESTIONABLE"
            "error_count": int,
            "confidence": float,
            "assumptions": List[str]
        }
    """
    from agent.tools.excel_loader import parse_decimal

    verifications = {}
    error_count = 0
    assumptions = []

    # Get transaction ID (use row number if confidence is low or missing)
    tx_id_col = detected_columns.get("transaction_id")
    tx_id_confidence = confidence_scores.get("transaction_id", 0.0)
    transaction_id = None

    # Use actual transaction ID only if confidence is high enough (>= 0.7)
    if tx_id_col and tx_id_col in transaction and transaction.get(tx_id_col) and tx_id_confidence >= 0.7:
        transaction_id = str(transaction.get(tx_id_col))
    else:
        # Use row number as fallback (includes sheet name)
        sheet_name = transaction.get('_sheet_name', '')
        row_num = transaction.get('_row_number', '')
        transaction_id = f"{sheet_name}:Row{row_num}" if sheet_name else f"Row{row_num}"
        if tx_id_confidence < 0.7 and tx_id_col:
            assumptions.append(f"Transaction ID column '{tx_id_col}' has low confidence ({tx_id_confidence:.2f}), using row number")

    # Verify remuneration
    commission_col = detected_columns.get("commission")
    if commission_col and commission_col in transaction:
        actual_commission = parse_decimal(transaction.get(commission_col))
    else:
        actual_commission = None
        assumptions.append("Commission column not found or detected")

    remuneration_comparison = compare_fees(
        actual_commission,
        expected_fees.get("remuneration", Decimal("0.00")),
        tolerance
    )
    verifications["remuneration"] = {
        "expected": expected_fees.get("remuneration", Decimal("0.00")),
        "actual": actual_commission,
        **remuneration_comparison
    }
    # Only count as error if not within tolerance AND not missing
    # (missing data is tracked separately)
    if not remuneration_comparison["within_tolerance"] and remuneration_comparison["status"] != "MISSING":
        error_count += 1

    # Verify rolling reserve
    rr_col = detected_columns.get("rolling_reserve")
    if rr_col and rr_col in transaction:
        actual_rr = parse_decimal(transaction.get(rr_col))
    else:
        actual_rr = None
        assumptions.append("Rolling Reserve column not found or detected")

    rr_comparison = compare_fees(
        actual_rr,
        expected_fees.get("rolling_reserve", Decimal("0.00")),
        tolerance
    )
    verifications["rolling_reserve"] = {
        "expected": expected_fees.get("rolling_reserve", Decimal("0.00")),
        "actual": actual_rr,
        **rr_comparison
    }
    # Only count as error if not within tolerance AND not missing
    if not rr_comparison["within_tolerance"] and rr_comparison["status"] != "MISSING":
        error_count += 1

    # Verify chargeback (if applicable)
    # For EUR (F) and AUD (F), use quantity × contractual fee approach
    chargeback_qty_col = detected_columns.get("chargeback_qty")
    chargeback_fee_collected_col = detected_columns.get("chargeback_fee_collected")

    if chargeback_qty_col and chargeback_fee_collected_col and \
       chargeback_qty_col in transaction and chargeback_fee_collected_col in transaction:
        # New approach: calculate expected from quantity
        qty = parse_decimal(transaction.get(chargeback_qty_col))
        actual_chargeback = parse_decimal(transaction.get(chargeback_fee_collected_col))

        if qty and qty > 0:
            # Expected = quantity × contractual fee (€50)
            expected_chargeback = qty * Decimal("50.00")  # Contractual chargeback fee

            chargeback_comparison = compare_fees(
                actual_chargeback,
                expected_chargeback,
                tolerance
            )
            verifications["chargeback"] = {
                "expected": expected_chargeback,
                "actual": actual_chargeback,
                **chargeback_comparison
            }
            if not chargeback_comparison["within_tolerance"] and chargeback_comparison["status"] != "MISSING":
                error_count += 1
    elif expected_fees.get("chargeback", Decimal("0.00")) > 0:
        # Old approach: use expected from fee_calculator
        chargeback_col = detected_columns.get("chargeback_fee")
        if chargeback_col and chargeback_col in transaction:
            actual_chargeback = parse_decimal(transaction.get(chargeback_col))
        else:
            actual_chargeback = None
            assumptions.append("Chargeback fee expected but column not found")

        chargeback_comparison = compare_fees(
            actual_chargeback,
            expected_fees["chargeback"],
            tolerance
        )
        verifications["chargeback"] = {
            "expected": expected_fees["chargeback"],
            "actual": actual_chargeback,
            **chargeback_comparison
        }
        # Only count as error if not within tolerance AND not missing
        if not chargeback_comparison["within_tolerance"] and chargeback_comparison["status"] != "MISSING":
            error_count += 1

    # Verify refund (if applicable)
    # For EUR (F) and AUD (F), use quantity × contractual fee approach
    refund_qty_col = detected_columns.get("refund_qty")
    refund_fee_collected_col = detected_columns.get("refund_fee_collected")

    if refund_qty_col and refund_fee_collected_col and \
       refund_qty_col in transaction and refund_fee_collected_col in transaction:
        # New approach: calculate expected from quantity
        qty = parse_decimal(transaction.get(refund_qty_col))
        actual_refund = parse_decimal(transaction.get(refund_fee_collected_col))

        if qty and qty > 0:
            # Expected = quantity × contractual fee (€5)
            expected_refund = qty * Decimal("5.00")  # Contractual refund fee

            refund_comparison = compare_fees(
                actual_refund,
                expected_refund,
                tolerance
            )
            verifications["refund"] = {
                "expected": expected_refund,
                "actual": actual_refund,
                **refund_comparison
            }
            if not refund_comparison["within_tolerance"] and refund_comparison["status"] != "MISSING":
                error_count += 1
    elif expected_fees.get("refund", Decimal("0.00")) > 0:
        # Old approach: use expected from fee_calculator
        refund_col = detected_columns.get("refund_fee")
        if refund_col and refund_col in transaction:
            actual_refund = parse_decimal(transaction.get(refund_col))
        else:
            actual_refund = None
            assumptions.append("Refund fee expected but column not found")

        refund_comparison = compare_fees(
            actual_refund,
            expected_fees["refund"],
            tolerance
        )
        verifications["refund"] = {
            "expected": expected_fees["refund"],
            "actual": actual_refund,
            **refund_comparison
        }
        # Only count as error if not within tolerance AND not missing
        if not refund_comparison["within_tolerance"] and refund_comparison["status"] != "MISSING":
            error_count += 1

    # Calculate overall confidence
    confidence = calculate_verification_confidence(
        confidence_scores,
        len(assumptions),
        error_count
    )

    # Determine overall status
    if error_count == 0:
        overall_status = "CORRECT"
    elif confidence < 0.7:
        # Low confidence detections should be marked as questionable, not errors
        overall_status = "QUESTIONABLE"
    else:
        overall_status = "HAS_ERRORS"

    return {
        "transaction_id": transaction_id,
        "verifications": verifications,
        "overall_status": overall_status,
        "error_count": error_count,
        "confidence": confidence,
        "assumptions": assumptions
    }


def calculate_verification_confidence(
    field_confidence_scores: Dict[str, float],
    assumption_count: int,
    error_count: int
) -> float:
    """
    Calculate overall confidence for a transaction verification.

    Args:
        field_confidence_scores: Confidence scores for field detection
        assumption_count: Number of assumptions made
        error_count: Number of errors found

    Returns:
        Confidence score (0.0-1.0)
    """
    # Base confidence from field detection
    relevant_fields = ["amount", "commission", "rolling_reserve"]
    relevant_scores = [
        field_confidence_scores.get(field, 0.0)
        for field in relevant_fields
    ]
    if relevant_scores:
        base_confidence = sum(relevant_scores) / len(relevant_scores)
    else:
        base_confidence = 0.5

    # Additional penalty if ANY critical field has very low confidence (< 0.6)
    # This ensures uncertain detections are marked as questionable
    min_critical_confidence = min(relevant_scores) if relevant_scores else 0.0
    if min_critical_confidence < 0.6:
        # Severe penalty to push below questionable threshold (0.7)
        low_confidence_penalty = 0.2
    else:
        low_confidence_penalty = 0.0

    # Penalty for assumptions (0.05 per assumption)
    assumption_penalty = min(assumption_count * 0.05, 0.3)

    # Penalty for errors (slight penalty, as errors might be legitimate)
    error_penalty = min(error_count * 0.02, 0.1)

    # Calculate final confidence
    final_confidence = max(0.0, base_confidence - low_confidence_penalty - assumption_penalty - error_penalty)

    return round(final_confidence, 2)


def categorize_by_confidence(
    verifications: List[Dict[str, any]],
    confidence_threshold: float = 0.5
) -> Dict[str, List[Dict]]:
    """
    Categorize verifications by confidence level.

    Args:
        verifications: List of verification results
        confidence_threshold: Threshold for questionable (default: 0.5)

    Returns:
        Dictionary with:
        {
            "high_confidence": List[Dict],
            "low_confidence": List[Dict]
        }
    """
    high_confidence = []
    low_confidence = []

    for verification in verifications:
        if verification["confidence"] >= confidence_threshold:
            high_confidence.append(verification)
        else:
            low_confidence.append(verification)

    return {
        "high_confidence": high_confidence,
        "low_confidence": low_confidence
    }
