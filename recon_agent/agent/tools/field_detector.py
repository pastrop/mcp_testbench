from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal, InvalidOperation


# Patterns for detecting fee-related columns
FEE_COLUMN_PATTERNS = {
    "transaction_id": [
        "transaction_id", "id", "номер", "order_id", "tx_id", "transactionid"
    ],
    "amount": [
        "amount", "сумма", "оборот", "transaction_amount", "amt", "sum", "total"
    ],
    "commission": [
        "commission", "комиссия", "вознаграждение", "fee", "charge", "commission_eur", "processing_fee"
    ],
    "rolling_reserve": [
        "rolling_reserve", "rr", "reserve", "резерв", "rolling_res", "rr_amount",
        "reservefund", "резервфонд"
    ],
    "chargeback_fee": [
        "chargeback", "чарджбэк", "cb_fee", "chb", "chargeback_fee", "cb"
    ],
    "refund_fee": [
        "refund", "возврат", "refund_fee", "ref", "refund_amount"
    ],
    "chargeback_qty": [
        "chargeback_qty", "chb_qty", "chb_кол-во", "chargeback_quantity"
    ],
    "chargeback_fee_collected": [
        "chargeback_fee_collected", "chb_fix_50_euro", "chb_fee_actual", "fix_50_euro"
    ],
    "refund_qty": [
        "refund_qty", "refund_кол-во", "refund_quantity"
    ],
    "refund_fee_collected": [
        "refund_fee_collected", "refund_fix_5_euro", "refund_fee_actual", "fix_5_euro"
    ],
    "date": [
        "date", "дата", "created", "timestamp", "transaction_date", "created_at"
    ],
    "status": [
        "status", "статус", "state", "transaction_status"
    ]
}


def detect_fee_columns(columns: List[str]) -> Dict[str, any]:
    """
    Auto-detect fee-related columns from a list of column names.

    Args:
        columns: List of column names (normalized)

    Returns:
        Dictionary with:
        {
            "detected_columns": {
                "transaction_id": "номер_транзакции",
                "amount": "сумма",
                ...
            },
            "confidence_scores": {
                "transaction_id": 0.95,
                "amount": 0.90,
                ...
            },
            "ambiguities": [
                "Multiple columns match 'amount': ['сумма', 'amount_eur']"
            ],
            "missing_fields": ["chargeback_fee", "refund_fee"]
        }
    """
    detected_columns = {}
    confidence_scores = {}
    ambiguities = []
    missing_fields = []

    # For each field type, find the best matching column
    for field_type, patterns in FEE_COLUMN_PATTERNS.items():
        matches = []

        # Find all matching columns
        for column in columns:
            for pattern in patterns:
                confidence = calculate_match_confidence(pattern, column)
                if confidence > 0:
                    matches.append((column, confidence))

        if not matches:
            # No match found
            detected_columns[field_type] = None
            confidence_scores[field_type] = 0.0
            missing_fields.append(field_type)
        elif len(matches) == 1:
            # Single match
            detected_columns[field_type] = matches[0][0]
            confidence_scores[field_type] = matches[0][1]
        else:
            # Multiple matches - use highest confidence
            matches.sort(key=lambda x: x[1], reverse=True)
            detected_columns[field_type] = matches[0][0]
            confidence_scores[field_type] = matches[0][1]

            # Record ambiguity if multiple high-confidence matches
            high_conf_matches = [m for m in matches if m[1] >= 0.7]
            if len(high_conf_matches) > 1:
                ambiguities.append(
                    f"Multiple columns match '{field_type}': {[m[0] for m in high_conf_matches]}"
                )

    return {
        "detected_columns": detected_columns,
        "confidence_scores": confidence_scores,
        "ambiguities": ambiguities,
        "missing_fields": missing_fields
    }


def calculate_match_confidence(pattern: str, column: str) -> float:
    """
    Calculate confidence score for pattern match.

    Args:
        pattern: Pattern to match (e.g., "commission")
        column: Column name to test

    Returns:
        Confidence score (0.0-1.0):
        - 1.0: Exact match
        - 0.9: Starts with pattern
        - 0.8: Ends with pattern
        - 0.7: Contains pattern
        - 0.6: Fuzzy match (Levenshtein distance < 3)
        - 0.0: No match
    """
    pattern = pattern.lower().strip()
    column = column.lower().strip()

    # Exact match
    if pattern == column:
        return 1.0

    # Starts with
    if column.startswith(pattern):
        return 0.9

    # Ends with
    if column.endswith(pattern):
        return 0.8

    # Contains
    if pattern in column:
        return 0.7

    # Fuzzy match (simple Levenshtein-like)
    distance = levenshtein_distance(pattern, column)
    if distance <= 2:
        return 0.6
    elif distance == 3:
        return 0.5

    return 0.0


