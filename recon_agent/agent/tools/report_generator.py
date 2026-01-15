import json
from decimal import Decimal
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path


def has_missing_data(verification: Dict[str, Any]) -> bool:
    """
    Check if a verification has any missing data.

    Args:
        verification: Transaction verification result

    Returns:
        True if transaction has any missing fees, False otherwise
    """
    verifications = verification.get("verifications", {})
    if not verifications:
        return False

    # Check if ANY fee verification has MISSING status
    for fee_type, fee_verify in verifications.items():
        if fee_verify.get("status") == "MISSING":
            return True

    return False


def generate_text_report(
    verifications: List[Dict[str, Any]],
    contract_file: str,
    excel_file: str,
    sheet_name: Optional[str],
    output_path: str,
    confidence_threshold: float = 0.5,
    detection_assumptions: List[str] = None
):
    """
    Generate human-readable text report with ASCII tables.

    Args:
        verifications: List of transaction verification results
        contract_file: Path to contract file
        excel_file: Path to Excel file
        sheet_name: Sheet name processed
        output_path: Output file path
        confidence_threshold: Threshold for questionable transactions
    """
    # Categorize verifications
    correct = []
    erroneous = []
    questionable = []
    missing_data = []

    for verification in verifications:
        if verification["confidence"] < confidence_threshold:
            questionable.append(verification)
        elif verification["error_count"] > 0:
            # Has actual errors (even if some fees are missing)
            erroneous.append(verification)
        elif has_missing_data(verification):
            # Only has missing data, no actual errors
            missing_data.append(verification)
        else:
            correct.append(verification)

    # Calculate total discrepancy
    total_discrepancy = Decimal("0.00")
    total_discrepancy_complete = Decimal("0.00")  # Exclude transactions with missing data

    for verification in erroneous:
        has_any_missing = has_missing_data(verification)

        for fee_type, fee_verify in verification["verifications"].items():
            if fee_verify.get("difference") is not None:
                total_discrepancy += abs(fee_verify["difference"])

                # Only count if this transaction has NO missing data
                if not has_any_missing:
                    total_discrepancy_complete += abs(fee_verify["difference"])

    # Generate report
    lines = []
    lines.append("=" * 80)
    lines.append("DINTARES FEE VERIFICATION REPORT")
    lines.append("=" * 80)
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Contract: {Path(contract_file).name}")
    lines.append(f"Excel File: {Path(excel_file).name}")
    if sheet_name:
        lines.append(f"Sheet: {sheet_name}")
    lines.append("")

    # Detection assumptions section
    if detection_assumptions:
        lines.append("DETECTION ASSUMPTIONS")
        lines.append("-" * 80)
        for assumption in detection_assumptions:
            lines.append(f"• {assumption}")
        lines.append("")
        lines.append("=" * 80)
        lines.append("")

    # Summary section
    lines.append("SUMMARY")
    lines.append("-" * 80)
    lines.append(f"Total Transactions:        {len(verifications):,}")
    lines.append(f"Correct:                   {len(correct):,}")
    lines.append(f"Erroneous:                 {len(erroneous):,}")
    lines.append(f"Questionable:              {len(questionable):,}")
    lines.append(f"Missing Data:              {len(missing_data):,}")
    lines.append(f"Total Discrepancy Amount:  €{total_discrepancy:.2f}")
    lines.append(f"  (Complete Data Only):    €{total_discrepancy_complete:.2f}")
    lines.append("")

    # Per-sheet breakdown (if multiple sheets detected)
    sheet_stats = {}
    for verification in verifications:
        tx_id = verification.get("transaction_id", "")
        # Extract sheet name from transaction ID (format: "SheetName:RowN")
        if ":" in tx_id:
            sheet_name = tx_id.split(":")[0]
        else:
            sheet_name = "Unknown"

        if sheet_name not in sheet_stats:
            sheet_stats[sheet_name] = {"total": 0, "correct": 0, "erroneous": 0, "questionable": 0, "missing_data": 0}

        sheet_stats[sheet_name]["total"] += 1

        if verification["confidence"] < confidence_threshold:
            sheet_stats[sheet_name]["questionable"] += 1
        elif verification["error_count"] > 0:
            sheet_stats[sheet_name]["erroneous"] += 1
        elif has_missing_data(verification):
            sheet_stats[sheet_name]["missing_data"] += 1
        else:
            sheet_stats[sheet_name]["correct"] += 1

    # Show per-sheet breakdown if multiple sheets
    if len(sheet_stats) > 1:
        lines.append("BREAKDOWN BY SHEET")
        lines.append("-" * 80)
        for sheet_name in sorted(sheet_stats.keys()):
            stats = sheet_stats[sheet_name]
            lines.append(f"{sheet_name}:")
            lines.append(f"  Total: {stats['total']:,} | Correct: {stats['correct']:,} | "
                        f"Erroneous: {stats['erroneous']:,} | Questionable: {stats['questionable']:,} | "
                        f"Missing Data: {stats['missing_data']:,}")
        lines.append("")

    lines.append("=" * 80)
    lines.append("")

    # Erroneous transactions section
    if erroneous:
        lines.append("ERRONEOUS TRANSACTIONS")
        lines.append("-" * 80)
        lines.append("")

        # Group errors by fee type
        errors_by_type = {}
        for verification in erroneous:
            tx_id = verification["transaction_id"] or "N/A"
            for fee_type, fee_verify in verification["verifications"].items():
                # Skip MISSING fees - they go in the Missing Data section
                if fee_verify.get("status") == "MISSING":
                    continue

                if not fee_verify.get("within_tolerance", False):
                    expected = fee_verify.get("expected", Decimal("0.00"))
                    actual = fee_verify.get("actual")
                    difference = fee_verify.get("difference")

                    if fee_type not in errors_by_type:
                        errors_by_type[fee_type] = []

                    # Store with difference as Decimal for sorting
                    errors_by_type[fee_type].append({
                        "tx_id": tx_id,
                        "expected": expected,
                        "actual": actual,
                        "difference": difference,
                        "abs_difference": abs(difference) if difference else Decimal("0.00")
                    })

        # Display each fee type in a separate table, sorted by absolute difference
        fee_type_order = ["remuneration", "rolling_reserve", "chargeback", "refund"]

        for fee_type in fee_type_order:
            if fee_type not in errors_by_type:
                continue

            errors = errors_by_type[fee_type]
            # Sort by absolute difference (descending - largest discrepancies first)
            errors.sort(key=lambda x: x["abs_difference"], reverse=True)

            lines.append(f"{fee_type.replace('_', ' ').title()} Errors ({len(errors)} transactions)")
            lines.append("-" * 80)

            # Build rows for this fee type
            error_rows = []
            for error in errors:
                error_rows.append([
                    error["tx_id"],
                    f"€{error['expected']:.2f}",
                    f"€{error['actual']:.2f}" if error['actual'] is not None else "MISSING",
                    f"{'+' if error['difference'] and error['difference'] > 0 else ''}€{error['difference']:.2f}" if error['difference'] else "N/A"
                ])

            # Create ASCII table (without "Fee Type" column since it's in the header)
            headers = ["Transaction ID", "Expected", "Actual", "Difference"]
            table = create_ascii_table(headers, error_rows)
            lines.append(table)
            lines.append("")

    else:
        lines.append("ERRONEOUS TRANSACTIONS")
        lines.append("-" * 80)
        lines.append("No erroneous transactions found.")
        lines.append("")

    lines.append("=" * 80)
    lines.append("")

    # Questionable transactions section
    if questionable:
        lines.append("QUESTIONABLE TRANSACTIONS")
        lines.append("-" * 80)
        lines.append("")

        # Build questionable details
        questionable_rows = []
        for verification in questionable:
            tx_id = verification["transaction_id"] or "N/A"
            confidence = verification["confidence"]
            assumptions = verification.get("assumptions", [])
            reason = "; ".join(assumptions) if assumptions else "Low confidence"

            questionable_rows.append([
                tx_id,
                reason[:50],  # Truncate long reasons
                f"{confidence:.2f}"
            ])

        # Create ASCII table
        headers = ["Transaction ID", "Reason", "Confidence"]
        table = create_ascii_table(headers, questionable_rows)
        lines.append(table)
        lines.append("")
    else:
        lines.append("QUESTIONABLE TRANSACTIONS")
        lines.append("-" * 80)
        lines.append("No questionable transactions found.")
        lines.append("")

    lines.append("=" * 80)
    lines.append("")

    # Missing Data transactions section
    # Show ALL fee lines with MISSING status from ALL verifications
    # (not just from missing_data category, since erroneous transactions can also have some missing fees)
    lines.append("MISSING DATA TRANSACTIONS")
    lines.append("-" * 80)
    lines.append("")

    missing_rows = []
    for verification in verifications:
        # Skip questionable transactions (they're already listed separately)
        if verification["confidence"] < confidence_threshold:
            continue

        tx_id = verification["transaction_id"] or "N/A"
        for fee_type, fee_verify in verification["verifications"].items():
            if fee_verify.get("status") == "MISSING":
                expected = fee_verify.get("expected", Decimal("0.00"))

                missing_rows.append([
                    tx_id,
                    fee_type.replace("_", " ").title(),
                    f"€{expected:.2f}",
                    "MISSING"
                ])

    if missing_rows:
        # Create ASCII table
        headers = ["Transaction ID", "Fee Type", "Expected", "Actual"]
        table = create_ascii_table(headers, missing_rows)
        lines.append(table)
        lines.append("")
    else:
        lines.append("No transactions with missing data found.")
        lines.append("")

    lines.append("=" * 80)

    # Write to file
    report_text = "\n".join(lines)
    Path(output_path).write_text(report_text, encoding="utf-8")

    return report_text


