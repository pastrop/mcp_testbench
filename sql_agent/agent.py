"""
Text-to-SQL Agent

Main orchestration module that coordinates schema analysis,
user clarifications, and query translation.
"""

from typing import Optional, Dict, Any, List
from schema_manager import SchemaManager, SchemaAmbiguity
from query_translator import QueryTranslator
import json


class TextToSQLAgent:
    """
    Main agent that orchestrates the text-to-SQL translation process.

    Workflow:
    1. Load and analyze schema
    2. Identify ambiguities and request clarifications (human-in-the-loop)
    3. Translate natural language to SQL
    """

    def __init__(
        self,
        schema_path: str = "schema.json",
        table_name: str = "transactions",
        auto_clarify: bool = False
    ):
        """
        Initialize the agent.

        Args:
            schema_path: Path to the schema JSON file
            table_name: Name of the table to query
            auto_clarify: If True, skip human clarification (for testing)
        """
        self.schema_manager = SchemaManager(schema_path)
        self._query_translator = None  # Lazy initialization
        self.table_name = table_name
        self.auto_clarify = auto_clarify
        self.initialized = False

    @property
    def query_translator(self):
        """Lazy initialization of query translator (requires API key)."""
        if self._query_translator is None:
            self._query_translator = QueryTranslator()
        return self._query_translator

    def initialize(self) -> Dict[str, Any]:
        """
        Initialize the agent by loading and analyzing the schema.

        Returns:
            Dictionary containing initialization results and any ambiguities found
        """
        # Load schema
        if not self.schema_manager.load_schema():
            return {
                "success": False,
                "error": "Failed to load schema",
                "ambiguities": []
            }

        # Analyze for ambiguities
        ambiguities = self.schema_manager.analyze_schema()

        # Filter ambiguities by severity
        high_priority = [a for a in ambiguities if a.severity == 'high']
        medium_priority = [a for a in ambiguities if a.severity == 'medium']

        self.initialized = True

        return {
            "success": True,
            "columns_loaded": len(self.schema_manager.columns),
            "ambiguities": {
                "high": high_priority,
                "medium": medium_priority,
                "total": len(ambiguities)
            }
        }

    def get_ambiguities_for_review(self) -> List[Dict[str, Any]]:
        """
        Get ambiguities formatted for human review.

        Returns:
            List of ambiguities with details for user review
        """
        if not self.initialized:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        ambiguities_list = []

        for idx, ambiguity in enumerate(self.schema_manager.ambiguities):
            # Only present high and medium severity
            if ambiguity.severity in ['high', 'medium']:
                amb_dict = {
                    "id": idx,
                    "severity": ambiguity.severity,
                    "reason": ambiguity.reason,
                    "columns": []
                }

                # Get full details for each column
                for col_name in ambiguity.columns:
                    col = self.schema_manager.get_column(col_name)
                    if col:
                        amb_dict["columns"].append({
                            "name": col.name,
                            "type": col.type,
                            "short_description": col.short_description,
                            "detailed_description": col.detailed_description
                        })

                ambiguities_list.append(amb_dict)

        return ambiguities_list

    def add_clarification(self, column_name: str, clarification: str):
        """
        Add a user clarification for a specific column.

        Args:
            column_name: Name of the column to clarify
            clarification: User's clarification text
        """
        if not self.initialized:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        self.schema_manager.add_clarification(column_name, clarification)

    def translate_query(
        self,
        natural_language_query: str,
        return_details: bool = True
    ) -> Dict[str, Any]:
        """
        Translate a natural language query to SQL.

        Args:
            natural_language_query: The user's question
            return_details: If True, return full details including explanation

        Returns:
            Dictionary containing SQL query and metadata
        """
        if not self.initialized:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        # Get enriched schema description
        schema_description = self.schema_manager.get_enriched_schema_description()

        # Translate to SQL
        result = self.query_translator.translate(
            natural_language_query=natural_language_query,
            schema_description=schema_description,
            table_name=self.table_name
        )

        # Validate the query
        if result.get("sql") and not result.get("error"):
            validation = self.query_translator.validate_query(result["sql"])
            result["validation"] = validation

        if not return_details:
            # Return simplified response
            return {
                "sql": result.get("sql"),
                "confidence": result.get("confidence"),
                "valid": result.get("validation", {}).get("valid", False)
            }

        return result

    def process_query_with_feedback(
        self,
        natural_language_query: str
    ) -> Dict[str, Any]:
        """
        Process a query and return results formatted for user feedback.

        Args:
            natural_language_query: The user's question

        Returns:
            Formatted results with SQL, explanation, and any warnings
        """
        result = self.translate_query(natural_language_query)

        response = {
            "query": natural_language_query,
            "success": not result.get("error", False),
        }

        if result.get("error"):
            response["error"] = result.get("explanation")
            return response

        response.update({
            "sql": result["sql"],
            "explanation": result.get("explanation", ""),
            "confidence": result.get("confidence", "medium"),
            "warnings": result.get("warnings", []),
            "validation": result.get("validation", {})
        })

        return response

    def save_clarifications(self, output_path: str = "schema_clarified.json"):
        """Save the schema with user clarifications."""
        if not self.initialized:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        self.schema_manager.save_schema_with_clarifications(output_path)

    def get_schema_summary(self) -> Dict[str, Any]:
        """Get a summary of the loaded schema."""
        if not self.initialized:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        return {
            "table_name": self.table_name,
            "total_columns": len(self.schema_manager.columns),
            "column_types": {
                "STRING": len(self.schema_manager.get_columns_by_type("STRING")),
                "FLOAT": len(self.schema_manager.get_columns_by_type("FLOAT")),
                "INTEGER": len(self.schema_manager.get_columns_by_type("INTEGER")),
                "DATE": len(self.schema_manager.get_columns_by_type("DATE")),
                "TIMESTAMP": len(self.schema_manager.get_columns_by_type("TIMESTAMP"))
            },
            "clarifications_added": len(self.schema_manager.clarifications)
        }

    def interactive_clarification_session(self):
        """
        Run an interactive session to gather clarifications for ambiguities.
        This is meant for CLI usage.
        """
        if not self.initialized:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        ambiguities = self.get_ambiguities_for_review()

        if not ambiguities:
            print("\n✓ No significant ambiguities detected in the schema.")
            return

        print(f"\n⚠️  Found {len(ambiguities)} potential ambiguities in the schema.")
        print("Please review and provide clarifications:\n")

        for amb in ambiguities:
            print(f"\n{'='*80}")
            print(f"Ambiguity {amb['id'] + 1} [{amb['severity'].upper()}]:")
            print(f"Reason: {amb['reason']}\n")

            for col in amb['columns']:
                print(f"  Column: {col['name']} ({col['type']})")
                print(f"    Short: {col['short_description']}")
                print(f"    Detail: {col['detailed_description']}")
                print()

            # Ask for clarification
            print("Would you like to add clarifications for any of these columns?")
            print("Format: column_name: your clarification")
            print("Or press Enter to skip:\n")

            user_input = input("> ").strip()

            if user_input:
                # Parse input
                if ':' in user_input:
                    col_name, clarification = user_input.split(':', 1)
                    col_name = col_name.strip()
                    clarification = clarification.strip()

                    if self.schema_manager.get_column(col_name):
                        self.add_clarification(col_name, clarification)
                        print(f"✓ Clarification added for '{col_name}'")
                    else:
                        print(f"⚠️  Column '{col_name}' not found")

        print(f"\n{'='*80}")
        print(f"✓ Clarification session complete. {len(self.schema_manager.clarifications)} clarifications added.")


