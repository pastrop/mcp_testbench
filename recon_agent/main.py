#!/usr/bin/env python3
"""
DINTARES Fee Verification Agent

Verifies transaction fees against DINTARES contract terms.
"""

import argparse
import sys
from pathlib import Path

from agent.core import DintaresFeeVerificationAgent


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Verify DINTARES transaction fees against contract terms",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Auto-discover and verify transactions (uses files from data/ directory)
  python main.py

  # Run discovery mode to see Excel structure
  python main.py --discovery

  # Verify all sheets
  python main.py --all-sheets

  # Specify custom files
  python main.py --contract data/contract.json --excel data/transactions.xlsx

  # Verify specific sheet with custom output
  python main.py --sheet "EUR (F)" --output output/eur_report
        """
    )

    parser.add_argument(
        '--excel',
        default=None,
        help='Path to Excel file with transactions (auto-discovers if not specified)'
    )

    parser.add_argument(
        '--contract',
        default=None,
        help='Path to contract JSON file (auto-discovers if not specified)'
    )

    parser.add_argument(
        '--output',
        default='output/fee_verification_report',
        help='Output file prefix (default: output/fee_verification_report)'
    )

    parser.add_argument(
        '--discovery',
        action='store_true',
        help='Run discovery mode to show Excel structure before verification'
    )

    parser.add_argument(
        '--sheet',
        default=None,
        help='Specific sheet name to process (default: first sheet)'
    )

    parser.add_argument(
        '--all-sheets',
        action='store_true',
        help='Process all sheets in the Excel file (generates combined report)'
    )

    parser.add_argument(
        '--confidence-threshold',
        type=float,
        default=0.5,
        help='Confidence threshold for questionable transactions (default: 0.5)'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )

    args = parser.parse_args()

    # Auto-discover contract file if not specified
    if args.contract is None:
        try:
            from agent.tools.contract_loader import discover_contract_file
            contract_path = Path(discover_contract_file())
            print(f"Auto-discovered contract: {contract_path.name}")
        except Exception as e:
            print("=" * 60)
            print("ERROR: Could not auto-discover contract file")
            print("=" * 60)
            print(f"{e}")
            sys.exit(1)
    else:
        contract_path = Path(args.contract)
        if not contract_path.exists():
            print("=" * 60)
            print("ERROR: Contract file not found")
            print("=" * 60)
            print(f"Path: {contract_path}")
            print("\nPlease check the file path and try again.")
            sys.exit(1)

    # Auto-discover Excel file if not specified
    if args.excel is None:
        try:
            from agent.tools.excel_loader import discover_excel_file
            excel_path = Path(discover_excel_file())
            print(f"Auto-discovered Excel file: {excel_path.name}")
        except Exception as e:
            print("=" * 60)
            print("ERROR: Could not auto-discover Excel file")
            print("=" * 60)
            print(f"{e}")
            sys.exit(1)
    else:
        excel_path = Path(args.excel)
        if not excel_path.exists():
            print("=" * 60)
            print("ERROR: Excel file not found")
            print("=" * 60)
            print(f"Path: {excel_path}")
            print("\nPlease check the file path and try again.")
            sys.exit(1)

    # Create output directory if needed
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Banner
    print("=" * 60)
    print("FEE VERIFICATION AGENT")
    print("=" * 60)

    try:
        # Initialize agent
        agent = DintaresFeeVerificationAgent(str(contract_path))
        agent.initialize()

        # Discovery mode
        if args.discovery:
            proceed = agent.run_discovery(str(excel_path))
            if not proceed:
                print("\nVerification cancelled by user.")
                sys.exit(0)

        # Verify transactions
        if args.all_sheets:
            # Process all sheets
            verifications, sheet_names = agent.verify_all_sheets(str(excel_path))
            sheet_identifier = "all_sheets"
        else:
            # Process single sheet
            verifications = agent.verify_transactions(
                str(excel_path),
                sheet_name=args.sheet
            )
            sheet_names = [args.sheet] if args.sheet else None
            sheet_identifier = args.sheet

        if not verifications:
            print("\nERROR: No verifications performed")
            sys.exit(1)

        # Export results
        agent.export_results(
            verifications,
            str(excel_path),
            sheet_identifier,
            str(output_path)
        )

        print("\n" + "=" * 60)
        print("VERIFICATION COMPLETE")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\n\nVerification interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print("\n" + "=" * 60)
        print("ERROR")
        print("=" * 60)
        print(f"{e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
