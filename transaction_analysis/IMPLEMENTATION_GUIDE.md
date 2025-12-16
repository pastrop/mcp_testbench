# Implementation Guide: Transaction Fee Verification Agent

## Quick Start Overview

This guide provides concrete implementation examples for the agent tools and shows how to build the system step-by-step.

---

## Tool Implementation Examples

### 1. Data Loader Tools

#### `load_contract_data.py`
```python
import json
from typing import Dict, List
from pydantic import BaseModel

class ContractRule(BaseModel):
    wl_rate: float = 0.0
    fixed_fee: float = 0.0
    refund_fee: float = 0.0
    chb_fee: float = 0.0
    currency: str
    region: str = "WW"

def load_contract_data(file_path: str) -> Dict:
    """
    Load and parse contract JSON file.

    Returns:
        {
            "raw_data": dict,
            "card_fees": dict,
            "apm_fees": dict,
            "outgoing_fees": dict,
            "settlement_fees": dict,
            "currencies": list,
            "regions": list,
            "payment_methods": list
        }
    """
    with open(file_path, 'r') as f:
        data = json.load(f)

    # Extract metadata
    currencies = set()
    regions = set()
    payment_methods = set()

    # Parse card fees
    for key, value in data.get("card_fees", {}).items():
        currencies.add(value.get("currency"))
        regions.add(value.get("region"))
        payment_methods.add("card")

    # Parse APM fees
    for key, value in data.get("apm_open_banking_fees", {}).items():
        if isinstance(value, dict) and "currency" in value:
            currencies.add(value.get("currency"))
            regions.add(value.get("region"))
            payment_methods.add(key.split("_")[0])  # e.g., "sofort", "blik"

    # Parse outgoing fees
    for category, methods in data.get("outgoing_fees", {}).items():
        if isinstance(methods, dict):
            for method, details in methods.items():
                if isinstance(details, dict):
                    currencies.add(details.get("currency"))
                    payment_methods.add(category)

    return {
        "raw_data": data,
        "card_fees": data.get("card_fees", {}),
        "apm_fees": data.get("apm_open_banking_fees", {}),
        "outgoing_fees": data.get("outgoing_fees", {}),
        "settlement_fees": data.get("settlement_fees", {}),
        "crypto_fees": data.get("incoming_fees", {}).get("crypto", {}),
        "excessive_cb_fees": data.get("excessive_chargeback_fees", {}),
        "fx_fees": data.get("currency_exchange_fees", {}),
        "currencies": sorted(list(currencies)),
        "regions": sorted(list(regions)),
        "payment_methods": sorted(list(payment_methods))
    }
```

#### `load_transaction_data.py`
```python
import pandas as pd
from typing import Dict, List, Optional

def load_transaction_data(
    file_path: str,
    limit: Optional[int] = None,
    offset: int = 0,
    filters: Optional[Dict] = None
) -> Dict:
    """
    Load transaction data from CSV with optional filtering.

    Args:
        file_path: Path to CSV file
        limit: Maximum number of rows to load
        offset: Number of rows to skip
        filters: Dict of column filters, e.g., {"status": "approved"}

    Returns:
        {
            "transactions": list of dicts,
            "total_count": int,
            "columns": list of column names,
            "has_more": bool
        }
    """
    # Read with chunking for large files
    if limit:
        df = pd.read_csv(file_path, skiprows=range(1, offset+1), nrows=limit)
    else:
        df = pd.read_csv(file_path, skiprows=range(1, offset+1))

    # Get total count (approximate if using limit)
    total_count = len(df) if not limit else len(df) + offset

    # Apply filters
    if filters:
        for column, value in filters.items():
            if column in df.columns:
                df = df[df[column] == value]

    # Convert to list of dicts
    transactions = df.to_dict('records')

    return {
        "transactions": transactions,
        "total_count": total_count,
        "columns": list(df.columns),
        "has_more": limit is not None and len(df) == limit
    }

def get_transaction_batch(
    file_path: str,
    batch_size: int = 100,
    batch_number: int = 0
) -> Dict:
    """
    Get a specific batch of transactions.

    Args:
        file_path: Path to CSV file
        batch_size: Number of transactions per batch
        batch_number: Which batch to retrieve (0-indexed)

    Returns:
        Same as load_transaction_data
    """
    offset = batch_number * batch_size
    return load_transaction_data(file_path, limit=batch_size, offset=offset)
```

