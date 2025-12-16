# Semantic Field Mapping with Claude

## Problem

Transaction CSV and contract JSON may use different terminology for the same concept:
- Contract: "fees" vs Transaction table: "commissions"
- Contract: "transaction_fee" vs Table: "processing_charge"
- Contract: "fixed_fee" vs Table: "flat_rate"

Static dictionaries cannot handle all variations.

## Solution: Claude-Powered Semantic Mapping

Use Claude to understand semantic relationships between field names and infer correct mappings.

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│         Transaction CSV Columns                  │
│  ["comission_eur", "mdr_eur", "amount_eur", ...] │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│       Claude Semantic Mapper                     │
│                                                  │
│  • Analyzes field names                         │
│  • Understands semantic relationships           │
│  • Examines sample data values                  │
│  • Considers data types and ranges              │
│  • Assigns confidence scores                    │
└────────────────────┬────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────┐
│         Mapped Fields + Confidence              │
│  {                                               │
│    "comission_eur": {                           │
│      "maps_to": "total_commission",             │
│      "confidence": 0.95,                        │
│      "reasoning": "Likely total commission..."  │
│    }                                            │
│  }                                              │
└─────────────────────────────────────────────────┘
```

---

## Implementation

### Enhanced Field Mapper with Claude

```python
import anthropic
from typing import Dict, List, Optional
import json

class SemanticFieldMapper:
    """Use Claude to map fields with semantic understanding."""

    def __init__(self, anthropic_api_key: str):
        self.client = anthropic.Anthropic(api_key=anthropic_api_key)

    def map_fields_semantically(
        self,
        csv_columns: List[str],
        sample_data: Dict[str, any],
        contract_terminology: List[str],
        context: Optional[str] = None
    ) -> Dict[str, Dict]:
        """
        Use Claude to map CSV columns to standardized field names.

        Args:
            csv_columns: List of column names from CSV
            sample_data: Sample row from CSV to help understand data
            contract_terminology: Terms used in contract (e.g., ["fee", "rate", "commission"])
            context: Additional context about the data

        Returns:
            {
                "column_name": {
                    "maps_to": "standardized_name",
                    "confidence": 0.0-1.0,
                    "reasoning": "explanation",
                    "alternative_mappings": [...]
                }
            }
        """

        prompt = f"""You are a data mapping expert. Analyze these CSV columns and map them to standardized field names.

## CSV Columns
{json.dumps(csv_columns, indent=2)}

## Sample Data (first row)
{json.dumps(sample_data, indent=2)}

## Contract Terminology
The contract uses these terms: {', '.join(contract_terminology)}

## Context
{context or "Payment transaction data with fees, commissions, and amounts."}

## Your Task

For each CSV column, determine:
1. What it likely represents
2. The standardized name it should map to
3. Your confidence (0.0-1.0) in this mapping
4. Your reasoning
5. Alternative possible mappings

## Standardized Field Names to Use

**Fee/Commission Related:**
- `commission_total` - Total commission/fee charged
- `commission_percentage` - Percentage-based commission component
- `commission_fixed` - Fixed commission component
- `merchant_discount_rate` - MDR (percentage rate)
- `processing_fee` - Generic processing fee
- `transaction_fee` - Per-transaction fee

**Amount Related:**
- `transaction_amount` - Total transaction amount
- `net_amount` - Amount after fees
- `gross_amount` - Amount before fees

**Metadata:**
- `transaction_id` - Unique identifier
- `payment_method` - How payment was made
- `currency` - Transaction currency
- `status` - Transaction status

## Special Considerations

1. **Semantic Similarity**: "fees" and "commissions" are synonyms in this context
2. **Suffixes**: "_eur", "_usd" indicate currency denomination
3. **Abbreviations**: "mdr" = merchant discount rate, "chb" = chargeback
4. **Typos**: "comission" = "commission"
5. **Compound fields**: Some fields may combine multiple concepts

## Output Format

Return a JSON object with this structure:

```json
{{
  "column_name": {{
    "maps_to": "standardized_field_name",
    "confidence": 0.95,
    "reasoning": "Clear indication that this is...",
    "data_type": "float",
    "alternative_mappings": [
      {{"field": "alternative_name", "confidence": 0.3, "reason": "Could also be..."}}
    ],
    "notes": "Any additional observations"
  }}
}}
```

Be thoughtful about ambiguous cases. If unsure, provide lower confidence and list alternatives.
"""

        response = self.client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )

        # Extract JSON from response
        response_text = response.content[0].text

        # Parse JSON (handle markdown code blocks)
        import re
        json_match = re.search(r'```json\n(.*?)\n```', response_text, re.DOTALL)
        if json_match:
            mapping = json.loads(json_match.group(1))
        else:
            # Try to find raw JSON
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                mapping = json.loads(json_match.group(0))
            else:
                raise ValueError("Could not extract JSON from Claude's response")

        return mapping

    def get_field_value(
        self,
        transaction: Dict,
        standardized_field: str,
        field_mapping: Dict
    ) -> tuple[any, float, str]:
        """
        Get value of a standardized field from transaction using mapping.

        Returns:
            (value, confidence, source_field)
        """
        # Find which CSV column maps to this standardized field
        for csv_column, mapping_info in field_mapping.items():
            if mapping_info["maps_to"] == standardized_field:
                if csv_column in transaction:
                    return (
                        transaction[csv_column],
                        mapping_info["confidence"],
                        csv_column
                    )

        return (None, 0.0, None)


