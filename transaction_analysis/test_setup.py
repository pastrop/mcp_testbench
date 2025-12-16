#!/usr/bin/env python3
"""Test script to verify installation and setup."""

import sys
from pathlib import Path


def test_imports():
    """Test that all required packages can be imported."""
    print("Testing imports...")

    try:
        import anthropic
        print("✓ anthropic")
    except ImportError as e:
        print(f"✗ anthropic: {e}")
        return False

    try:
        import pandas
        print("✓ pandas")
    except ImportError as e:
        print(f"✗ pandas: {e}")
        return False

    try:
        import pydantic
        print("✓ pydantic")
    except ImportError as e:
        print(f"✗ pydantic: {e}")
        return False

    try:
        from dotenv import load_dotenv
        print("✓ python-dotenv")
    except ImportError as e:
        print(f"✗ python-dotenv: {e}")
        return False

    return True


def test_agent_modules():
    """Test that agent modules can be imported."""
    print("\nTesting agent modules...")

    try:
        from agent.tools.data_loader import load_contract_data, load_transaction_data
        print("✓ agent.tools.data_loader")
    except ImportError as e:
        print(f"✗ agent.tools.data_loader: {e}")
        return False

    try:
        from agent.tools.field_mapper import extract_transaction_characteristics
        print("✓ agent.tools.field_mapper")
    except ImportError as e:
        print(f"✗ agent.tools.field_mapper: {e}")
        return False

    try:
        from agent.tools.contract_matcher import find_applicable_contract_rule
        print("✓ agent.tools.contract_matcher")
    except ImportError as e:
        print(f"✗ agent.tools.contract_matcher: {e}")
        return False

    try:
        from agent.tools.fee_calculator import calculate_expected_fees, compare_fees
        print("✓ agent.tools.fee_calculator")
    except ImportError as e:
        print(f"✗ agent.tools.fee_calculator: {e}")
        return False

    try:
        from agent.core import TransactionVerificationAgent
        print("✓ agent.core")
    except ImportError as e:
        print(f"✗ agent.core: {e}")
        return False

    return True


def test_data_files():
    """Test that required data files exist."""
    print("\nTesting data files...")

    contract_file = Path("data/parsed_contract.json")
    if contract_file.exists():
        print(f"✓ {contract_file}")
    else:
        print(f"✗ {contract_file} not found")
        return False

    transaction_file = Path("data/transaction_table.csv")
    if transaction_file.exists():
        print(f"✓ {transaction_file}")
    else:
        print(f"✗ {transaction_file} not found")
        return False

    return True


def test_data_loading():
    """Test that data files can be loaded."""
    print("\nTesting data loading...")

    try:
        from agent.tools.data_loader import load_contract_data

        contract_data = load_contract_data("data/parsed_contract.json")
        print(f"✓ Contract loaded: {len(contract_data['currencies'])} currencies")
    except Exception as e:
        print(f"✗ Failed to load contract: {e}")
        return False

    try:
        from agent.tools.data_loader import load_transaction_data

        tx_data = load_transaction_data("data/transaction_table.csv", limit=5)
        print(f"✓ Transactions loaded: {tx_data['total_count']} transactions")
    except Exception as e:
        print(f"✗ Failed to load transactions: {e}")
        return False

    return True


def test_tools():
    """Test that tools execute correctly."""
    print("\nTesting tools...")

    try:
        from agent.tools.field_mapper import infer_payment_method

        test_tx = {
            "traffic_type_group": "card",
            "card_brand": "VISA"
        }

        result = infer_payment_method(test_tx)
        if result["payment_method"] == "card":
            print(f"✓ infer_payment_method: {result['payment_method']} (confidence: {result['confidence']})")
        else:
            print(f"✗ infer_payment_method returned unexpected result: {result}")
            return False

    except Exception as e:
        print(f"✗ infer_payment_method failed: {e}")
        return False

    try:
        from agent.tools.fee_calculator import calculate_expected_fees

        test_rule = {
            "wl_rate": 0.06,
            "fixed_fee": 0.15
        }

        result = calculate_expected_fees(100.0, test_rule, "payment")
        expected_total = 6.15  # (100 * 0.06) + 0.15

        if abs(result["breakdown"]["total"] - expected_total) < 0.01:
            print(f"✓ calculate_expected_fees: {result['breakdown']['total']}")
        else:
            print(f"✗ calculate_expected_fees: expected {expected_total}, got {result['breakdown']['total']}")
            return False

    except Exception as e:
        print(f"✗ calculate_expected_fees failed: {e}")
        return False

    return True


def main():
    """Run all tests."""
    print("="*60)
    print("Transaction Verification Agent - Setup Test")
    print("="*60)

    all_passed = True

    all_passed &= test_imports()
    all_passed &= test_agent_modules()
    all_passed &= test_data_files()
    all_passed &= test_data_loading()
    all_passed &= test_tools()

    print("\n" + "="*60)
    if all_passed:
        print("✓ All tests passed!")
        print("\nYou're ready to run:")
        print("  python main.py --max-transactions 5")
        print("\n(Make sure to set ANTHROPIC_API_KEY in .env first)")
    else:
        print("✗ Some tests failed")
        print("\nPlease fix the issues above before running the agent.")
        sys.exit(1)
    print("="*60)


if __name__ == "__main__":
    main()