def levenshtein_distance(s1: str, s2: str) -> int:
    """
    Calculate Levenshtein distance between two strings.

    Args:
        s1: First string
        s2: Second string

    Returns:
        Edit distance
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Cost of insertions, deletions, substitutions
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def calculate_overall_confidence(
    field_confidence_scores: Dict[str, float],
    required_fields: List[str] = None
) -> Tuple[float, List[str]]:
    """
    Calculate overall confidence for field detection.

    Args:
        field_confidence_scores: Dict of field -> confidence score
        required_fields: List of required fields (default: amount, transaction_id)

    Returns:
        Tuple of (overall_confidence, reasons)
    """
    if required_fields is None:
        required_fields = ["amount", "transaction_id"]

    reasons = []

    # Check required fields
    missing_required = []
    for field in required_fields:
        if field not in field_confidence_scores or field_confidence_scores[field] == 0.0:
            missing_required.append(field)

    if missing_required:
        reasons.append(f"Missing required fields: {', '.join(missing_required)}")
        return (0.3, reasons)

    # Calculate average confidence of required fields
    required_confidences = [field_confidence_scores[f] for f in required_fields]
    avg_required = sum(required_confidences) / len(required_confidences)

    # Calculate average confidence of all detected fields (non-zero)
    detected_confidences = [c for c in field_confidence_scores.values() if c > 0]
    if detected_confidences:
        avg_all = sum(detected_confidences) / len(detected_confidences)
    else:
        avg_all = 0.0

    # Overall confidence is weighted average
    overall = (avg_required * 0.7 + avg_all * 0.3)

    # Determine confidence level and reasons
    if overall >= 0.8:
        reasons.append("High confidence: All key fields detected clearly")
    elif overall >= 0.5:
        reasons.append("Medium confidence: Some fields detected with uncertainty")
        low_conf_fields = [f for f, c in field_confidence_scores.items() if 0 < c < 0.7]
        if low_conf_fields:
            reasons.append(f"Low confidence fields: {', '.join(low_conf_fields)}")
    else:
        reasons.append("Low confidence: Multiple fields missing or ambiguous")

    return (round(overall, 2), reasons)


def detect_commission_types_by_percentage(
    transactions: List[Dict[str, Any]],
    detected_columns: Dict[str, Optional[str]],
    target_remuneration_pct: float = 3.8,
    target_rr_pct: float = 10.0
) -> Dict[str, Any]:
    """
    Detect commission types by analyzing actual percentage values in the data.

    This function looks at transactions where amount columns have values,
    calculates what percentage each commission column represents,
    and identifies which column matches the expected percentages for
    remuneration (3.8%) and rolling reserve (10%).

    Args:
        transactions: List of transaction dictionaries
        detected_columns: Current detected column mappings
        target_remuneration_pct: Expected remuneration percentage (default: 3.8)
        target_rr_pct: Expected rolling reserve percentage (default: 10.0)

    Returns:
        Dictionary with:
        {
            "remuneration_column": str or None,
            "rolling_reserve_column": str or None,
            "assumptions": List[str],  # Human-readable assumptions made
            "analysis": {
                "column_name": {
                    "avg_percentage": float,
                    "sample_count": int,
                    "matches": str  # "remuneration", "rolling_reserve", or "unknown"
                }
            }
        }
    """
    from agent.tools.excel_loader import parse_decimal

    result = {
        "remuneration_column": None,
        "rolling_reserve_column": None,
        "assumptions": [],
        "analysis": {}
    }

    # Get amount column
    amount_col = detected_columns.get("amount")
    if not amount_col or not transactions:
        return result

    # Find all commission-like columns (containing "commission" in the name)
    commission_columns = [
        col for col in transactions[0].keys()
        if col and isinstance(col, str) and
        ('commission' in col.lower() or col.lower().startswith('comm'))
        and col != amount_col and not col.startswith('_')
    ]

    if not commission_columns:
        return result

    # Analyze each commission column
    for comm_col in commission_columns:
        percentages = []

        for transaction in transactions[:50]:  # Sample first 50 transactions
            amount_val = parse_decimal(transaction.get(amount_col))
            comm_val = parse_decimal(transaction.get(comm_col))

            if amount_val and comm_val and amount_val > 0:
                pct = float((comm_val / amount_val) * 100)
                percentages.append(pct)

        if percentages:
            avg_pct = sum(percentages) / len(percentages)
            result["analysis"][comm_col] = {
                "avg_percentage": round(avg_pct, 3),
                "sample_count": len(percentages),
                "matches": "unknown"
            }

            # Check if it matches remuneration (3.8% ± 0.2%)
            if abs(avg_pct - target_remuneration_pct) < 0.2:
                result["remuneration_column"] = comm_col
                result["analysis"][comm_col]["matches"] = "remuneration"
                result["assumptions"].append(
                    f"Column '{comm_col}' averages {avg_pct:.2f}% of transaction amount, "
                    f"assumed to be Remuneration (contract: {target_remuneration_pct}%)"
                )

            # Check if it matches rolling reserve (10% ± 0.2%)
            elif abs(avg_pct - target_rr_pct) < 0.2:
                result["rolling_reserve_column"] = comm_col
                result["analysis"][comm_col]["matches"] = "rolling_reserve"
                result["assumptions"].append(
                    f"Column '{comm_col}' averages {avg_pct:.2f}% of transaction amount, "
                    f"assumed to be Rolling Reserve (contract: {target_rr_pct}%)"
                )

    return result