# Usage Example
def map_transaction_fields_with_claude(
    transaction: Dict,
    csv_columns: List[str],
    contract_terms: List[str]
) -> Dict:
    """
    Map transaction fields using Claude's semantic understanding.
    """
    mapper = SemanticFieldMapper(api_key="your-api-key")

    # Get semantic mapping
    field_mapping = mapper.map_fields_semantically(
        csv_columns=csv_columns,
        sample_data=transaction,
        contract_terminology=contract_terms,
        context="Payment processing transactions with various fee types"
    )

    # Apply mapping to transaction
    mapped_transaction = {}
    assumptions = []

    for csv_field, value in transaction.items():
        if csv_field in field_mapping:
            mapping_info = field_mapping[csv_field]
            standardized_field = mapping_info["maps_to"]

            mapped_transaction[standardized_field] = value

            # Document assumption if confidence < 1.0
            if mapping_info["confidence"] < 1.0:
                assumptions.append({
                    "original_field": csv_field,
                    "mapped_to": standardized_field,
                    "confidence": mapping_info["confidence"],
                    "reasoning": mapping_info["reasoning"]
                })

        else:
            # Keep unmapped fields as-is
            mapped_transaction[csv_field] = value

    return {
        "mapped_transaction": mapped_transaction,
        "field_mapping": field_mapping,
        "assumptions": assumptions
    }