---

### 2. Mapping & Matcher Tools

#### `field_mapper.py`
```python
from typing import Dict, List, Tuple

# Field mapping dictionary
FIELD_MAPPINGS = {
    "comission_eur": "commission_total",
    "mdr_eur": "merchant_discount_rate",
    "base_eur": "base_fee",
    "fixed_eur": "fixed_fee",
    "min_eur": "minimum_fee",
    "amount_eur": "amount",
    "traffic_type_group": "payment_method",
    "gate_name": "gateway_name",
    "card_brand": "card_type",
    "transaction_type": "type",
    "transaction_status": "status"
}

# Reverse mappings for inference
PAYMENT_METHOD_INDICATORS = {
    "apple_pay": ["apple_pay", "applepay", "apple pay"],
    "google_pay": ["google_pay", "googlepay", "google pay"],
    "sepa": ["sepa"],
    "card": ["card", "wl", "visa", "mastercard"],
    "blik": ["blik"],
    "sofort": ["sofort"],
    "open_banking": ["open_banking", "openbanking"]
}

def map_transaction_fields(
    transaction: Dict,
    available_columns: List[str]
) -> Dict:
    """
    Map transaction CSV fields to standardized names.

    Args:
        transaction: Raw transaction dict
        available_columns: List of available column names

    Returns:
        {
            "mapped_fields": dict with standardized field names,
            "unmapped_fields": list of fields that couldn't be mapped,
            "assumptions": list of dicts documenting mapping decisions
        }
    """
    mapped_fields = {}
    unmapped_fields = []
    assumptions = []

    for key, value in transaction.items():
        if key in FIELD_MAPPINGS:
            mapped_key = FIELD_MAPPINGS[key]
            mapped_fields[mapped_key] = value
            if key != mapped_key:
                assumptions.append({
                    "original_field": key,
                    "mapped_to": mapped_key,
                    "assumption": f"Mapped '{key}' to standardized field '{mapped_key}'"
                })
        else:
            # Keep original field name if no mapping
            mapped_fields[key] = value
            if key not in ["transaction_id", "order_id", "created_date"]:  # Skip known fields
                unmapped_fields.append(key)

    return {
        "mapped_fields": mapped_fields,
        "unmapped_fields": unmapped_fields,
        "assumptions": assumptions
    }

def infer_payment_method(transaction: Dict) -> Dict:
    """
    Infer payment method from transaction data.

    Args:
        transaction: Mapped transaction dict

    Returns:
        {
            "payment_method": str,
            "confidence": float (0.0-1.0),
            "evidence": list of strings explaining the inference
        }
    """
    evidence = []
    confidence = 0.0
    payment_method = "unknown"

    # Check explicit payment method field
    if "traffic_type_group" in transaction:
        traffic_type = str(transaction["traffic_type_group"]).lower()
        for method, indicators in PAYMENT_METHOD_INDICATORS.items():
            if any(ind in traffic_type for ind in indicators):
                payment_method = method
                confidence = 0.95
                evidence.append(f"traffic_type_group='{traffic_type}' indicates {method}")
                return {"payment_method": payment_method, "confidence": confidence, "evidence": evidence}

    # Check gate_name field
    if "gate_name" in transaction:
        gate_name = str(transaction["gate_name"]).lower()
        for method, indicators in PAYMENT_METHOD_INDICATORS.items():
            if any(ind in gate_name for ind in indicators):
                payment_method = method
                confidence = 0.85
                evidence.append(f"gate_name='{gate_name}' suggests {method}")
                return {"payment_method": payment_method, "confidence": confidence, "evidence": evidence}

    # Check card_brand field for card transactions
    if "card_brand" in transaction and transaction["card_brand"]:
        card_brand = str(transaction["card_brand"]).upper()
        if card_brand in ["VISA", "MASTERCARD", "AMEX"]:
            payment_method = "card"
            confidence = 0.90
            evidence.append(f"card_brand='{card_brand}' indicates card transaction")
            return {"payment_method": payment_method, "confidence": confidence, "evidence": evidence}

    # Default fallback
    if payment_method == "unknown":
        evidence.append("Could not determine payment method from available fields")
        confidence = 0.0

    return {
        "payment_method": payment_method,
        "confidence": confidence,
        "evidence": evidence
    }
```

