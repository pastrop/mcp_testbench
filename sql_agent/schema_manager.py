"""
Schema Manager Module

Handles loading, analyzing, and managing database schemas from JSON files.
Detects ambiguities and potential duplicates in column names.
"""

import json
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict
import re


@dataclass
class SchemaColumn:
    """Represents a single column in the schema."""
    name: str
    type: str
    short_description: str
    detailed_description: str


@dataclass
class SchemaAmbiguity:
    """Represents a detected ambiguity or potential duplicate."""
    columns: List[str]
    reason: str
    severity: str  # 'high', 'medium', 'low'


class SchemaManager:
    """Manages database schema loading and analysis."""

    def __init__(self, schema_path: str = "schema.json"):
        self.schema_path = schema_path
        self.columns: List[SchemaColumn] = []
        self.ambiguities: List[SchemaAmbiguity] = []
        self.clarifications: Dict[str, str] = {}

    def load_schema(self) -> bool:
        """Load schema from JSON file."""
        try:
            with open(self.schema_path, 'r') as f:
                schema_data = json.load(f)

            self.columns = [
                SchemaColumn(
                    name=col['name'],
                    type=col['type'],
                    short_description=col['short_description'],
                    detailed_description=col['detailed_description']
                )
                for col in schema_data
            ]
            return True
        except Exception as e:
            print(f"Error loading schema: {e}")
            return False

    def analyze_schema(self) -> List[SchemaAmbiguity]:
        """Analyze schema for ambiguities and potential duplicates."""
        self.ambiguities = []

        # Check for similar column names
        self._detect_similar_names()

        # Check for columns with similar descriptions
        self._detect_similar_descriptions()

        # Check for ambiguous naming patterns
        self._detect_ambiguous_patterns()

        return self.ambiguities

    def _detect_similar_names(self):
        """Detect columns with similar names."""
        # Group by base name (without suffixes like _eur, _id, etc.)
        name_groups = defaultdict(list)

        for col in self.columns:
            # Extract base name
            base_name = re.sub(r'_(eur|usd|id|fee|amt|date|no_time)$', '', col.name)
            name_groups[base_name].append(col.name)

        # Find groups with multiple columns
        for base_name, col_names in name_groups.items():
            if len(col_names) > 1:
                # Check if these are genuinely different (e.g., EUR vs original currency)
                has_currency_suffix = any('_eur' in name for name in col_names)

                if has_currency_suffix:
                    # This might be intentional (currency conversions)
                    severity = 'low'
                    reason = f"Multiple currency variants of '{base_name}' field"
                else:
                    # Potential duplicates
                    severity = 'high'
                    reason = f"Potential duplicate columns with similar names"

                self.ambiguities.append(SchemaAmbiguity(
                    columns=col_names,
                    reason=reason,
                    severity=severity
                ))

    def _detect_similar_descriptions(self):
        """Detect columns with very similar descriptions."""
        for i, col1 in enumerate(self.columns):
            for col2 in self.columns[i+1:]:
                # Compare short descriptions
                if self._similarity_ratio(
                    col1.short_description.lower(),
                    col2.short_description.lower()
                ) > 0.8:
                    self.ambiguities.append(SchemaAmbiguity(
                        columns=[col1.name, col2.name],
                        reason=f"Very similar descriptions: '{col1.short_description}' vs '{col2.short_description}'",
                        severity='medium'
                    ))

    def _detect_ambiguous_patterns(self):
        """Detect ambiguous naming patterns."""
        # Check for columns that might be confusing
        patterns = {
            'status': ['status', 'transaction_status'],
            'type': ['type', 'transaction_type'],
            'error': ['error_code', 'error_message', 'external_error_code', 'external_error_message', 'merchant_error_code', 'merchant_error_message'],
            'date': ['created_date', 'created_date_no_time', 'fx_date'],
            'commission': ['comission_eur', 'transaction_comission', 'agent_eur', 'icc_eur'],
            'amount': ['amount', 'amount_eur', 'total_amt'],
            'merchant': ['merchant', 'merchant_name', 'merchant_id', 'merchant_group'],
            'processor': ['processor_name', 'processor_id', 'proc_group'],
        }

        for pattern_name, pattern_cols in patterns.items():
            matching_cols = [col.name for col in self.columns if col.name in pattern_cols]
            if len(matching_cols) > 1:
                self.ambiguities.append(SchemaAmbiguity(
                    columns=matching_cols,
                    reason=f"Multiple {pattern_name}-related columns that may be confusing",
                    severity='medium'
                ))

    def _similarity_ratio(self, str1: str, str2: str) -> float:
        """Calculate similarity ratio between two strings (simple implementation)."""
        if str1 == str2:
            return 1.0

        # Count common words
        words1 = set(str1.split())
        words2 = set(str2.split())

        if not words1 or not words2:
            return 0.0

        common = words1.intersection(words2)
        return len(common) / max(len(words1), len(words2))

    def add_clarification(self, column_name: str, clarification: str):
        """Add a user clarification for a column."""
        self.clarifications[column_name] = clarification

    def get_column(self, name: str) -> Optional[SchemaColumn]:
        """Get a column by name."""
        for col in self.columns:
            if col.name == name:
                return col
        return None

    def get_enriched_schema_description(self) -> str:
        """Get a comprehensive schema description for the LLM, including clarifications."""
        lines = ["Database Schema Description:\n"]
        lines.append("=" * 80)
        lines.append(f"\nTable: transactions (single table, no joins required)")
        lines.append(f"Total Columns: {len(self.columns)}\n")

        for col in self.columns:
            lines.append(f"\nColumn: {col.name}")
            lines.append(f"  Type: {col.type}")
            lines.append(f"  Short Description: {col.short_description}")
            lines.append(f"  Detailed Description: {col.detailed_description}")

            # Add clarification if available
            if col.name in self.clarifications:
                lines.append(f"  USER CLARIFICATION: {self.clarifications[col.name]}")

        lines.append("\n" + "=" * 80)

        return "\n".join(lines)

    def save_schema_with_clarifications(self, output_path: str = "schema_clarified.json"):
        """Save schema with clarifications to a new JSON file."""
        schema_data = []
        for col in self.columns:
            col_dict = {
                'name': col.name,
                'type': col.type,
                'short_description': col.short_description,
                'detailed_description': col.detailed_description
            }
            if col.name in self.clarifications:
                col_dict['user_clarification'] = self.clarifications[col.name]
            schema_data.append(col_dict)

        with open(output_path, 'w') as f:
            json.dump(schema_data, f, indent=2)

    def get_columns_by_type(self, type_filter: str) -> List[SchemaColumn]:
        """Get all columns of a specific type."""
        return [col for col in self.columns if col.type == type_filter]

    def search_columns(self, search_term: str) -> List[SchemaColumn]:
        """Search for columns by name or description."""
        search_term = search_term.lower()
        results = []

        for col in self.columns:
            if (search_term in col.name.lower() or
                search_term in col.short_description.lower() or
                search_term in col.detailed_description.lower()):
                results.append(col)

        return results