```

---

## Example: Handling "fees" vs "commissions"

### Scenario

**Contract terminology**: Uses "fees" throughout
**Transaction CSV**: Has column "comission_eur"

### Claude's Analysis

```json
{
  "comission_eur": {
    "maps_to": "commission_total",
    "confidence": 0.92,
    "reasoning": "Despite spelling variation ('comission' vs 'commission'), this clearly represents the total commission/fee charged. The '_eur' suffix indicates currency denomination. In payment processing, 'commission' and 'fee' are synonymous terms.",
    "data_type": "float",
    "alternative_mappings": [],
    "notes": "Spelling variation likely a typo. Semantically equivalent to 'fee' used in contract."
  },
  "mdr_eur": {
    "maps_to": "merchant_discount_rate",
    "confidence": 0.98,
    "reasoning": "MDR is standard industry abbreviation for Merchant Discount Rate - the percentage-based component of transaction fees. This is the variable fee portion.",
    "data_type": "float",
    "alternative_mappings": [
      {
        "field": "commission_percentage",
        "confidence": 0.85,
        "reason": "Could represent the percentage component of total commission"
      }
    ],
    "notes": "MDR is industry-standard terminology"
  },
  "base_eur": {
    "maps_to": "commission_total",
    "confidence": 0.65,
    "reasoning": "Labeled as 'base' which is ambiguous. Could be base fee, base amount, or base commission. Sample data shows it equals mdr_eur value in some cases, suggesting it might be the total calculated fee before adjustments.",
    "data_type": "float",
    "alternative_mappings": [
      {
        "field": "commission_base_calculated",
        "confidence": 0.70,
        "reason": "More likely represents calculated fee before adjustments"
      },
      {
        "field": "transaction_amount_base",
        "confidence": 0.25,
        "reason": "Could be base transaction amount, but less likely given other amount fields"
      }
    ],
    "notes": "AMBIGUOUS - recommend reviewing actual data to confirm"
  }
}
```

---

## Advanced: Iterative Refinement

Claude can refine mappings based on validation feedback:

```python
class AdaptiveFieldMapper(SemanticFieldMapper):
    """Field mapper that learns from validation feedback."""

    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.mapping_history = []

    def refine_mapping(
        self,
        current_mapping: Dict,
        validation_results: List[Dict],
        discrepancies: List[Dict]
    ) -> Dict:
        """
        Refine field mapping based on validation results.

        Args:
            current_mapping: Current field mapping
            validation_results: Results from fee validation
            discrepancies: Detected fee discrepancies

        Returns:
            Refined mapping with updated confidence scores
        """

        prompt = f"""You previously mapped these fields:

{json.dumps(current_mapping, indent=2)}

After running validation, we found these issues:

## Validation Results
{json.dumps(validation_results, indent=2)}

## Discrepancies Found
{json.dumps(discrepancies, indent=2)}

## Analysis Request

1. Review if field mappings might be incorrect
2. Identify patterns in discrepancies that suggest mapping errors
3. Propose revised mappings if needed
4. Adjust confidence scores based on validation outcomes

For example:
- If many transactions show 2x expected fees, maybe we're double-counting by mapping two fields to the same concept
- If fees are consistently 0 when they shouldn't be, maybe we mapped the wrong field
- If discrepancies correlate with specific payment methods, mapping might be method-specific

Provide refined mapping with reasoning for any changes.
"""

        response = self.client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )

        # Parse refined mapping
        # ... [same JSON extraction logic]

        return refined_mapping
```

---

## Hybrid Approach: Static + Semantic

Best practice combines both:

```python
class HybridFieldMapper:
    """Combine static mappings with Claude semantic mapping."""

    # Known variations (fast, no API cost)
    STATIC_MAPPINGS = {
        "comission_eur": "commission_total",
        "commision_eur": "commission_total",
        "transaction_comission": "commission_total",
        "mdr_eur": "merchant_discount_rate",
        "amount_eur": "transaction_amount",
    }

    # Semantic equivalents
    SEMANTIC_GROUPS = {
        "commission": ["fee", "charge", "commission", "cost"],
        "amount": ["amount", "sum", "total", "value"],
        "rate": ["rate", "percentage", "percent"],
    }

    def __init__(self, api_key: str):
        self.semantic_mapper = SemanticFieldMapper(api_key)
        self.semantic_cache = {}

    def map_fields(
        self,
        csv_columns: List[str],
        sample_data: Dict,
        use_semantic: bool = True
    ) -> Dict:
        """
        Map fields using static mappings first, then semantic if needed.
        """
        mapping = {}

        # Step 1: Apply static mappings (instant)
        for column in csv_columns:
            if column in self.STATIC_MAPPINGS:
                mapping[column] = {
                    "maps_to": self.STATIC_MAPPINGS[column],
                    "confidence": 1.0,
                    "reasoning": "Exact match in static mapping dictionary",
                    "method": "static"
                }

        # Step 2: Use semantic groups for common terms
        for column in csv_columns:
            if column not in mapping:
                mapped = self._try_semantic_groups(column)
                if mapped:
                    mapping[column] = mapped

        # Step 3: Use Claude for remaining unmapped fields
        if use_semantic:
            unmapped = [c for c in csv_columns if c not in mapping]
            if unmapped:
                # Check cache first
                cache_key = tuple(sorted(unmapped))
                if cache_key in self.semantic_cache:
                    claude_mapping = self.semantic_cache[cache_key]
                else:
                    # Call Claude
                    claude_mapping = self.semantic_mapper.map_fields_semantically(
                        csv_columns=unmapped,
                        sample_data=sample_data,
                        contract_terminology=["fee", "commission", "rate", "amount"]
                    )
                    self.semantic_cache[cache_key] = claude_mapping

                # Merge Claude mappings
                for col, info in claude_mapping.items():
                    info["method"] = "semantic"
                    mapping[col] = info

        return mapping

    def _try_semantic_groups(self, column: str) -> Optional[Dict]:
        """Try to map using semantic group matching."""
        column_lower = column.lower()

        # Check if column contains any semantic group terms
        for standard_term, equivalents in self.SEMANTIC_GROUPS.items():
            for equiv in equivalents:
                if equiv in column_lower:
                    return {
                        "maps_to": f"{standard_term}_total",
                        "confidence": 0.75,
                        "reasoning": f"Column name contains '{equiv}' which is semantically related to '{standard_term}'",
                        "method": "semantic_group"
                    }

        return None
