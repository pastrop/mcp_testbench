#!/usr/bin/env python3
"""
Generate sample transaction data for testing the Pandas Query Agent.

This creates a realistic dataset with the required columns for demonstration purposes.
"""

import random
from datetime import datetime, timedelta

import pandas as pd


def generate_sample_data(num_rows: int = 1000) -> pd.DataFrame:
    """Generate sample transaction data."""

    # Seed for reproducibility
    random.seed(42)

    # Sample data generators
    card_brands = ["Visa", "Mastercard", "Amex", "Discover", "UnionPay"]
    traffic_types = ["Online", "POS", "Mobile", "ATM", "Recurring"]
    countries = ["US", "UK", "DE", "FR", "ES", "IT", "NL", "BE", "CA", "AU"]
    merchants = [f"Merchant_{i}" for i in range(1, 51)]
    companies = [f"Company_{chr(65+i)}" for i in range(10)]
    processors = ["Stripe", "Adyen", "PayPal", "Square", "Braintree"]
    transaction_types = ["purchase", "refund", "authorization", "capture", "void"]
    transaction_statuses = ["completed", "pending", "failed", "cancelled", "processing"]
    card_types = ["credit", "debit", "prepaid", "virtual"]

    data = []

    start_date = datetime(2024, 1, 1)

    for i in range(num_rows):
        # Generate transaction data
        amount = round(random.uniform(10, 5000), 2)
        commission_rate = random.uniform(0.01, 0.05)
        commission = round(amount * commission_rate, 2)
        transaction_commission = round(random.uniform(0.1, 2.0), 2)
        agent_fee = round(random.uniform(0, 50), 2)
        tax_reserve = round(amount * random.uniform(0.0, 0.15), 2)
        monthly_fee = round(random.uniform(0, 100), 2) if random.random() > 0.7 else 0

        created_date = start_date + timedelta(
            days=random.randint(0, 300),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59)
        )

        merchant = random.choice(merchants)
        company = random.choice(companies)

        row = {
            "comission_eur": commission,
            "amount_eur": amount,
            "card_brand_group": random.choice(card_brands),
            "traffic_type_group": random.choice(traffic_types),
            "transaction_comission": transaction_commission,
            "country": random.choice(countries),
            "order_id": f"ORD-{i+1:06d}",
            "created_date": created_date.strftime("%Y-%m-%d %H:%M:%S"),
            "manager_id": f"MGR-{random.randint(1, 20):03d}",
            "merchant_name": merchant,
            "gate_id": f"GATE-{random.randint(1, 10):02d}",
            "merchant_id": f"MERCH-{merchants.index(merchant)+1:03d}",
            "company_id": f"COMP-{companies.index(company)+1:02d}",
            "company_name": company,
            "white_label_id": f"WL-{random.randint(1, 5):02d}",
            "processor_name": random.choice(processors),
            "processor_id": f"PROC-{random.randint(1, 5):02d}",
            "transaction_type": random.choice(transaction_types),
            "transaction_status": random.choice(transaction_statuses),
            "agent_fee": agent_fee,
            "card_type": random.choice(card_types),
            "tax_reserve_cost": tax_reserve,
            "monthly_fee": monthly_fee,
            "item_id": f"ITEM-{random.randint(1, 100):04d}",
            "records": random.randint(1, 10)
        }

        data.append(row)

    df = pd.DataFrame(data)
    return df


def main():
    """Generate and save sample data."""
    import sys

    # Parse arguments
    num_rows = 1000
    output_file = "sample_transactions.csv"

    if len(sys.argv) > 1:
        num_rows = int(sys.argv[1])

    if len(sys.argv) > 2:
        output_file = sys.argv[2]

    print(f"Generating {num_rows} sample transactions...")
    df = generate_sample_data(num_rows)

    print(f"Saving to {output_file}...")
    if output_file.endswith(".csv"):
        df.to_csv(output_file, index=False)
    elif output_file.endswith(".parquet"):
        df.to_parquet(output_file, index=False)
    elif output_file.endswith(".json"):
        df.to_json(output_file, orient="records", indent=2)
    else:
        print(f"Unsupported format. Defaulting to CSV.")
        output_file = output_file.rsplit(".", 1)[0] + ".csv"
        df.to_csv(output_file, index=False)

    print(f"\nSuccess! Generated {len(df)} rows with {len(df.columns)} columns")
    print(f"File saved: {output_file}")
    print(f"File size: {os.path.getsize(output_file) / 1024:.2f} KB")

    # Display sample
    print("\nSample data (first 5 rows):")
    print(df.head())

    print("\nData summary:")
    print(f"  Total transaction amount: €{df['amount_eur'].sum():,.2f}")
    print(f"  Total commission: €{df['comission_eur'].sum():,.2f}")
    print(f"  Average transaction: €{df['amount_eur'].mean():.2f}")
    print(f"  Date range: {df['created_date'].min()} to {df['created_date'].max()}")
    print(f"  Unique merchants: {df['merchant_name'].nunique()}")
    print(f"  Unique countries: {df['country'].nunique()}")


if __name__ == "__main__":
    import os
    main()