#### `contract_matcher.py`
```python
from typing import Dict, List, Optional

def find_applicable_contract_rule(
    contract_data: Dict,
    currency: str,
    payment_method: str,
    region: Optional[str] = None,
    card_brand: Optional[str] = None,
    transaction_type: str = "payment",
    amount: Optional[float] = None,
    monthly_volume: Optional[float] = None
) -> Dict:
    """
    Find applicable contract rule(s) for a transaction.

    Returns:
        {
            "rules": list of matching rules,
            "best_match": dict or None,
            "ambiguities": list of strings,
            "confidence": float
        }
    """
    matching_rules = []
    ambiguities = []

    # Normalize inputs
    currency = currency.upper()
    payment_method = payment_method.lower()

    # Search in card fees
    if payment_method in ["card", "wl", "apple_pay", "google_pay"]:
        card_fees = contract_data.get("card_fees", {})

        for rule_key, rule in card_fees.items():
            # Match currency
            if rule.get("currency") != currency:
                continue

            # Match region if provided
            if region:
                rule_region = rule.get("region", "WW")
                if region.upper() not in [rule_region, "WW"]:
                    # Check if region is in EEA and rule applies to EEA
                    if not (region.upper() in ["DE", "PL", "FR"] and rule_region == "EEA"):
                        continue

            matching_rules.append({
                "category": "card_fees",
                "rule_key": rule_key,
                "rule": rule,
                "match_score": calculate_match_score(rule, currency, region, card_brand)
            })

    # Search in APM fees
    if payment_method in ["apple_pay", "google_pay", "blik", "sofort", "open_banking"]:
        apm_fees = contract_data.get("apm_fees", {})

        for rule_key, rule in apm_fees.items():
            if payment_method in rule_key.lower():
                if isinstance(rule, dict) and "currency" in rule:
                    if rule.get("currency") == currency:
                        matching_rules.append({
                            "category": "apm_fees",
                            "rule_key": rule_key,
                            "rule": rule,
                            "match_score": calculate_match_score(rule, currency, region, None)
                        })
                # Handle tiered structures
                elif isinstance(rule, dict) and "tier" in rule_key.lower():
                    # This is a tiered fee structure
                    applicable_tier = determine_tier(rule, monthly_volume, amount)
                    if applicable_tier:
                        matching_rules.append({
                            "category": "apm_fees",
                            "rule_key": rule_key,
                            "tier": applicable_tier,
                            "rule": rule.get(applicable_tier, {}),
                            "match_score": calculate_match_score(rule.get(applicable_tier, {}), currency, region, None)
                        })

    # Search in outgoing fees
    if transaction_type in ["payout", "withdrawal"]:
        outgoing_fees = contract_data.get("outgoing_fees", {})

        if payment_method == "sepa":
            sepa_fees = outgoing_fees.get("sepa", {})
            for rule_key, rule in sepa_fees.items():
                if rule.get("currency") == currency:
                    matching_rules.append({
                        "category": "outgoing_fees.sepa",
                        "rule_key": rule_key,
                        "rule": rule,
                        "match_score": 0.9
                    })

        elif payment_method == "card":
            card_payouts = outgoing_fees.get("cards", {})
            for rule_key, rule in card_payouts.items():
                if rule.get("currency") == currency:
                    matching_rules.append({
                        "category": "outgoing_fees.cards",
                        "rule_key": rule_key,
                        "rule": rule,
                        "match_score": calculate_match_score(rule, currency, region, card_brand)
                    })

    # Determine best match
    if not matching_rules:
        return {
            "rules": [],
            "best_match": None,
            "ambiguities": [f"No matching rule found for {payment_method}/{currency}/{transaction_type}"],
            "confidence": 0.0
        }

    # Sort by match score
    matching_rules.sort(key=lambda x: x["match_score"], reverse=True)
    best_match = matching_rules[0]

    # Check for ambiguity
    if len(matching_rules) > 1:
        if matching_rules[1]["match_score"] >= matching_rules[0]["match_score"] - 0.1:
            ambiguities.append(f"Multiple rules match with similar scores: {[r['rule_key'] for r in matching_rules[:3]]}")

    # Calculate confidence
    confidence = best_match["match_score"]
    if ambiguities:
        confidence *= 0.8

    return {
        "rules": matching_rules,
        "best_match": best_match,
        "ambiguities": ambiguities,
        "confidence": confidence
    }

def calculate_match_score(
    rule: Dict,
    currency: str,
    region: Optional[str],
    card_brand: Optional[str]
) -> float:
    """Calculate how well a rule matches the transaction characteristics."""
    score = 0.5  # base score

    # Currency match is critical
    if rule.get("currency") == currency:
        score += 0.3

    # Region match
    if region:
        rule_region = rule.get("region", "WW")
        if rule_region == "WW":
            score += 0.1  # Universal rule
        elif rule_region == region:
            score += 0.2  # Exact match
        elif region in ["DE", "FR", "PL"] and rule_region == "EEA":
            score += 0.15  # EEA match

    # Card brand match (if applicable)
    if card_brand and "card_brand" in rule:
        if rule["card_brand"].lower() == card_brand.lower():
            score += 0.1

    return min(score, 1.0)

def determine_tier(tier_structure: Dict, monthly_volume: Optional[float], amount: float) -> Optional[str]:
    """Determine which tier applies based on monthly volume."""
    if not monthly_volume:
        # Default to tier 1 if volume unknown
        return "tier_1_0_to_500k" if "tier_1" in str(tier_structure) else None

    # Parse tier boundaries from keys
    # Example: "tier_1_0_to_500k" -> 0 to 500,000
    # This is simplified; production code should parse these properly
    if monthly_volume < 500000:
        return "tier_1_0_to_500k"
    elif monthly_volume < 1000000:
        return "tier_2_500k_to_1m"
    else:
        return "tier_3_over_1m"
```