def create_ascii_table(
    headers: List[str],
    rows: List[List[str]],
    max_col_width: int = 30
) -> str:
    """
    Create formatted ASCII table with box-drawing characters.

    Args:
        headers: List of column headers
        rows: List of row data (each row is a list of strings)
        max_col_width: Maximum column width (default: 30)

    Returns:
        Formatted ASCII table as string
    """
    if not rows:
        return "No data to display"

    # Calculate column widths
    col_widths = []
    for i, header in enumerate(headers):
        max_width = len(header)
        for row in rows:
            if i < len(row):
                max_width = max(max_width, len(str(row[i])))
        col_widths.append(min(max_width, max_col_width))

    # Build table
    lines = []

    # Top border
    top_border = "┌" + "┬".join("─" * (w + 2) for w in col_widths) + "┐"
    lines.append(top_border)

    # Headers
    header_row = "│"
    for header, width in zip(headers, col_widths):
        header_row += f" {header:<{width}} │"
    lines.append(header_row)

    # Header separator
    separator = "├" + "┼".join("─" * (w + 2) for w in col_widths) + "┤"
    lines.append(separator)

    # Data rows
    for row in rows:
        data_row = "│"
        for i, (cell, width) in enumerate(zip(row, col_widths)):
            cell_str = str(cell) if i < len(row) else ""
            # Truncate if too long
            if len(cell_str) > width:
                cell_str = cell_str[:width-3] + "..."
            data_row += f" {cell_str:<{width}} │"
        lines.append(data_row)

    # Bottom border
    bottom_border = "└" + "┴".join("─" * (w + 2) for w in col_widths) + "┘"
    lines.append(bottom_border)

    return "\n".join(lines)


