"""Contract rule matching tools."""

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

    Args:
        contract_data: Loaded contract data
        currency: Transaction currency (EUR, USD, etc.)
        payment_method: Payment method (card, sepa, apple_pay, etc.)
        region: Transaction region/country (optional)
        card_brand: Card brand if applicable (optional)
        transaction_type: Transaction type (payment, payout, refund, chargeback)
        amount: Transaction amount (optional, for tiered fees)
        monthly_volume: Monthly cumulative volume (optional, for tiered fees)

    Returns:
        Dictionary with:
        - rules: List of matching rules
        - best_match: Best matching rule
        - ambiguities: List of ambiguities encountered
        - confidence: Confidence score (0.0-1.0)
    """
    matching_rules = []
    ambiguities = []

    # Normalize inputs
    currency = currency.upper() if currency else "EUR"
    payment_method = payment_method.lower() if payment_method else "unknown"

    # Search in card fees
    if payment_method in ["card", "wl"] or card_brand:
        card_fees = contract_data.get("card_fees", {})

        for rule_key, rule in card_fees.items():
            # Match currency
            if rule.get("currency") != currency:
                continue

            # Match region if provided
            if region:
                rule_region = rule.get("region", "WW")
                region_match = False

                # Exact match
                if region.upper() == rule_region:
                    region_match = True
                # Worldwide matches everything
                elif rule_region == "WW":
                    region_match = True
                # EEA countries
                elif rule_region == "EEA" and region.upper() in ["DE", "PL", "FR", "IT", "ES", "NL", "BE", "AT", "IE", "PT", "FI", "SE", "DK", "NO", "IS", "LI"]:
                    region_match = True

                if not region_match:
                    continue

            matching_rules.append({
                "category": "card_fees",
                "rule_key": rule_key,
                "rule": rule,
                "match_score": _calculate_match_score(rule, currency, region, card_brand)
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
                            "match_score": _calculate_match_score(rule, currency, region, None)
                        })

    # Search in outgoing fees
    if transaction_type in ["payout", "withdrawal"]:
        outgoing_fees = contract_data.get("outgoing_fees", {})

        if payment_method == "sepa" or "sepa" in str(region).lower() if region else False:
            sepa_fees = outgoing_fees.get("sepa", {})
            for rule_key, rule in sepa_fees.items():
                if isinstance(rule, dict) and rule.get("currency") == currency:
                    matching_rules.append({
                        "category": "outgoing_fees.sepa",
                        "rule_key": rule_key,
                        "rule": rule,
                        "match_score": 0.9
                    })

        elif payment_method == "card":
            card_payouts = outgoing_fees.get("cards", {})
            for rule_key, rule in card_payouts.items():
                if isinstance(rule, dict) and rule.get("currency") == currency:
                    matching_rules.append({
                        "category": "outgoing_fees.cards",
                        "rule_key": rule_key,
                        "rule": rule,
                        "match_score": _calculate_match_score(rule, currency, region, card_brand)
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

    # Check for ambiguity (multiple high-scoring matches)
    if len(matching_rules) > 1:
        if matching_rules[1]["match_score"] >= matching_rules[0]["match_score"] - 0.1:
            ambiguities.append(
                f"Multiple rules match with similar scores: {[r['rule_key'] for r in matching_rules[:3]]}"
            )

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


def _calculate_match_score(
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
        elif region in ["DE", "FR", "PL", "IT", "ES"] and rule_region == "EEA":
            score += 0.15  # EEA match

    # Card brand match (if applicable)
    if card_brand and "card_brand" in str(rule):
        # Check if rule key contains card brand info
        rule_str = str(rule).lower()
        if card_brand.lower() in rule_str:
            score += 0.1

    return min(score, 1.0)
