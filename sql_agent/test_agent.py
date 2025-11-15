"""
Comprehensive Test Suite for Text-to-SQL Agent

Tests all components including schema management, query translation,
and end-to-end agent functionality.
"""

import unittest
import os
from pathlib import Path
from unittest.mock import patch
from schema_manager import SchemaManager
from query_translator import QueryTranslator
from agent import TextToSQLAgent


# Get the directory where this test file is located
TEST_DIR = Path(__file__).parent
SCHEMA_PATH = TEST_DIR / "schema.json"


class TestSchemaManager(unittest.TestCase):
    """Test cases for SchemaManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.schema_manager = SchemaManager(str(SCHEMA_PATH))

    def test_load_schema_success(self):
        """Test successful schema loading."""
        result = self.schema_manager.load_schema()
        self.assertTrue(result)
        self.assertGreater(len(self.schema_manager.columns), 0)

    def test_load_schema_with_invalid_path(self):
        """Test schema loading with invalid path."""
        manager = SchemaManager("nonexistent.json")
        result = manager.load_schema()
        self.assertFalse(result)

    def test_analyze_schema_detects_ambiguities(self):
        """Test that schema analysis detects ambiguities."""
        self.schema_manager.load_schema()
        ambiguities = self.schema_manager.analyze_schema()

        # Should detect multiple ambiguities in the payment schema
        self.assertGreater(len(ambiguities), 0)

        # Check for expected ambiguity types
        reasons = [amb.reason for amb in ambiguities]
        has_commission_ambiguity = any('commission' in r.lower() for r in reasons)
        self.assertTrue(has_commission_ambiguity)

    def test_detect_similar_names(self):
        """Test detection of similar column names."""
        self.schema_manager.load_schema()
        self.schema_manager._detect_similar_names()

        # Should detect EUR vs non-EUR variants
        ambiguities = self.schema_manager.ambiguities
        self.assertGreater(len(ambiguities), 0)

    def test_add_clarification(self):
        """Test adding clarifications to columns."""
        self.schema_manager.load_schema()
        test_clarification = "Use this column for EUR amounts only"

        self.schema_manager.add_clarification("amount_eur", test_clarification)

        self.assertIn("amount_eur", self.schema_manager.clarifications)
        self.assertEqual(
            self.schema_manager.clarifications["amount_eur"],
            test_clarification
        )

    def test_get_column(self):
        """Test retrieving a column by name."""
        self.schema_manager.load_schema()

        col = self.schema_manager.get_column("transaction_id")
        self.assertIsNotNone(col)
        self.assertEqual(col.name, "transaction_id")
        self.assertEqual(col.type, "STRING")

    def test_get_column_not_found(self):
        """Test retrieving non-existent column."""
        self.schema_manager.load_schema()

        col = self.schema_manager.get_column("nonexistent_column")
        self.assertIsNone(col)

    def test_get_columns_by_type(self):
        """Test filtering columns by type."""
        self.schema_manager.load_schema()

        float_cols = self.schema_manager.get_columns_by_type("FLOAT")
        self.assertGreater(len(float_cols), 0)

        for col in float_cols:
            self.assertEqual(col.type, "FLOAT")

    def test_search_columns(self):
        """Test searching columns by keyword."""
        self.schema_manager.load_schema()

        results = self.schema_manager.search_columns("commission")
        self.assertGreater(len(results), 0)

        for col in results:
            self.assertTrue(
                'commission' in col.name.lower() or
                'commission' in col.short_description.lower() or
                'commission' in col.detailed_description.lower()
            )

    def test_enriched_schema_description(self):
        """Test generation of enriched schema description."""
        self.schema_manager.load_schema()
        self.schema_manager.add_clarification(
            "amount_eur",
            "Primary transaction amount in EUR"
        )

        description = self.schema_manager.get_enriched_schema_description()

        self.assertIn("amount_eur", description)
        self.assertIn("Primary transaction amount in EUR", description)
        self.assertIn("USER CLARIFICATION", description)


class TestQueryTranslator(unittest.TestCase):
    """Test cases for QueryTranslator."""

    def setUp(self):
        """Set up test fixtures."""
        # Only run these tests if API key is available
        if not os.environ.get("ANTHROPIC_API_KEY"):
            self.skipTest("ANTHROPIC_API_KEY not set")

        self.translator = QueryTranslator()

    def test_translator_initialization(self):
        """Test translator initializes correctly."""
        self.assertIsNotNone(self.translator.client)
        self.assertEqual(self.translator.model, "claude-sonnet-4-5-20250929")

    def test_validate_query_no_joins(self):
        """Test validation rejects queries with JOINs."""
        sql = "SELECT * FROM transactions JOIN orders ON transactions.order_id = orders.id"
        validation = self.translator.validate_query(sql)

        self.assertFalse(validation["valid"])
        self.assertTrue(any("JOIN" in err for err in validation["errors"]))

    def test_validate_query_destructive_operations(self):
        """Test validation rejects destructive operations."""
        destructive_queries = [
            "DROP TABLE transactions",
            "DELETE FROM transactions WHERE 1=1",
            "TRUNCATE TABLE transactions"
        ]

        for sql in destructive_queries:
            validation = self.translator.validate_query(sql)
            self.assertFalse(validation["valid"])

    def test_validate_query_valid_select(self):
        """Test validation accepts valid SELECT query."""
        sql = "SELECT transaction_id, amount_eur FROM transactions WHERE status = 'approved'"
        validation = self.translator.validate_query(sql)

        self.assertTrue(validation["valid"])
        self.assertEqual(len(validation["errors"]), 0)

    @unittest.skipIf(
        os.environ.get("SKIP_API_TESTS") == "1",
        "Skipping API tests to avoid costs"
    )
    def test_translate_simple_query(self):
        """Test translation of a simple query."""
        schema_description = """
        Table: transactions
        Columns:
        - amount_eur (FLOAT): Transaction amount in EUR
        - status (STRING): Transaction status
        """

        result = self.translator.translate(
            "What is the total amount in EUR?",
            schema_description
        )

        self.assertIsNotNone(result.get("sql"))
        self.assertIn("SUM", result["sql"].upper())
        self.assertIn("amount_eur", result["sql"].lower())

    def test_parse_response(self):
        """Test parsing of Claude's response."""
        mock_response = """
SQL:
```sql
SELECT SUM(amount_eur) as total
FROM transactions
WHERE status = 'approved'
```

EXPLANATION:
This query calculates the sum of all approved transactions.

CONFIDENCE: high

WARNINGS:
Excludes non-approved transactions
        """

        result = self.translator._parse_response(mock_response)

        self.assertIsNotNone(result["sql"])
        self.assertIn("SUM(amount_eur)", result["sql"])
        self.assertEqual(result["confidence"], "high")
        self.assertGreater(len(result["warnings"]), 0)


