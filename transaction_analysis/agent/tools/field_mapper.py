"""Field mapping and payment method inference tools."""

from typing import Dict, List, Optional, Tuple


# Static field mappings for known variations
FIELD_MAPPINGS = {
    "comission_eur": "commission_total",
    "commision_eur": "commission_total",
    "transaction_comission": "commission_total",
    "mdr_eur": "merchant_discount_rate",
    "base_eur": "base_fee",
    "fixed_eur": "fixed_fee",
    "min_eur": "minimum_fee",
    "amount_eur": "transaction_amount",
    "traffic_type_group": "payment_method",
    "gate_name": "gateway_name",
    "card_brand": "card_type",
    "transaction_type": "type",
    "transaction_status": "status",
}

# Payment method indicators for inference
PAYMENT_METHOD_INDICATORS = {
    "apple_pay": ["apple_pay", "applepay", "apple pay"],
    "google_pay": ["google_pay", "googlepay", "google pay"],
    "sepa": ["sepa"],
    "card": ["card", "wl", "visa", "mastercard"],
    "blik": ["blik"],
    "sofort": ["sofort"],
    "open_banking": ["open_banking", "openbanking"],
}


def map_transaction_fields(
    transaction: Dict,
    available_columns: List[str]
) -> Dict:
    """
    Map transaction CSV fields to standardized names.

    Args:
        transaction: Raw transaction dictionary
        available_columns: List of available column names

    Returns:
        Dictionary with:
        - mapped_fields: Transaction with standardized field names
        - unmapped_fields: List of fields that couldn't be mapped
        - assumptions: List of mapping decisions made
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
            # Keep original field name
            mapped_fields[key] = value

            # Track unmapped non-standard fields
            if key not in ["transaction_id", "order_id", "created_date", "country", "currency"]:
                if not any(std_field in key.lower() for std_field in ["id", "date", "time", "name"]):
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
        transaction: Mapped transaction dictionary

    Returns:
        Dictionary with:
        - payment_method: Inferred payment method
        - confidence: Confidence score (0.0-1.0)
        - evidence: List of evidence supporting the inference
    """
    evidence = []
    confidence = 0.0
    payment_method = "unknown"

    # Priority 1: Check explicit payment method field
    if "payment_method" in transaction and transaction["payment_method"]:
        traffic_type = str(transaction["payment_method"]).lower()
        for method, indicators in PAYMENT_METHOD_INDICATORS.items():
            if any(ind in traffic_type for ind in indicators):
                payment_method = method
                confidence = 0.95
                evidence.append(f"payment_method field='{traffic_type}' directly indicates {method}")
                return {"payment_method": payment_method, "confidence": confidence, "evidence": evidence}

    # Check traffic_type_group
    if "traffic_type_group" in transaction and transaction["traffic_type_group"]:
        traffic_type = str(transaction["traffic_type_group"]).lower()
        for method, indicators in PAYMENT_METHOD_INDICATORS.items():
            if any(ind in traffic_type for ind in indicators):
                payment_method = method
                confidence = 0.95
                evidence.append(f"traffic_type_group='{traffic_type}' indicates {method}")
                return {"payment_method": payment_method, "confidence": confidence, "evidence": evidence}

    # Priority 2: Check gateway name field
    gateway_fields = ["gateway_name", "gate_name", "gate_descriptor"]
    for field in gateway_fields:
        if field in transaction and transaction[field]:
            gate_name = str(transaction[field]).lower()
            for method, indicators in PAYMENT_METHOD_INDICATORS.items():
                if any(ind in gate_name for ind in indicators):
                    payment_method = method
                    confidence = 0.85
                    evidence.append(f"{field}='{gate_name}' suggests {method}")
                    return {"payment_method": payment_method, "confidence": confidence, "evidence": evidence}

    # Priority 3: Check card_brand field for card transactions
    card_fields = ["card_type", "card_brand"]
    for field in card_fields:
        if field in transaction and transaction[field]:
            card_brand = str(transaction[field]).upper()
            if card_brand in ["VISA", "MASTERCARD", "AMEX", "DISCOVER"]:
                payment_method = "card"
                confidence = 0.90
                evidence.append(f"{field}='{card_brand}' indicates card transaction")
                return {"payment_method": payment_method, "confidence": confidence, "evidence": evidence}

    # Priority 4: Check transaction type for payouts
    if "type" in transaction:
        tx_type = str(transaction.get("type", "")).lower()
        if "payout" in tx_type or "withdrawal" in tx_type:
            # Could be SEPA payout
            if "source" in transaction and "sepa" in str(transaction["source"]).lower():
                payment_method = "sepa"
                confidence = 0.75
                evidence.append(f"type='{tx_type}' with source containing 'sepa' suggests SEPA payout")
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


def extract_transaction_characteristics(transaction: Dict) -> Dict:
    """
    Extract key characteristics from a transaction for contract matching.

    Args:
        transaction: Mapped transaction dictionary

    Returns:
        Dictionary with extracted characteristics
    """
    # Map fields first
    mapped = map_transaction_fields(transaction, list(transaction.keys()))
    tx = mapped["mapped_fields"]

    # Infer payment method
    payment_info = infer_payment_method(tx)

    # Extract characteristics
    characteristics = {
        "amount": float(tx.get("transaction_amount", tx.get("amount_eur", tx.get("amount", 0)))),
        "currency": tx.get("currency", "EUR"),
        "payment_method": payment_info["payment_method"],
        "payment_method_confidence": payment_info["confidence"],
        "region": tx.get("country"),
        "card_brand": tx.get("card_type", tx.get("card_brand")),
        "transaction_type": tx.get("type", "payment"),
        "status": tx.get("status", "unknown"),
        "actual_commission": float(tx.get("commission_total", tx.get("comission_eur", 0))),
        "transaction_id": tx.get("transaction_id"),
        "mapping_assumptions": mapped["assumptions"],
        "payment_method_evidence": payment_info["evidence"]
    }

    return characteristics
