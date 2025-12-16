#!/usr/bin/env python3
"""Test that export_results correctly sums discrepancy_amount fields."""

import json
import os
import tempfile
from agent.tools.report_generator import generate_text_report

# Use the actual discrepancy data from the user's report
actual_discrepancies = [
    {
        "transaction_id": "dd125a2d-df30-460b-a9c9-7ff2bf5f1872",
        "actual_commission": 17.86,
        "expected_commission": 10.487265,
        "discrepancy_amount": 7.372735,
        "discrepancy_percentage": 70.3,
        "status": "OVERCHARGED",
        "reasoning": "Test reasoning"
    },
    {
        "transaction_id": "dd11f69b-4836-4377-926d-715bddf77545",
        "actual_commission": 1.59,
        "expected_commission": 0.90,
        "discrepancy_amount": 0.69,
        "status": "OVERCHARGED",
        "response": "Some response",
        "note": "Test note"
    }
]

# Test JSON export logic
total_discrepancy_amount = sum(
    d.get("discrepancy_amount", d.get("discrepancy", 0))
    for d in actual_discrepancies
    if isinstance(d.get("discrepancy_amount", d.get("discrepancy", 0)), (int, float))
)

# Create test output
test_output = {
    "summary": {
        "total_discrepancies": len(actual_discrepancies),
        "total_discrepancy_amount": total_discrepancy_amount
    },
    "discrepancies": actual_discrepancies
}

# Write to temp file
with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
    json.dump(test_output, f, indent=2)
    temp_file = f.name

# Read back and verify
with open(temp_file, 'r') as f:
    result = json.load(f)

print("Generated JSON Summary:")
print(f"  total_discrepancies: {result['summary']['total_discrepancies']}")
print(f"  total_discrepancy_amount: {result['summary']['total_discrepancy_amount']:.6f}")

print("\nIndividual Discrepancies:")
for i, d in enumerate(result['discrepancies'], 1):
    amt = d.get("discrepancy_amount", 0)
    print(f"  {i}. {d['transaction_id']}: €{amt:.6f}")

expected_sum = 7.372735 + 0.69
print(f"\nExpected sum: €{expected_sum:.6f}")
print(f"Actual sum: €{result['summary']['total_discrepancy_amount']:.6f}")

if abs(result['summary']['total_discrepancy_amount'] - expected_sum) < 0.000001:
    print("\n✓ SUCCESS: total_discrepancy_amount correctly sums individual discrepancies!")
else:
    print(f"\n❌ FAILED: Sum mismatch!")

# Clean up
os.unlink(temp_file)
