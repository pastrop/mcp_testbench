"""
Interactive Demo for Text-to-SQL Agent

This demo includes the human-in-the-loop clarification workflow.
Run this to see the full interactive experience including ambiguity resolution.
Set ANTHROPIC_API_KEY environment variable to enable query translation.
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from agent import TextToSQLAgent


class TeeOutput:
    """Captures output to both console and file."""

    def __init__(self, filepath):
        self.terminal = sys.stdout
        self.log = open(filepath, 'w', encoding='utf-8')

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        self.terminal.flush()
        self.log.flush()

    def close(self):
        self.log.close()


def demo_schema_analysis_interactive(agent):
    """Demonstrate schema analysis with interactive ambiguity resolution."""
    print("\n" + "=" * 80)
    print("TEXT-TO-SQL AGENT DEMO (INTERACTIVE)")
    print("=" * 80)

    # Initialize and analyze schema
    print("\n1. Initializing agent and loading schema...")
    init_result = agent.initialize()

    if not init_result["success"]:
        print(f"❌ Error: {init_result['error']}")
        return False

    print(f"✅ Loaded {init_result['columns_loaded']} columns")
    print(f"✅ Found {init_result['ambiguities']['total']} potential ambiguities")
    print(f"   - High priority: {len(init_result['ambiguities']['high'])}")
    print(f"   - Medium priority: {len(init_result['ambiguities']['medium'])}")

    # Get schema summary
    print("\n2. Schema Summary:")
    summary = agent.get_schema_summary()
    print(f"   Table: {summary['table_name']}")
    print(f"   Total columns: {summary['total_columns']}")
    print(f"   Column types:")
    for col_type, count in summary['column_types'].items():
        if count > 0:
            print(f"     - {col_type}: {count}")

    # Show some ambiguities
    print("\n3. Sample Ambiguities Detected:")
    ambiguities = agent.get_ambiguities_for_review()
    for i, amb in enumerate(ambiguities[:3]):  # Show first 3
        print(f"\n   Ambiguity {i+1} [{amb['severity'].upper()}]:")
        print(f"   Reason: {amb['reason']}")
        print(f"   Affected columns: {', '.join([c['name'] for c in amb['columns']])}")

    # Interactive clarification session
    print("\n4. Starting Interactive Clarification Session...")
    print("=" * 80)
    print("You will now be prompted to clarify ambiguities in the schema.")
    print("This helps the agent generate more accurate SQL queries.")
    print("=" * 80)

    if init_result['ambiguities']['total'] > 0:
        agent.interactive_clarification_session()
        print(f"\n✅ Added {len(agent.schema_manager.clarifications)} clarifications")
    else:
        print("\n✅ No ambiguities found - schema is clear!")

    # Search columns
    print("\n5. Searching for 'commission' columns...")
    results = agent.schema_manager.search_columns("commission")
    print(f"   Found {len(results)} matching columns:")
    for col in results[:5]:
        print(f"     - {col.name} ({col.type}): {col.short_description}")

    return True


def demo_query_translation(agent):
    """Demonstrate query translation (requires API key)."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("\n" + "=" * 80)
        print("⚠️  ANTHROPIC_API_KEY not set - skipping query translation demo")
        print("   Set the API key to see query translation in action:")
        print("   export ANTHROPIC_API_KEY='your-key-here'")
        print("=" * 80)
        return

    print("\n" + "=" * 80)
    print("QUERY TRANSLATION DEMO")
    print("=" * 80)

    # Example queries - same as automated demo
    queries = [
        "What is the total transaction amount in EUR for all approved transactions in the last month?",
        "Which merchants have the highest total commission fees across all their transactions?",
        "What is the average MDR percentage applied to Visa transactions compared to Mastercard transactions?",
        "How many transactions were declined by each processor, and what are the most common error codes?",
        "What is the distribution of transaction types (payment, payout, refund) by merchant group?",
        "Which countries generate the most transaction volume, and what is their approval rate?"
    ]

    for i, query in enumerate(queries, 1):
        print(f"\n{i}. Query: {query}")
        print("   Translating...")

        # Try with auto_retry enabled to demonstrate rebuild functionality
        result = agent.process_query_with_feedback(query, auto_retry=True)

        if result['success']:
            # Check if query was rebuilt
            if result.get('rebuilt'):
                print(f"\n   🔨 Query was REBUILT (attempt {result.get('retry_count', 0)})")
                print(f"   Rebuild successful: {result.get('rebuild_successful', False)}")

                # Show original failed query
                if result.get('original_sql'):
                    print(f"\n   ❌ Original SQL (FAILED validation):")
                    print("   " + "-" * 76)
                    for line in result['original_sql'].split('\n')[:5]:
                        print(f"   {line}")
                    if len(result['original_sql'].split('\n')) > 5:
                        print("   ...")
                    print("   " + "-" * 76)

                    # Show why it failed
                    orig_errors = result.get('original_validation', {}).get('errors', [])
                    if orig_errors:
                        print(f"\n   Original validation errors:")
                        for error in orig_errors:
                            print(f"      - {error}")

            print(f"\n   ✅ Final SQL:")
            print("   " + "-" * 76)
            for line in result['sql'].split('\n'):
                print(f"   {line}")
            print("   " + "-" * 76)
            print(f"\n   Explanation: {result['explanation']}")
            print(f"   Confidence: {result['confidence']}")

            if result['warnings']:
                print(f"\n   ⚠️  Warnings:")
                for warning in result['warnings']:
                    print(f"      - {warning}")

            # Final validation status
            if result.get('validation', {}).get('valid'):
                print(f"   ✅ Final validation: PASSED")
            else:
                print(f"   ❌ Final validation: FAILED")
                for error in result.get('validation', {}).get('errors', []):
                    print(f"      - {error}")
        else:
            print(f"   ❌ Error: {result.get('error')}")

        print()


def main():
    """Run the interactive demo."""
    # Create output filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    script_dir = Path(__file__).parent
    output_file = script_dir / f"demo_interactive_output_{timestamp}.txt"

    # Set up output capture to both console and file
    tee = TeeOutput(output_file)
    original_stdout = sys.stdout
    sys.stdout = tee

    try:
        print(f"Interactive demo output is being saved to: {output_file.name}")
        print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        # Get the path to schema.json relative to this file
        script_dir = Path(__file__).parent
        schema_path = script_dir / "schema.json"

        # Initialize agent
        agent = TextToSQLAgent(schema_path=str(schema_path), table_name="transactions")

        # Demo schema analysis with interactive clarification
        success = demo_schema_analysis_interactive(agent)

        if success:
            # Demo query translation (requires API key)
            demo_query_translation(agent)

        print("\n" + "=" * 80)
        print("Interactive Demo Complete!")
        print("=" * 80)
        print("\nTo use the agent in your own code:")
        print("  from agent import TextToSQLAgent")
        print("  agent = TextToSQLAgent('schema.json')")
        print("  agent.initialize()")
        print("  agent.interactive_clarification_session()  # Optional")
        print("  result = agent.translate_query('your question here')")
        print("\nTo run the automated demo (no user input):")
        print("  python demo.py")
        print("\nTo run the MCP server:")
        print("  python mcp_server.py")
        print("=" * 80)
        print(f"\nEnd time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Output saved to: {output_file}")

    finally:
        # Restore stdout and close the file
        sys.stdout = original_stdout
        tee.close()
        print(f"\n✅ Interactive demo complete! Output saved to: {output_file}")


if __name__ == "__main__":
    main()