class TestTextToSQLAgent(unittest.TestCase):
    """Test cases for the main TextToSQLAgent."""

    def setUp(self):
        """Set up test fixtures."""
        self.agent = TextToSQLAgent(schema_path=str(SCHEMA_PATH))

    def test_agent_initialization(self):
        """Test agent initializes correctly."""
        result = self.agent.initialize()

        self.assertTrue(result["success"])
        self.assertGreater(result["columns_loaded"], 0)
        self.assertIn("ambiguities", result)

    def test_agent_requires_initialization(self):
        """Test that agent methods require initialization."""
        agent = TextToSQLAgent()

        with self.assertRaises(RuntimeError):
            agent.get_ambiguities_for_review()

        with self.assertRaises(RuntimeError):
            agent.translate_query("test query")

    def test_get_ambiguities_for_review(self):
        """Test retrieving ambiguities for user review."""
        self.agent.initialize()
        ambiguities = self.agent.get_ambiguities_for_review()

        # Should return list of dicts with expected structure
        self.assertIsInstance(ambiguities, list)

        if len(ambiguities) > 0:
            amb = ambiguities[0]
            self.assertIn("id", amb)
            self.assertIn("severity", amb)
            self.assertIn("reason", amb)
            self.assertIn("columns", amb)

    def test_add_clarification(self):
        """Test adding clarifications through the agent."""
        self.agent.initialize()

        self.agent.add_clarification(
            "amount_eur",
            "Transaction amount in EUR after currency conversion"
        )

        self.assertIn("amount_eur", self.agent.schema_manager.clarifications)

    def test_get_schema_summary(self):
        """Test getting schema summary."""
        self.agent.initialize()
        summary = self.agent.get_schema_summary()

        self.assertEqual(summary["table_name"], "transactions")
        self.assertGreater(summary["total_columns"], 0)
        self.assertIn("column_types", summary)

    @unittest.skipIf(
        os.environ.get("SKIP_API_TESTS") == "1",
        "Skipping API tests to avoid costs"
    )
    def test_translate_query_integration(self):
        """Test end-to-end query translation."""
        if not os.environ.get("ANTHROPIC_API_KEY"):
            self.skipTest("ANTHROPIC_API_KEY not set")

        self.agent.initialize()

        result = self.agent.process_query_with_feedback(
            "What is the total commission in EUR by merchant?"
        )

        self.assertTrue(result["success"])
        self.assertIsNotNone(result.get("sql"))
        self.assertIn("confidence", result)

    def test_process_query_with_feedback_format(self):
        """Test that process_query_with_feedback returns correct format."""
        if not os.environ.get("ANTHROPIC_API_KEY"):
            self.skipTest("ANTHROPIC_API_KEY not set")

        self.agent.initialize()

        with patch.object(self.agent.query_translator, 'translate') as mock_translate:
            mock_translate.return_value = {
                "sql": "SELECT * FROM transactions",
                "explanation": "Test explanation",
                "confidence": "high",
                "warnings": [],
                "validation": {"valid": True, "errors": [], "warnings": []}
            }

            result = self.agent.process_query_with_feedback("test query")

            self.assertIn("query", result)
            self.assertIn("success", result)
            self.assertIn("sql", result)
            self.assertIn("confidence", result)


