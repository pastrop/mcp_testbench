"""Human-readable report generation."""

from datetime import datetime
from typing import List, Dict


def generate_text_report(discrepancies: List[Dict], output_file: str):
    """
    Generate a human-readable text report.

    Args:
        discrepancies: List of discrepancy dictionaries
        output_file: Path to output text file
    """
    report_lines = []

    # Header
    report_lines.extend([
        "=" * 80,
        "TRANSACTION COMMISSION DISCREPANCY REPORT",
        "=" * 80,
        "",
        "EXECUTIVE SUMMARY",
        "-" * 80,
        ""
    ])

    # Calculate summary statistics
    total_discrepancies = len(discrepancies)
    total_amount = sum(
        d.get("discrepancy_amount", d.get("discrepancy", 0))
        for d in discrepancies
        if isinstance(d.get("discrepancy_amount", d.get("discrepancy", 0)), (int, float))
    )

    overcharged = sum(1 for d in discrepancies if d.get("status") == "OVERCHARGED")
    undercharged = sum(1 for d in discrepancies if d.get("status") == "UNDERCHARGED")
    errors = sum(1 for d in discrepancies if d.get("error"))

    # Summary section
    report_lines.extend([
        f"Total Discrepancies Found: {total_discrepancies}",
        f"Total Discrepancy Amount: €{abs(total_amount):.2f}",
        f"  - Overcharged: {overcharged} transactions",
        f"  - Undercharged: {undercharged} transactions",
    ])

    if errors:
        report_lines.append(f"  - Errors/Incomplete: {errors} transactions")

    report_lines.extend(["", "=" * 80, ""])

    # Individual discrepancy sections
    for idx, discrepancy in enumerate(discrepancies, 1):
        report_lines.extend(_format_discrepancy(idx, discrepancy))
        report_lines.append("")

    # Overall recommendation
    report_lines.extend([
        "=" * 80,
        "OVERALL RECOMMENDATIONS",
        "=" * 80,
        ""
    ])

    if overcharged > 0:
        report_lines.extend([
            f"⚠️  IMMEDIATE INVESTIGATION REQUIRED",
            f"   {overcharged} transaction(s) show overcharging",
            ""
        ])

    if undercharged > 0:
        report_lines.extend([
            f"📊 REVIEW RECOMMENDED",
            f"   {undercharged} transaction(s) show undercharging",
            ""
        ])

    if errors > 0:
        report_lines.extend([
            f"❓ INCOMPLETE ANALYSIS",
            f"   {errors} transaction(s) could not be fully analyzed",
            ""
        ])

    # Footer
    report_lines.extend([
        "-" * 80,
        f"Report Generated: {datetime.now().strftime('%B %d, %Y at %H:%M:%S')}",
        "=" * 80
    ])

    # Write to file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))


