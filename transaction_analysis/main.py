#!/usr/bin/env python3
"""CLI interface for transaction fee verification agent."""

import argparse
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

from agent.core import TransactionVerificationAgent

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Transaction Fee Verification Agent - Verify transaction fees against contract terms"
    )

    parser.add_argument(
        "--contract",
        type=str,
        default="data/parsed_contract.json",
        help="Path to contract JSON file (default: data/parsed_contract.json)"
    )

    parser.add_argument(
        "--transactions",
        type=str,
        default="data/transaction_table.csv",
        help="Path to transaction CSV file (default: data/transaction_table.csv)"
    )

    parser.add_argument(
        "--output",
        type=str,
        default="output/discrepancy_report.json",
        help="Path to output files (generates .json and .txt) (default: output/discrepancy_report.json)"
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of transactions to process per batch (default: 10)"
    )

    parser.add_argument(
        "--max-transactions",
        type=int,
        default=None,
        help="Maximum number of transactions to process (default: all)"
    )

    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Anthropic API key (default: from ANTHROPIC_API_KEY env var)"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load environment variables
    load_dotenv()

    # Get API key
    api_key = args.api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("No API key provided. Set ANTHROPIC_API_KEY environment variable or use --api-key")
        sys.exit(1)

    # Check files exist
    if not Path(args.contract).exists():
        logger.error(f"Contract file not found: {args.contract}")
        sys.exit(1)

    if not Path(args.transactions).exists():
        logger.error(f"Transaction file not found: {args.transactions}")
        sys.exit(1)

    # Create agent
    logger.info("Initializing Transaction Verification Agent...")
    agent = TransactionVerificationAgent(
        api_key=api_key,
        contract_file=args.contract
    )

    # Run verification
    try:
        logger.info(f"Processing transactions from {args.transactions}")
        discrepancies = agent.run(
            transaction_file=args.transactions,
            batch_size=args.batch_size,
            max_transactions=args.max_transactions
        )

        # Export results
        agent.export_results(args.output)

        # Print summary
        print("\n" + "="*60)
        print("VERIFICATION COMPLETE")
        print("="*60)
        print(f"Total discrepancies found: {len(discrepancies)}")

        if discrepancies:
            text_file = args.output.replace('.json', '.txt')
            print(f"\nResults saved to:")
            print(f"  - JSON: {args.output}")
            print(f"  - Text: {text_file}")
            print("\nSample discrepancies:")
            for i, disc in enumerate(discrepancies[:3]):
                print(f"\n{i+1}. Transaction ID: {disc.get('transaction_id')}")
                print(f"   Status: {disc.get('status', disc.get('error', 'Unknown'))}")
                if 'actual_commission' in disc:
                    print(f"   Actual: {disc.get('actual_commission')}, Expected: {disc.get('expected_commission')}")
        else:
            print("\n✓ No fee discrepancies found!")

        print("\n" + "="*60)

    except KeyboardInterrupt:
        logger.info("\nVerification interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error during verification: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