class TestQueryScenarios(unittest.TestCase):
    """Test various query scenarios."""

    def setUp(self):
        """Set up test fixtures."""
        if not os.environ.get("ANTHROPIC_API_KEY"):
            self.skipTest("ANTHROPIC_API_KEY not set")

        if os.environ.get("SKIP_API_TESTS") == "1":
            self.skipTest("Skipping API tests")

        self.agent = TextToSQLAgent(schema_path="schema.json")
        self.agent.initialize()

    def test_aggregation_query(self):
        """Test query with aggregation."""
        result = self.agent.translate_query(
            "What is the total transaction amount in EUR?"
        )

        self.assertIsNotNone(result.get("sql"))
        sql_upper = result["sql"].upper()
        self.assertIn("SUM", sql_upper)
        self.assertTrue("amount_eur" in result["sql"].lower() or "AMOUNT_EUR" in sql_upper)

    def test_filtering_query(self):
        """Test query with WHERE clause."""
        result = self.agent.translate_query(
            "Show all approved transactions"
        )

        self.assertIsNotNone(result.get("sql"))
        sql_upper = result["sql"].upper()
        self.assertIn("WHERE", sql_upper)
        self.assertIn("approved", result["sql"].lower())

    def test_grouping_query(self):
        """Test query with GROUP BY."""
        result = self.agent.translate_query(
            "Show total amount by merchant"
        )

        self.assertIsNotNone(result.get("sql"))
        sql_upper = result["sql"].upper()
        self.assertIn("GROUP BY", sql_upper)

    def test_date_filtering_query(self):
        """Test query with date filtering."""
        result = self.agent.translate_query(
            "Show transactions from January 2024"
        )

        self.assertIsNotNone(result.get("sql"))
        sql_upper = result["sql"].upper()
        self.assertTrue("WHERE" in sql_upper or "BETWEEN" in sql_upper)

    def test_ordering_query(self):
        """Test query with ORDER BY."""
        result = self.agent.translate_query(
            "Show top 10 transactions by amount"
        )

        self.assertIsNotNone(result.get("sql"))
        sql_upper = result["sql"].upper()
        self.assertIn("ORDER BY", sql_upper)
        self.assertIn("LIMIT", sql_upper)


def run_test_suite():
    """Run the complete test suite with detailed output."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test cases
    suite.addTests(loader.loadTestsFromTestCase(TestSchemaManager))
    suite.addTests(loader.loadTestsFromTestCase(TestQueryTranslator))
    suite.addTests(loader.loadTestsFromTestCase(TestTextToSQLAgent))
    suite.addTests(loader.loadTestsFromTestCase(TestQueryScenarios))

    # Run with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Print summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")

    return result.wasSuccessful()


if __name__ == "__main__":
    import sys

    # Run tests
    success = run_test_suite()

    # Exit with appropriate code
    sys.exit(0 if success else 1)
