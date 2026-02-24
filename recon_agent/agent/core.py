from typing import List, Dict, Optional, Any, Tuple
from decimal import Decimal
from pathlib import Path

from agent.models.contract import DintaresContract
from agent.tools.contract_loader import load_contract
from agent.tools.excel_loader import load_excel_structure, load_transactions
from agent.tools.field_detector import (
    detect_fee_columns,
    calculate_overall_confidence,
    detect_commission_types_by_percentage
)
from agent.tools.fee_calculator import calculate_expected_fees
from agent.tools.rr_calculator import RollingReserveTracker, calculate_expected_rr
from agent.tools.fee_verifier import verify_transaction_fees
from agent.tools.report_generator import (
    generate_text_report,
    export_json_report,
    print_summary
)


class DintaresFeeVerificationAgent:
    """
    Fee verification agent.

    Coordinates all tools to verify transaction fees against contract terms.
    """

    def __init__(self, contract_file: str):
        """
        Initialize agent with contract.

        Args:
            contract_file: Path to contract JSON file
        """
        self.contract_file = contract_file
        self.contract: Optional[DintaresContract] = None
        self.rr_tracker: Optional[RollingReserveTracker] = None
        self.excel_structure: Optional[Dict] = None
        self.detected_columns: Optional[Dict] = None
        self.confidence_scores: Optional[Dict] = None
        self.detection_assumptions: List[str] = []

    def initialize(self):
        """Load contract and initialize RR tracker."""
        print("Loading contract...")
        self.contract = load_contract(self.contract_file)

        # Initialize Rolling Reserve tracker
        self.rr_tracker = RollingReserveTracker(
            cap=self.contract.rolling_reserve_cap,
            holding_days=self.contract.rolling_reserve_days
        )

        print(f"✓ Contract loaded: {Path(self.contract_file).name}")
        print(f"  - Remuneration: {self.contract.remuneration_rate * 100}%")
        print(f"  - Chargeback: €{self.contract.chargeback_cost}")
        print(f"  - Refund: €{self.contract.refund_cost}")
        print(f"  - Rolling Reserve: {self.contract.rolling_reserve_rate * 100}% (cap: €{self.contract.rolling_reserve_cap})")

    def run_discovery(self, excel_file: str) -> bool:
        """
        Run discovery mode to show Excel structure.

        Args:
            excel_file: Path to Excel file

        Returns:
            True if user confirms to proceed
        """
        print(f"\nDiscovering Excel structure: {Path(excel_file).name}")
        print("-" * 60)

        try:
            self.excel_structure = load_excel_structure(excel_file)
        except Exception as e:
            print(f"ERROR: Failed to load Excel structure: {e}")
            return False

        # Display sheets
        print(f"\nFound {len(self.excel_structure['sheets'])} sheet(s):")
        for sheet_name in self.excel_structure['sheets']:
            row_count = self.excel_structure['row_counts'].get(sheet_name, 0)
            col_count = len(self.excel_structure['columns_per_sheet'].get(sheet_name, []))
            header_row = self.excel_structure['header_rows'].get(sheet_name, 0)
            header_info = f" (headers in row {header_row + 1})" if header_row > 0 else ""
            print(f"  - {sheet_name}: {row_count:,} rows, {col_count} columns{header_info}")

        # Display detected Russian mappings
        if self.excel_structure['detected_mappings']:
            print(f"\nDetected Russian → English mappings:")
            for orig, norm in list(self.excel_structure['detected_mappings'].items())[:10]:
                print(f"  - {orig} → {norm}")

        # Show first sheet columns
        if self.excel_structure['sheets']:
            first_sheet = self.excel_structure['sheets'][0]
            columns = self.excel_structure['columns_per_sheet'][first_sheet]
            print(f"\nColumns in '{first_sheet}' ({len(columns)} total):")
            for i, col in enumerate(columns[:20], 1):
                normalized = self.excel_structure['normalized_columns'][first_sheet].get(col, col)
                print(f"  {i:2d}. {col} → {normalized}")
            if len(columns) > 20:
                print(f"  ... and {len(columns) - 20} more columns")

        print("\n" + "-" * 60)
        response = input("\nProceed with verification? (y/n): ").strip().lower()
        return response in ['y', 'yes']

    def verify_transactions(
        self,
        excel_file: str,
        sheet_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Verify all transactions in Excel file.

        Args:
            excel_file: Path to Excel file
            sheet_name: Specific sheet to process (default: first sheet)

        Returns:
            List of verification results
        """
        print(f"\nLoading transactions from: {Path(excel_file).name}")

        # Load transactions
        try:
            transactions = load_transactions(excel_file, sheet_name)
        except Exception as e:
            print(f"ERROR: Failed to load transactions: {e}")
            return []

        if not transactions:
            print("ERROR: No transactions found")
            return []

        print(f"✓ Loaded {len(transactions):,} transactions")

        # Detect fee columns
        print("\nDetecting fee columns...")
        column_names = list(transactions[0].keys()) if transactions else []
        detection_result = detect_fee_columns(column_names)

        self.detected_columns = detection_result["detected_columns"]
        self.confidence_scores = detection_result["confidence_scores"]

        # Display detected columns
        print("\nDetected columns:")
        for field_type, column_name in self.detected_columns.items():
            confidence = self.confidence_scores.get(field_type, 0.0)
            status = "✓" if confidence >= 0.7 else "?" if confidence > 0 else "✗"
            print(f"  {status} {field_type:20s} → {column_name or 'NOT FOUND':30s} (confidence: {confidence:.2f})")

        # Show ambiguities
        if detection_result["ambiguities"]:
            print("\nAmbiguities detected:")
            for ambiguity in detection_result["ambiguities"]:
                print(f"  ! {ambiguity}")

        # Perform percentage-based detection for commission types
        print("\nAnalyzing commission columns by percentage...")
        percentage_analysis = detect_commission_types_by_percentage(
            transactions,
            self.detected_columns,
            target_remuneration_pct=float(self.contract.remuneration_rate * 100),
            target_rr_pct=float(self.contract.rolling_reserve_rate * 100)
        )

        # Store assumptions for reporting
        self.detection_assumptions = percentage_analysis.get("assumptions", [])

        # Override detected columns with percentage-based detection
        if percentage_analysis["remuneration_column"]:
            self.detected_columns["commission"] = percentage_analysis["remuneration_column"]
            self.confidence_scores["commission"] = 1.0
            print(f"  ✓ Identified '{percentage_analysis['remuneration_column']}' as Remuneration "
                  f"({percentage_analysis['analysis'][percentage_analysis['remuneration_column']]['avg_percentage']:.2f}%)")

        if percentage_analysis["rolling_reserve_column"]:
            self.detected_columns["rolling_reserve"] = percentage_analysis["rolling_reserve_column"]
            self.confidence_scores["rolling_reserve"] = 1.0
            print(f"  ✓ Identified '{percentage_analysis['rolling_reserve_column']}' as Rolling Reserve "
                  f"({percentage_analysis['analysis'][percentage_analysis['rolling_reserve_column']]['avg_percentage']:.2f}%)")

        # Show other analyzed columns
        for col, analysis in percentage_analysis["analysis"].items():
            if analysis["matches"] == "unknown":
                print(f"  ? Column '{col}' averages {analysis['avg_percentage']:.2f}% (purpose unknown)")

        # Document when fee types are skipped due to missing/low-confidence columns
        chargeback_conf = self.confidence_scores.get("chargeback_fee", 0.0)
        refund_conf = self.confidence_scores.get("refund_fee", 0.0)

        if not self.detected_columns.get("chargeback_fee") or chargeback_conf < 0.7:
            self.detection_assumptions.append(
                "Chargeback verification skipped: No valid chargeback column found or confidence too low "
                f"(detected: '{self.detected_columns.get('chargeback_fee')}', confidence: {chargeback_conf:.2f})"
            )
            print(f"  ⊗ Chargeback verification will be skipped (no valid column found)")

        if not self.detected_columns.get("refund_fee") or refund_conf < 0.7:
            self.detection_assumptions.append(
                "Refund verification skipped: No valid refund column found or confidence too low "
                f"(detected: '{self.detected_columns.get('refund_fee')}', confidence: {refund_conf:.2f})"
            )
            print(f"  ⊗ Refund verification will be skipped (no valid column found)")

        # Calculate overall confidence
        overall_confidence, reasons = calculate_overall_confidence(
            self.confidence_scores,
            required_fields=["amount"]
        )
        print(f"\nOverall detection confidence: {overall_confidence:.2f}")
        for reason in reasons:
            print(f"  - {reason}")

        # Verify each transaction
        print(f"\nVerifying fees...")
        verifications = []

        for i, transaction in enumerate(transactions, 1):
            if i % 100 == 0:
                print(f"  Processed {i}/{len(transactions)} transactions...")

            # Calculate expected fees (including RR)
            expected_fees = calculate_expected_fees(
                transaction,
                self.contract,
                self.detected_columns,
                self.confidence_scores
            )

            # Calculate expected RR separately
            amount_str = transaction.get(self.detected_columns.get("amount"))
            if amount_str:
                try:
                    from agent.tools.excel_loader import parse_decimal
                    amount = parse_decimal(amount_str)
                    if amount:
                        rr_result = calculate_expected_rr(
                            amount,
                            self.contract.rolling_reserve_rate,
                            self.contract.rolling_reserve_cap
                        )
                        expected_fees["rolling_reserve"] = rr_result["rr_amount"]
                except:
                    pass

            # Verify fees
            verification = verify_transaction_fees(
                transaction,
                expected_fees,
                self.detected_columns,
                self.confidence_scores
            )

            verifications.append(verification)

        print(f"✓ Verified {len(verifications):,} transactions")

        return verifications

    def verify_all_sheets(
        self,
        excel_file: str
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Verify transactions in all sheets of the Excel file.

        Args:
            excel_file: Path to Excel file

        Returns:
            Tuple of (all_verifications, sheet_names)
        """
        import pandas as pd

        print(f"\nLoading Excel file to discover sheets...")

        try:
            xl = pd.ExcelFile(excel_file)
            sheet_names = xl.sheet_names
        except Exception as e:
            print(f"ERROR: Failed to load Excel file: {e}")
            return ([], [])

        print(f"Found {len(sheet_names)} sheet(s): {', '.join(sheet_names)}")
        print("=" * 60)

        all_verifications = []
        processed_sheets = []

        for i, sheet_name in enumerate(sheet_names, 1):
            print(f"\n[{i}/{len(sheet_names)}] Processing sheet: {sheet_name}")
            print("-" * 60)

            try:
                verifications = self.verify_transactions(excel_file, sheet_name)

                if verifications:
                    all_verifications.extend(verifications)
                    processed_sheets.append(sheet_name)
                    print(f"✓ Added {len(verifications):,} verifications from '{sheet_name}'")
                else:
                    print(f"⊗ No transactions found in '{sheet_name}'")

            except Exception as e:
                print(f"✗ Error processing '{sheet_name}': {e}")
                continue

        print("\n" + "=" * 60)
        print(f"Total verifications collected: {len(all_verifications):,} from {len(processed_sheets)} sheet(s)")

        return (all_verifications, processed_sheets)

    def export_results(
        self,
        verifications: List[Dict[str, Any]],
        excel_file: str,
        sheet_name: Optional[str],
        output_prefix: str
    ):
        """
        Export verification results to text and JSON.

        Args:
            verifications: List of verification results
            excel_file: Excel file path
            sheet_name: Sheet name
            output_prefix: Output file prefix
        """
        print(f"\nGenerating reports...")

        # Generate text report
        txt_path = f"{output_prefix}.txt"
        generate_text_report(
            verifications,
            self.contract_file,
            excel_file,
            sheet_name,
            txt_path,
            detection_assumptions=self.detection_assumptions
        )
        print(f"✓ Text report: {txt_path}")

        # Generate JSON report
        json_path = f"{output_prefix}.json"
        export_json_report(
            verifications,
            self.contract_file,
            excel_file,
            sheet_name,
            json_path,
            detection_assumptions=self.detection_assumptions
        )
        print(f"✓ JSON report: {json_path}")

        # Print summary
        print_summary(verifications)
