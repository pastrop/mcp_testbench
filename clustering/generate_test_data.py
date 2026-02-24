#!/usr/bin/env python3
"""
Synthetic Transaction Data Generator

Generates test data with transactions and fees using different commission rates.
Creates outliers for testing clustering/anomaly detection algorithms.
"""

import argparse
import random
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pandas as pd


# Commission rate groups
STANDARD_COMMISSION_RATES = [3.5, 3.8, 4.8, 5.0]  # Main groups (95% of data)
OUTLIER_COMMISSION_RATES = [1.0, 2.0, 3.0, 6.0]  # Outliers (5% of data)

# Transaction amount bounds
MIN_TRANSACTION = 1.0
MAX_TRANSACTION = 1000.0

# Outlier percentage
OUTLIER_PERCENTAGE = 0.05


def generate_transactions(n_rows: int) -> np.ndarray:
    """Generate random transaction amounts between MIN and MAX."""
    return np.random.uniform(MIN_TRANSACTION, MAX_TRANSACTION, n_rows)


def assign_commission_rates(n_rows: int) -> Tuple[np.ndarray, List[str]]:
    """
    Assign commission rates to transactions.

    95% get standard rates (3.5%, 3.8%, 4.8%, 5.0%)
    5% get outlier rates (1%, 2%, 3%, 6%)

    Returns:
        Tuple of (commission_rates_array, labels_list)
    """
    n_outliers = int(n_rows * OUTLIER_PERCENTAGE)
    n_standard = n_rows - n_outliers

    # Create arrays
    commission_rates = np.zeros(n_rows)
    labels = []

    # Assign standard commission rates to 95% of rows
    standard_rates = np.random.choice(STANDARD_COMMISSION_RATES, size=n_standard)
    commission_rates[:n_standard] = standard_rates
    labels.extend(['standard'] * n_standard)

    # Assign outlier commission rates to 5% of rows
    outlier_rates = np.random.choice(OUTLIER_COMMISSION_RATES, size=n_outliers)
    commission_rates[n_standard:] = outlier_rates
    labels.extend(['outlier'] * n_outliers)

    # Shuffle the data to mix standard and outlier rows
    indices = np.arange(n_rows)
    np.random.shuffle(indices)
    commission_rates = commission_rates[indices]
    labels = [labels[i] for i in indices]

    return commission_rates, labels


def calculate_transaction_fees(
    transactions: np.ndarray,
    commission_rates: np.ndarray
) -> np.ndarray:
    """Calculate transaction fees based on commission rates."""
    return transactions * (commission_rates / 100.0)


def generate_synthetic_data(n_rows: int = 1000) -> pd.DataFrame:
    """
    Generate synthetic transaction data with fees.

    Args:
        n_rows: Number of rows to generate (default: 1000)

    Returns:
        DataFrame with columns: Transaction, Transaction_Fee, Commission_Rate, Label
    """
    # Set random seed for reproducibility (optional, can be removed for true randomness)
    np.random.seed(None)
    random.seed(None)

    # Generate data
    transactions = generate_transactions(n_rows)
    commission_rates, labels = assign_commission_rates(n_rows)
    transaction_fees = calculate_transaction_fees(transactions, commission_rates)

    # Create DataFrame
    df = pd.DataFrame({
        'Transaction': transactions,
        'Transaction_Fee': transaction_fees,
        'Commission_Rate': commission_rates,
        'Label': labels  # For verification/testing purposes
    })

    return df


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description='Generate synthetic transaction data for testing'
    )
    parser.add_argument(
        '--rows',
        type=int,
        default=1000,
        help='Number of rows to generate (default: 1000)'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='data',
        help='Output directory for the CSV file (default: data)'
    )
    parser.add_argument(
        '--filename',
        type=str,
        default='test_data.csv',
        help='Output filename (default: test_data.csv)'
    )
    parser.add_argument(
        '--seed',
        type=int,
        default=None,
        help='Random seed for reproducibility (optional)'
    )

    args = parser.parse_args()

    # Set random seed if provided
    if args.seed is not None:
        np.random.seed(args.seed)
        random.seed(args.seed)

    # Create output directory if it doesn't exist
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate data
    print(f"Generating {args.rows} rows of synthetic transaction data...")
    df = generate_synthetic_data(args.rows)

    # Save to CSV
    output_path = output_dir / args.filename
    df.to_csv(output_path, index=False, float_format='%.2f')

    # Print summary statistics
    print(f"\nData saved to: {output_path}")
    print(f"\nSummary Statistics:")
    print(f"  Total rows: {len(df)}")
    print(f"  Standard commission rows: {len(df[df['Label'] == 'standard'])}")
    print(f"  Outlier commission rows: {len(df[df['Label'] == 'outlier'])}")
    print(f"\nCommission rate distribution:")
    print(df['Commission_Rate'].value_counts().sort_index())
    print(f"\nTransaction statistics:")
    print(df['Transaction'].describe())
    print(f"\nTransaction Fee statistics:")
    print(df['Transaction_Fee'].describe())


if __name__ == '__main__':
    main()