```

---

## Performance Optimization

### 1. Cache Semantic Mappings

```python
# Map once per CSV schema, reuse for all transactions
schema_hash = hash(tuple(sorted(csv_columns)))
if schema_hash in mapping_cache:
    field_mapping = mapping_cache[schema_hash]
else:
    field_mapping = mapper.map_fields_semantically(...)
    mapping_cache[schema_hash] = field_mapping
```

### 2. Batch Analysis

```python
# Instead of mapping each transaction individually,
# analyze the schema once and apply to all transactions
field_mapping = map_schema_once(csv_columns, sample_transactions[0])

for transaction in all_transactions:
    mapped_tx = apply_mapping(transaction, field_mapping)
```

### 3. Confidence Thresholds

```python
# Only use Claude for truly ambiguous cases
if simple_heuristic_confidence(column_name) < 0.7:
    # Use Claude for semantic mapping
    mapping = semantic_mapper.map_fields(...)
else:
    # Use fast static mapping
    mapping = static_mapper.map_fields(...)
```

---

## Validation

After mapping, validate by checking:

```python
def validate_mapping(
    mapping: Dict,
    sample_transactions: List[Dict],
    expected_fields: List[str]
) -> Dict:
    """
    Validate that mapping produces expected fields.
    """
    issues = []

    # Check: Are all expected fields mapped?
    mapped_fields = set(m["maps_to"] for m in mapping.values())
    missing = set(expected_fields) - mapped_fields
    if missing:
        issues.append(f"Missing expected fields: {missing}")

    # Check: Do mapped values make sense?
    for tx in sample_transactions[:10]:
        mapped_tx = apply_mapping(tx, mapping)

        # Sanity checks
        if "commission_total" in mapped_tx:
            if not isinstance(mapped_tx["commission_total"], (int, float)):
                issues.append("commission_total is not numeric")

        if "transaction_amount" in mapped_tx:
            if mapped_tx["transaction_amount"] < 0:
                issues.append("Negative transaction amount detected")

    return {
        "is_valid": len(issues) == 0,
        "issues": issues
    }
```

---

## Summary

### Static Mapping (Current)
- ✅ Fast
- ✅ No API cost
- ❌ Only handles pre-defined variations
- ❌ Can't handle semantic differences

### Claude Semantic Mapping (Enhanced)
- ✅ Handles semantic variations ("fees" vs "commissions")
- ✅ Understands context and data types
- ✅ Provides confidence scores
- ✅ Documents reasoning
- ✅ Can learn from feedback
- ⚠️ API cost (mitigated by caching)
- ⚠️ Slower (but only run once per schema)

### Hybrid Approach (Recommended)
- ✅ Best of both worlds
- ✅ Fast for common cases
- ✅ Smart for ambiguous cases
- ✅ Cost-effective

---

## Real Example

```python
# CSV has: "processing_fees_eur", "merchant_fee_eur"
# Contract uses: "transaction_commission", "mdr"

mapper = HybridFieldMapper(api_key="...")
mapping = mapper.map_fields(
    csv_columns=["processing_fees_eur", "merchant_fee_eur", "amount_eur"],
    sample_data=sample_transaction
)

# Claude determines:
# "processing_fees_eur" → "commission_total" (confidence: 0.88)
# "merchant_fee_eur" → "merchant_discount_rate" (confidence: 0.75)
# "amount_eur" → "transaction_amount" (confidence: 1.0)
```
