"""
Demo script for the Text-to-SQL Agent

Run this to see the agent in action.
Set ANTHROPIC_API_KEY environment variable to enable query translation.
"""

import os
from pathlib import Path
from agent import TextToSQLAgent


def demo_schema_analysis():
    """Demonstrate schema analysis and ambiguity detection."""
    print("\n" + "=" * 80)
    print("TEXT-TO-SQL AGENT DEMO")
    print("=" * 80)

    # Get the path to schema.json relative to this file
    script_dir = Path(__file__).parent
    schema_path = script_dir / "schema.json"

    # Initialize agent
    print("\n1. Initializing agent...")
    agent = TextToSQLAgent(schema_path=str(schema_path), table_name="transactions")

    # Initialize and analyze schema
    print("2. Loading and analyzing schema...")
    init_result = agent.initialize()

    if not init_result["success"]:
        print(f"❌ Error: {init_result['error']}")
        return None

    print(f"✅ Loaded {init_result['columns_loaded']} columns")
    print(f"✅ Found {init_result['ambiguities']['total']} potential ambiguities")
    print(f"   - High priority: {len(init_result['ambiguities']['high'])}")
    print(f"   - Medium priority: {len(init_result['ambiguities']['medium'])}")

    # Get schema summary
    print("\n3. Schema Summary:")
    summary = agent.get_schema_summary()
    print(f"   Table: {summary['table_name']}")
    print(f"   Total columns: {summary['total_columns']}")
    print(f"   Column types:")
    for col_type, count in summary['column_types'].items():
        if count > 0:
            print(f"     - {col_type}: {count}")

    # Show some ambiguities
    print("\n4. Sample Ambiguities Detected:")
    ambiguities = agent.get_ambiguities_for_review()
    for i, amb in enumerate(ambiguities[:3]):  # Show first 3
        print(f"\n   Ambiguity {i+1} [{amb['severity'].upper()}]:")
        print(f"   Reason: {amb['reason']}")
        print(f"   Affected columns: {', '.join([c['name'] for c in amb['columns']])}")

    # Add example clarifications
    print("\n5. Adding example clarifications...")
    agent.add_clarification(
        "amount_eur",
        "This is the transaction amount in EUR after currency conversion"
    )
    agent.add_clarification(
        "comission_eur",
        "This is the total commission charged in EUR, including all fee components"
    )
    print(f"✅ Added {len(agent.schema_manager.clarifications)} clarifications")

    # Search columns
    print("\n6. Searching for 'commission' columns...")
    results = agent.schema_manager.search_columns("commission")
    print(f"   Found {len(results)} matching columns:")
    for col in results[:5]:
        print(f"     - {col.name} ({col.type}): {col.short_description}")

    return agent


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

    # Example queries
    queries = [
        "What is the total transaction amount in EUR?",
        "Show top 5 merchants by commission earned",
        "How many approved transactions were there in January 2024?",
    ]

    for i, query in enumerate(queries, 1):
        print(f"\n{i}. Query: {query}")
        print("   Translating...")

        result = agent.process_query_with_feedback(query)

        if result['success']:
            print(f"\n   ✅ Generated SQL:")
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

            # Validate
            if result.get('validation', {}).get('valid'):
                print(f"   ✅ Query validation passed")
            else:
                print(f"   ❌ Query validation failed:")
                for error in result.get('validation', {}).get('errors', []):
                    print(f"      - {error}")
        else:
            print(f"   ❌ Error: {result.get('error')}")

        print()


def main():
    """Run the demo."""
    # Demo schema analysis (no API key needed)
    agent = demo_schema_analysis()

    if agent:
        # Demo query translation (requires API key)
        demo_query_translation(agent)

    print("\n" + "=" * 80)
    print("Demo complete!")
    print("=" * 80)
    print("\nTo use the agent in your own code:")
    print("  from agent import TextToSQLAgent")
    print("  agent = TextToSQLAgent('schema.json')")
    print("  agent.initialize()")
    print("  result = agent.translate_query('your question here')")
    print("\nTo run the MCP server:")
    print("  python mcp_server.py")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