def _format_discrepancy(number: int, discrepancy: Dict) -> List[str]:
    """Format a single discrepancy entry."""
    lines = []

    # Header
    tx_id = discrepancy.get("transaction_id", "Unknown")
    lines.extend([
        "=" * 80,
        f"DISCREPANCY #{number}: Transaction {tx_id}",
        "=" * 80,
        ""
    ])

    # Status
    status = discrepancy.get("status", "UNKNOWN")
    error = discrepancy.get("error")

    if error:
        lines.extend([
            "STATUS",
            "-" * 80,
            f"❌ ERROR - {error}",
            ""
        ])
    elif status == "OVERCHARGED":
        diff_pct = discrepancy.get("discrepancy_percentage", 0)
        lines.extend([
            "STATUS",
            "-" * 80,
            f"⚠️  OVERCHARGED - {abs(diff_pct):.2f}% above expected",
            ""
        ])
    elif status == "UNDERCHARGED":
        diff_pct = discrepancy.get("discrepancy_percentage", 0)
        lines.extend([
            "STATUS",
            "-" * 80,
            f"📉 UNDERCHARGED - {abs(diff_pct):.2f}% below expected",
            ""
        ])

    # Transaction Details
    lines.extend([
        "TRANSACTION DETAILS",
        "-" * 80,
        ""
    ])

    if "amount" in discrepancy:
        lines.append(f"  • Amount: €{discrepancy['amount']:.2f}")

    if "currency" in discrepancy:
        lines.append(f"  • Currency: {discrepancy['currency']}")

    if "payment_method" in discrepancy:
        lines.append(f"  • Payment Method: {discrepancy['payment_method'].title()}")

    if "card_brand" in discrepancy and discrepancy["card_brand"]:
        lines.append(f"  • Card Brand: {discrepancy['card_brand']}")

    if "country" in discrepancy and discrepancy["country"]:
        lines.append(f"  • Region: {discrepancy['country']}")

    if "transaction_date" in discrepancy:
        lines.append(f"  • Date: {discrepancy['transaction_date']}")

    lines.append("")

    # Financial Discrepancy (if not an error)
    if not error and "actual_commission" in discrepancy:
        lines.extend([
            "FINANCIAL DISCREPANCY",
            "-" * 80,
            ""
        ])

        actual = discrepancy.get("actual_commission", 0)
        expected = discrepancy.get("expected_commission", 0)
        diff = discrepancy.get("discrepancy_amount", discrepancy.get("discrepancy", 0))
        diff_pct = discrepancy.get("discrepancy_percentage", 0)

        # Format as table
        lines.extend([
            f"  {'Metric':<40} {'Amount (EUR)':>15}",
            f"  {'-' * 40} {'-' * 15}",
            f"  {'Actual Commission Charged':<40} €{actual:>14.2f}",
            f"  {'Expected Commission':<40} €{expected:>14.2f}",
            f"  {'Discrepancy':<40} €{diff:>14.2f}",
            f"  {'Discrepancy Percentage':<40} {diff_pct:>14.2f}%",
            ""
        ])

        # Expected Fee Breakdown
        if "expected_breakdown" in discrepancy:
            breakdown = discrepancy["expected_breakdown"]
            lines.extend([
                "EXPECTED FEE BREAKDOWN",
                "-" * 80,
                ""
            ])

            if "percentage_fee" in breakdown:
                lines.append(f"  1. Percentage Fee: €{breakdown['percentage_fee']:.2f}")

            if "fixed_fee" in breakdown:
                lines.append(f"  2. Fixed Fee: €{breakdown['fixed_fee']:.2f}")

            if "total" in breakdown:
                lines.append(f"  3. TOTAL EXPECTED: €{breakdown['total']:.2f}")

            lines.append("")

    # Response (for transactions where Claude provided detailed analysis)
    if "response" in discrepancy and discrepancy["response"]:
        lines.extend([
            "AGENT ANALYSIS",
            "-" * 80,
            "",
            _wrap_text(discrepancy["response"], 78),
            ""
        ])

    # Note (if present with response)
    if "note" in discrepancy and discrepancy["note"]:
        lines.extend([
            "NOTE",
            "-" * 80,
            "",
            _wrap_text(discrepancy["note"], 78),
            ""
        ])

    # Reasoning
    if "reasoning" in discrepancy and discrepancy["reasoning"]:
        lines.extend([
            "ANALYSIS",
            "-" * 80,
            "",
            _wrap_text(discrepancy["reasoning"], 78),
            ""
        ])

    # Assumptions
    if "assumptions" in discrepancy and discrepancy["assumptions"]:
        lines.extend([
            "ASSUMPTIONS MADE",
            "-" * 80,
            ""
        ])
        for assumption in discrepancy["assumptions"]:
            lines.append(f"  • {assumption}")
        lines.append("")

    # Confidence Level
    if "confidence" in discrepancy:
        confidence = discrepancy["confidence"]
        lines.extend([
            "CONFIDENCE LEVEL",
            "-" * 80,
            ""
        ])

        # Determine confidence category
        if confidence >= 0.8:
            level = "High Confidence"
            emoji = "✓"
        elif confidence >= 0.5:
            level = "Medium Confidence"
            emoji = "~"
        else:
            level = "Low Confidence"
            emoji = "?"

        lines.append(f"  {emoji} {int(confidence * 100)}% ({level})")

        if "confidence_reasoning" in discrepancy:
            lines.extend([
                "",
                f"  {discrepancy['confidence_reasoning']}",
            ])

        lines.append("")

    # Contract Rule Applied
    if "contract_rule_applied" in discrepancy:
        rule = discrepancy["contract_rule_applied"]
        lines.extend([
            "CONTRACT RULE APPLIED",
            "-" * 80,
            ""
        ])

        if "category" in rule:
            lines.append(f"  • Category: {rule['category']}")
        if "rule_key" in rule:
            lines.append(f"  • Rule: {rule['rule_key']}")
        if "wl_rate" in rule and rule["wl_rate"] is not None:
            lines.append(f"  • Rate: {rule['wl_rate'] * 100:.2f}%")
        if "fixed_fee" in rule and rule["fixed_fee"] is not None:
            lines.append(f"  • Fixed Fee: €{rule['fixed_fee']:.2f}")

        lines.append("")

    # Recommendations
    if status in ["OVERCHARGED", "UNDERCHARGED"]:
        lines.extend([
            "RECOMMENDATIONS",
            "-" * 80,
            ""
        ])

        if status == "OVERCHARGED":
            lines.append("  ⚠️  REQUIRES IMMEDIATE INVESTIGATION")
            lines.append("")
            lines.append("  The overcharge warrants urgent review:")
            lines.append("")
            lines.append(f"  1. Verify contract terms for this transaction")
            lines.append(f"  2. Check for undocumented fees")
            lines.append(f"  3. Review calculation logic")
            lines.append(f"  4. Investigate payment processor fees")
            lines.append(f"  5. Validate against rate plan in contract system")
        else:
            lines.append("  📊 REVIEW RECOMMENDED")
            lines.append("")
            lines.append("  The undercharge should be reviewed:")
            lines.append("")
            lines.append(f"  1. Verify if discount was intentionally applied")
            lines.append(f"  2. Check for promotional rates")
            lines.append(f"  3. Review calculation accuracy")
            lines.append(f"  4. Ensure consistent fee application")

        lines.append("")

    return lines


def _wrap_text(text: str, width: int = 78, indent: str = "  ") -> str:
    """Wrap long text to specified width with indentation."""
    words = text.split()
    lines = []
    current_line = indent

    for word in words:
        if len(current_line) + len(word) + 1 <= width:
            if current_line == indent:
                current_line += word
            else:
                current_line += " " + word
        else:
            lines.append(current_line)
            current_line = indent + word

    if current_line != indent:
        lines.append(current_line)

    return '\n'.join(lines)