def export_json_report(
    verifications: List[Dict[str, Any]],
    contract_file: str,
    excel_file: str,
    sheet_name: Optional[str],
    output_path: str,
    confidence_threshold: float = 0.5,
    detection_assumptions: List[str] = None
):
    """
    Export structured JSON report for machine processing.

    Args:
        verifications: List of transaction verification results
        contract_file: Path to contract file
        excel_file: Path to Excel file
        sheet_name: Sheet name processed
        output_path: Output file path
        confidence_threshold: Threshold for questionable transactions
    """
    # Categorize verifications
    correct = []
    erroneous = []
    questionable = []
    missing_data = []

    for verification in verifications:
        if verification["confidence"] < confidence_threshold:
            questionable.append(verification)
        elif verification["error_count"] > 0:
            # Has actual errors (even if some fees are missing)
            erroneous.append(verification)
        elif has_missing_data(verification):
            # Only has missing data, no actual errors
            missing_data.append(verification)
        else:
            correct.append(verification)

    # Calculate total discrepancy
    total_discrepancy = Decimal("0.00")
    total_discrepancy_complete = Decimal("0.00")  # Exclude transactions with missing data

    for verification in erroneous:
        has_any_missing = has_missing_data(verification)

        for fee_type, fee_verify in verification["verifications"].items():
            if fee_verify.get("difference") is not None:
                total_discrepancy += abs(fee_verify["difference"])

                # Only count if this transaction has NO missing data
                if not has_any_missing:
                    total_discrepancy_complete += abs(fee_verify["difference"])

    # Build report structure
    report = {
        "metadata": {
            "generated": datetime.now().isoformat(),
            "contract_file": contract_file,
            "excel_file": excel_file,
            "sheet_name": sheet_name,
            "confidence_threshold": confidence_threshold,
            "detection_assumptions": detection_assumptions or []
        },
        "summary": {
            "total_transactions": len(verifications),
            "correct_count": len(correct),
            "erroneous_count": len(erroneous),
            "questionable_count": len(questionable),
            "missing_data_count": len(missing_data),
            "total_discrepancy": str(total_discrepancy),
            "total_discrepancy_complete_data_only": str(total_discrepancy_complete)
        },
        "erroneous_transactions": erroneous,
        "questionable_transactions": questionable,
        "missing_data_transactions": missing_data,
        "all_verifications": verifications
    }

    # Custom JSON encoder for Decimal
    def decimal_encoder(obj):
        if isinstance(obj, Decimal):
            return str(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    # Write to file
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, default=decimal_encoder, ensure_ascii=False)

    return report


def print_summary(verifications: List[Dict[str, Any]], confidence_threshold: float = 0.5):
    """
    Print summary to console.

    Args:
        verifications: List of transaction verification results
        confidence_threshold: Threshold for questionable transactions
    """
    questionable = sum(1 for v in verifications if v["confidence"] < confidence_threshold)
    erroneous = sum(1 for v in verifications if v["error_count"] > 0 and v["confidence"] >= confidence_threshold)
    missing = sum(1 for v in verifications if v["error_count"] == 0 and has_missing_data(v) and v["confidence"] >= confidence_threshold)
    correct = sum(1 for v in verifications if v["error_count"] == 0 and not has_missing_data(v) and v["confidence"] >= confidence_threshold)

    print("\n" + "=" * 60)
    print("VERIFICATION COMPLETE")
    print("=" * 60)
    print(f"Total Transactions:  {len(verifications):,}")
    print(f"Correct:             {correct:,}")
    print(f"Erroneous:           {erroneous:,}")
    print(f"Questionable:        {questionable:,}")
    print(f"Missing Data:        {missing:,}")
    print("=" * 60 + "\n")