---

### 3. Fee Calculator Tools

#### `fee_calculator.py`
```python
from typing import Dict, Optional
from decimal import Decimal, ROUND_HALF_UP

def calculate_expected_fees(
    amount: float,
    contract_rule: Dict,
    transaction_type: str = "payment"
) -> Dict:
    """
    Calculate expected fees based on contract rule.

    Args:
        amount: Transaction amount
        contract_rule: The contract rule dict from find_applicable_contract_rule
        transaction_type: payment, payout, refund, or chargeback

    Returns:
        {
            "breakdown": {
                "percentage_fee": float,
                "fixed_fee": float,
                "total": float,
                "components": dict
            },
            "calculation_method": str,
            "applicable_rates": dict
        }
    """
    rule = contract_rule.get("rule", contract_rule)

    # Use Decimal for precise calculations
    amount_decimal = Decimal(str(amount))

    # Initialize components
    percentage_fee = Decimal("0")
    fixed_fee = Decimal("0")

    # Calculate based on transaction type
    if transaction_type == "payment":
        # Standard payment fee: (amount * wl_rate) + fixed_fee
        wl_rate = Decimal(str(rule.get("wl_rate", 0.0)))
        fixed_fee = Decimal(str(rule.get("fixed_fee", 0.0)))
        percentage_fee = amount_decimal * wl_rate

        calculation_method = f"Payment fee: ({amount} × {wl_rate}) + {fixed_fee}"

    elif transaction_type == "refund":
        # Refund fee is usually just the refund_fee
        fixed_fee = Decimal(str(rule.get("refund_fee", 0.0)))
        percentage_fee = Decimal("0")

        calculation_method = f"Refund fee: {fixed_fee} (flat)"

    elif transaction_type == "chargeback":
        # Chargeback fee
        fixed_fee = Decimal(str(rule.get("chb_fee", 0.0)))
        percentage_fee = Decimal("0")

        calculation_method = f"Chargeback fee: {fixed_fee} (flat)"

    elif transaction_type in ["payout", "withdrawal"]:
        # Outgoing transaction
        rate = Decimal(str(rule.get("rate", 0.0)))
        percentage_fee = amount_decimal * rate

        # Check for fixed payout fee
        if "payout_oct_fix" in rule:
            fixed_fee = Decimal(str(rule.get("payout_oct_fix", 0.0)))

        # Check for minimum payout fee
        if "payout_oct_min" in rule:
            min_fee = Decimal(str(rule.get("payout_oct_min", 0.0)))
            total_before_min = percentage_fee + fixed_fee
            if total_before_min < min_fee:
                fixed_fee = min_fee - percentage_fee

        calculation_method = f"Payout fee: ({amount} × {rate}) + {fixed_fee}"

    else:
        calculation_method = "Unknown transaction type"

    # Calculate total
    total = percentage_fee + fixed_fee

    # Round to 2 decimal places (standard for currency)
    percentage_fee = float(percentage_fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    fixed_fee = float(fixed_fee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    total = float(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    return {
        "breakdown": {
            "percentage_fee": percentage_fee,
            "fixed_fee": fixed_fee,
            "total": total,
            "components": {
                "wl_rate": rule.get("wl_rate"),
                "fixed_fee_rate": rule.get("fixed_fee"),
                "refund_fee": rule.get("refund_fee"),
                "chb_fee": rule.get("chb_fee")
            }
        },
        "calculation_method": calculation_method,
        "applicable_rates": {
            "wl_rate": rule.get("wl_rate", 0.0),
            "fixed_fee": rule.get("fixed_fee", 0.0),
            "rate": rule.get("rate", 0.0)
        }
    }

def compare_fees(
    actual_fee: float,
    expected_fee: float,
    tolerance: float = 0.01
) -> Dict:
    """
    Compare actual vs expected fees.

    Args:
        actual_fee: Fee that was actually charged
        expected_fee: Fee calculated from contract
        tolerance: Acceptable difference (default 0.01 = 1 cent)

    Returns:
        {
            "is_correct": bool,
            "difference_amount": float,
            "difference_percentage": float,
            "within_tolerance": bool,
            "status": str
        }
    """
    difference = actual_fee - expected_fee

    # Calculate percentage difference
    if expected_fee != 0:
        diff_percentage = (difference / expected_fee) * 100
    else:
        diff_percentage = 0.0 if difference == 0 else float('inf')

    # Check if within tolerance
    within_tolerance = abs(difference) <= tolerance

    # Determine status
    if within_tolerance:
        status = "CORRECT"
    elif difference > 0:
        status = "OVERCHARGED"
    else:
        status = "UNDERCHARGED"

    return {
        "is_correct": within_tolerance,
        "difference_amount": round(difference, 2),
        "difference_percentage": round(diff_percentage, 2),
        "within_tolerance": within_tolerance,
        "status": status
    }
```