def main():
    """Example usage of the agent."""
    print("Text-to-SQL Agent")
    print("=" * 80)

    # Initialize agent
    agent = TextToSQLAgent(schema_path="schema.json", table_name="transactions")

    print("\n1. Initializing and analyzing schema...")
    init_result = agent.initialize()

    if not init_result["success"]:
        print(f"Error: {init_result['error']}")
        return

    print(f"✓ Loaded {init_result['columns_loaded']} columns")
    print(f"✓ Found {init_result['ambiguities']['total']} potential ambiguities")
    print(f"  - High priority: {len(init_result['ambiguities']['high'])}")
    print(f"  - Medium priority: {len(init_result['ambiguities']['medium'])}")

    # Get schema summary
    print("\n2. Schema Summary:")
    summary = agent.get_schema_summary()
    print(f"  Table: {summary['table_name']}")
    print(f"  Columns by type:")
    for col_type, count in summary['column_types'].items():
        print(f"    {col_type}: {count}")

    # Example query
    print("\n3. Example Query Translation:")
    query = "What is the total transaction amount in EUR by card brand?"

    print(f"\nQuery: {query}")
    result = agent.process_query_with_feedback(query)

    if result['success']:
        print(f"\n✓ Generated SQL:")
        print(f"{result['sql']}\n")
        print(f"Explanation: {result['explanation']}")
        print(f"Confidence: {result['confidence']}")

        if result['warnings']:
            print(f"\nWarnings:")
            for warning in result['warnings']:
                print(f"  - {warning}")
    else:
        print(f"\n✗ Error: {result.get('error')}")


if __name__ == "__main__":
    main()
