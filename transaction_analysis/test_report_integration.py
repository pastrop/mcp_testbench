#!/usr/bin/env python3
"""Test report generator integration."""

import os
import sys
from agent.tools.report_generator import generate_text_report

# Sample discrepancies for testing
sample_discrepancies = [
    {
        "transaction_id": "test-123",
        "status": "OVERCHARGED",
        "actual_commission": 10.50,
        "expected_commission": 9.25,
        "discrepancy": 1.25,
        "discrepancy_percentage": 13.51,
        "amount": 500.00,
        "currency": "EUR",
        "payment_method": "card",
        "card_brand": "Visa",
        "country": "DE",
        "transaction_date": "2025-12-15",
        "reasoning": "The transaction was charged a higher commission than expected based on the contract terms. The expected fee for a EUR 500.00 Visa card payment in Germany should be EUR 9.25.",
        "assumptions": [
            "Assumed card payment method based on card_brand field",
            "Used German domestic rate from contract",
            "Applied standard Visa fee structure"
        ],
        "confidence": 0.85,
        "confidence_reasoning": "High confidence due to clear card brand identification and exact contract match for German domestic transactions.",
        "expected_breakdown": {
            "percentage_fee": 9.00,
            "fixed_fee": 0.25,
            "total": 9.25
        },
        "contract_rule_applied": {
            "category": "card_fees",
            "rule_key": "EUR_domestic_Visa",
            "wl_rate": 0.018,
            "fixed_fee": 0.25
        }
    },
    {
        "transaction_id": "test-456",
        "status": "UNDERCHARGED",
        "actual_commission": 5.00,
        "expected_commission": 6.50,
        "discrepancy": -1.50,
        "discrepancy_percentage": -23.08,
        "amount": 300.00,
        "currency": "EUR",
        "payment_method": "sepa",
        "transaction_date": "2025-12-14",
        "reasoning": "The SEPA transaction was undercharged. Based on contract terms, the fee should be EUR 6.50.",
        "assumptions": [
            "Identified payment method as SEPA from transaction type",
            "Applied standard SEPA rate"
        ],
        "confidence": 0.75,
        "confidence_reasoning": "Medium confidence - SEPA payment method inferred from limited data."
    },
    {
        "transaction_id": "test-789",
        "error": "Unable to determine payment method from transaction data",
        "actual_commission": 3.50,
        "confidence": 0.3
    }
]

def test_report_generation():
    """Test that report can be generated."""
    print("Testing report generator integration...")

    # Create test output
    test_output = "output/test_report.txt"
    os.makedirs("output", exist_ok=True)

    try:
        # Generate report
        generate_text_report(sample_discrepancies, test_output)

        # Check file was created
        if not os.path.exists(test_output):
            print(f"❌ Failed: Report file not created at {test_output}")
            return False

        # Check file has content
        with open(test_output, 'r') as f:
            content = f.read()

        if len(content) < 100:
            print(f"❌ Failed: Report content too short ({len(content)} chars)")
            return False

        # Check for key sections
        required_sections = [
            "EXECUTIVE SUMMARY",
            "TRANSACTION COMMISSION DISCREPANCY REPORT",
            "OVERCHARGED",
            "UNDERCHARGED",
            "ERROR",
            "OVERALL RECOMMENDATIONS"
        ]

        missing_sections = []
        for section in required_sections:
            if section not in content:
                missing_sections.append(section)

        if missing_sections:
            print(f"❌ Failed: Missing sections: {', '.join(missing_sections)}")
            return False

        print(f"✓ Report generated successfully")
        print(f"✓ File size: {len(content)} characters")
        print(f"✓ All required sections present")
        print(f"\nReport saved to: {test_output}")
        print("\nFirst 500 characters:")
        print("-" * 80)
        print(content[:500])
        print("-" * 80)

        return True

    except Exception as e:
        print(f"❌ Failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_report_generation()
    sys.exit(0 if success else 1)