---

### 4. Agent Orchestrator

#### `main.py`
```python
import json
from typing import Dict, List
from agent.tools.data_loader import load_contract_data, load_transaction_data
from agent.tools.field_mapper import map_transaction_fields, infer_payment_method
from agent.tools.contract_matcher import find_applicable_contract_rule
from agent.tools.fee_calculator import calculate_expected_fees, compare_fees

class TransactionFeeVerificationAgent:
    """Main agent orchestrator for transaction fee verification."""

    def __init__(self, contract_file: str, transaction_file: str):
        self.contract_file = contract_file
        self.transaction_file = transaction_file
        self.contract_data = None
        self.discrepancies = []

    def initialize(self):
        """Load contract and prepare for verification."""
        print("Loading contract data...")
        self.contract_data = load_contract_data(self.contract_file)
        print(f"Contract loaded: {len(self.contract_data['currencies'])} currencies, "
              f"{len(self.contract_data['payment_methods'])} payment methods")

    def verify_transaction(self, transaction: Dict) -> Optional[Dict]:
        """
        Verify a single transaction.

        Returns:
            Discrepancy report dict if fee is incorrect, None if correct
        """
        # Step 1: Map fields
        mapped = map_transaction_fields(transaction, list(transaction.keys()))
        tx = mapped["mapped_fields"]
        assumptions = mapped["assumptions"]

        # Step 2: Extract key characteristics
        amount = float(tx.get("amount", tx.get("amount_eur", 0)))
        currency = tx.get("currency", "EUR")
        actual_commission = float(tx.get("commission_total", tx.get("comission_eur", 0)))
        transaction_type = tx.get("type", "payment")
        status = tx.get("status", "unknown")

        # Skip declined transactions (no fees should be charged)
        if status == "declined":
            if actual_commission != 0:
                # This is an error - fees on declined transaction
                return self.generate_error_report(
                    transaction,
                    "Fee charged on declined transaction",
                    1.0
                )
            return None  # Correctly no fee on declined

        # Step 3: Infer payment method
        payment_info = infer_payment_method(tx)
        payment_method = payment_info["payment_method"]
        pm_confidence = payment_info["confidence"]
        assumptions.extend([{"assumption": e} for e in payment_info["evidence"]])

        if payment_method == "unknown":
            return self.generate_error_report(
                transaction,
                "Could not determine payment method",
                0.0
            )

        # Step 4: Find applicable contract rule
        rule_match = find_applicable_contract_rule(
            self.contract_data,
            currency=currency,
            payment_method=payment_method,
            region=tx.get("country"),
            card_brand=tx.get("card_brand"),
            transaction_type=transaction_type,
            amount=amount
        )

        if not rule_match["best_match"]:
            return self.generate_error_report(
                transaction,
                f"No contract rule found for {payment_method}/{currency}",
                0.0
            )

        # Step 5: Calculate expected fees
        expected = calculate_expected_fees(
            amount=amount,
            contract_rule=rule_match["best_match"],
            transaction_type=transaction_type
        )

        # Step 6: Compare fees
        comparison = compare_fees(
            actual_fee=actual_commission,
            expected_fee=expected["breakdown"]["total"],
            tolerance=0.01
        )

        # Step 7: Calculate overall confidence
        confidence = min(
            pm_confidence,
            rule_match["confidence"]
        )

        # Adjust confidence based on ambiguities
        if rule_match["ambiguities"]:
            confidence *= 0.9
        if len(assumptions) > 3:
            confidence *= 0.95

        # Step 8: Generate report if discrepancy found
        if not comparison["is_correct"]:
            return self.generate_discrepancy_report(
                transaction=transaction,
                actual_fee=actual_commission,
                expected_fee=expected["breakdown"]["total"],
                comparison=comparison,
                expected_breakdown=expected,
                rule_match=rule_match,
                payment_method=payment_method,
                assumptions=assumptions,
                confidence=confidence
            )

        return None  # Fee is correct

    def generate_discrepancy_report(
        self,
        transaction: Dict,
        actual_fee: float,
        expected_fee: float,
        comparison: Dict,
        expected_breakdown: Dict,
        rule_match: Dict,
        payment_method: str,
        assumptions: List[Dict],
        confidence: float
    ) -> Dict:
        """Generate detailed discrepancy report."""

        # Generate reasoning
        reasoning = f"Expected fee calculation: {expected_breakdown['calculation_method']}. "
        reasoning += f"Expected total: {expected_fee:.2f}. "
        reasoning += f"Actual charged: {actual_fee:.2f}. "
        reasoning += f"Difference: {comparison['difference_amount']:.2f} ({comparison['difference_percentage']:.1f}%). "

        if comparison["status"] == "OVERCHARGED":
            reasoning += "Transaction was OVERCHARGED."
        elif comparison["status"] == "UNDERCHARGED":
            reasoning += "Transaction was UNDERCHARGED."

        # Confidence reasoning
        confidence_reasoning = []
        if confidence >= 0.8:
            confidence_reasoning.append("High confidence: clear payment method and exact contract rule match")
        elif confidence >= 0.5:
            confidence_reasoning.append("Medium confidence: some ambiguity in payment method or contract rule")
        else:
            confidence_reasoning.append("Low confidence: significant uncertainty in payment method or contract matching")

        if rule_match["ambiguities"]:
            confidence_reasoning.append(f"Ambiguities: {'; '.join(rule_match['ambiguities'])}")

        return {
            "transaction_id": transaction.get("transaction_id"),
            "order_id": transaction.get("order_id"),
            "transaction_date": transaction.get("created_date_no_time"),
            "amount": transaction.get("amount_eur", transaction.get("amount")),
            "currency": transaction.get("currency"),
            "payment_method": payment_method,
            "card_brand": transaction.get("card_brand"),
            "country": transaction.get("country"),
            "actual_commission": actual_fee,
            "expected_commission": expected_fee,
            "discrepancy": comparison["difference_amount"],
            "discrepancy_percentage": comparison["difference_percentage"],
            "status": comparison["status"],
            "reasoning": reasoning,
            "assumptions": [a.get("assumption", str(a)) for a in assumptions],
            "confidence": round(confidence, 2),
            "confidence_reasoning": " ".join(confidence_reasoning),
            "contract_rule_applied": {
                "category": rule_match["best_match"]["category"],
                "rule_key": rule_match["best_match"]["rule_key"],
                "wl_rate": rule_match["best_match"]["rule"].get("wl_rate"),
                "fixed_fee": rule_match["best_match"]["rule"].get("fixed_fee")
            },
            "expected_breakdown": expected_breakdown["breakdown"]
        }

    def generate_error_report(self, transaction: Dict, error_message: str, confidence: float) -> Dict:
        """Generate report for transactions that couldn't be verified."""
        return {
            "transaction_id": transaction.get("transaction_id"),
            "status": "ERROR",
            "error_message": error_message,
            "confidence": confidence
        }

    def run(self, batch_size: int = 100, max_transactions: Optional[int] = None):
        """
        Run verification on all transactions.

        Args:
            batch_size: Number of transactions to process per batch
            max_transactions: Optional limit on total transactions to process
        """
        self.initialize()

        print(f"Starting transaction verification (batch_size={batch_size})...")

        batch_number = 0
        total_processed = 0
        total_discrepancies = 0

        while True:
            # Load batch
            print(f"Processing batch {batch_number + 1}...")
            batch = load_transaction_data(
                self.transaction_file,
                limit=batch_size,
                offset=batch_number * batch_size,
                filters={"status": "approved"}  # Only check approved transactions
            )

            if not batch["transactions"]:
                break

            # Process each transaction
            for transaction in batch["transactions"]:
                discrepancy = self.verify_transaction(transaction)
                if discrepancy:
                    self.discrepancies.append(discrepancy)
                    total_discrepancies += 1

                total_processed += 1

                # Check if we've hit the limit
                if max_transactions and total_processed >= max_transactions:
                    break

            # Check if we should continue
            if not batch["has_more"] or (max_transactions and total_processed >= max_transactions):
                break

            batch_number += 1

        print(f"\nVerification complete!")
        print(f"Total transactions processed: {total_processed}")
        print(f"Discrepancies found: {total_discrepancies}")
        print(f"Error rate: {(total_discrepancies/total_processed)*100:.2f}%")

        return self.discrepancies

    def export_results(self, output_file: str = "output/discrepancy_report.json"):
        """Export discrepancies to both JSON and human-readable text files."""
        import os
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        # Export JSON (structured data)
        with open(output_file, 'w') as f:
            json.dump({
                "summary": {
                    "total_discrepancies": len(self.discrepancies),
                    "discrepancies_by_status": self._count_by_status(),
                    "discrepancies_by_payment_method": self._count_by_payment_method(),
                    "total_discrepancy_amount": sum(d.get("discrepancy", 0) for d in self.discrepancies)
                },
                "discrepancies": self.discrepancies
            }, f, indent=2)

        print(f"✓ JSON report exported to {output_file}")

        # Export human-readable text report
        text_file = output_file.replace('.json', '.txt')
        from agent.tools.report_generator import generate_text_report
        generate_text_report(self.discrepancies, text_file)
        print(f"✓ Text report exported to {text_file}")

        print(f"\nReports generated:")
        print(f"  - JSON: {output_file}")
        print(f"  - Text: {text_file}")

    def _count_by_status(self) -> Dict:
        """Count discrepancies by status."""
        counts = {}
        for d in self.discrepancies:
            status = d.get("status", "UNKNOWN")
            counts[status] = counts.get(status, 0) + 1
        return counts

    def _count_by_payment_method(self) -> Dict:
        """Count discrepancies by payment method."""
        counts = {}
        for d in self.discrepancies:
            method = d.get("payment_method", "unknown")
            counts[method] = counts.get(method, 0) + 1
        return counts


# Usage example
if __name__ == "__main__":
    agent = TransactionFeeVerificationAgent(
        contract_file="data/parsed_contract.json",
        transaction_file="data/transaction_table.csv"
    )

    # Run verification
    agent.run(batch_size=100, max_transactions=1000)

    # Export results
    agent.export_results("output/discrepancy_report.json")
```

