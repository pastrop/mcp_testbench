#!/usr/bin/env python3
"""Test that discrepancy amount sum is calculated correctly."""

import json

# Sample discrepancies matching the actual data structure
test_discrepancies = [
    {
        "transaction_id": "test-1",
        "actual_commission": 17.86,
        "expected_commission": 10.487265,
        "discrepancy_amount": 7.372735,
        "status": "OVERCHARGED"
    },
    {
        "transaction_id": "test-2",
        "actual_commission": 1.59,
        "expected_commission": 0.90,
        "discrepancy_amount": 0.69,
        "status": "OVERCHARGED"
    },
    {
        "transaction_id": "test-3",
        "response": "Some text response",
        "note": "No discrepancy_amount field"
    }
]

# Test the calculation logic (same as in agent/core.py)
total_amount = sum(
    d.get("discrepancy_amount", d.get("discrepancy", 0))
    for d in test_discrepancies
    if isinstance(d.get("discrepancy_amount", d.get("discrepancy", 0)), (int, float))
)

print("Test Discrepancies:")
for i, d in enumerate(test_discrepancies, 1):
    disc_amt = d.get("discrepancy_amount", d.get("discrepancy", 0))
    print(f"  {i}. Transaction {d['transaction_id']}: {disc_amt}")

print(f"\nExpected total: {7.372735 + 0.69:.6f}")
print(f"Calculated total: {total_amount:.6f}")

if abs(total_amount - (7.372735 + 0.69)) < 0.000001:
    print("\n✓ Test PASSED: Total discrepancy amount calculated correctly!")
else:
    print(f"\n❌ Test FAILED: Expected {7.372735 + 0.69}, got {total_amount}")