---

## Running the Agent

### 1. Install Dependencies
```bash
pip install pandas pydantic anthropic
```

### 2. Run Verification
```python
from agent.main import TransactionFeeVerificationAgent

agent = TransactionFeeVerificationAgent(
    contract_file="parsed_contract.json",
    transaction_file="transaction_table.csv"
)

# Verify all transactions
results = agent.run()

# Export report
agent.export_results("discrepancy_report.json")
```

### 3. Example Output
```json
{
  "summary": {
    "total_discrepancies": 45,
    "discrepancies_by_status": {
      "OVERCHARGED": 23,
      "UNDERCHARGED": 22
    },
    "total_discrepancy_amount": -15.67
  },
  "discrepancies": [
    {
      "transaction_id": "dd523aac-9bdf-429e-829e-7961316306bc",
      "amount": 510.28,
      "actual_commission": 5.0,
      "expected_commission": 5.1028,
      "discrepancy": -0.1028,
      "status": "UNDERCHARGED",
      "confidence": 0.85,
      "reasoning": "Expected calculation shows mismatch...",
      "assumptions": ["Field 'comission_eur' mapped to commission_total"]
    }
  ]
}
```

---

## Next Steps

1. Implement remaining tools (context, tiered fees)
2. Add unit tests
3. Integrate with Claude API for enhanced reasoning
4. Add interactive mode for ambiguous cases
5. Create visualization dashboard for results
