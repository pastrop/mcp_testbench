#!/usr/bin/env python3
"""
Quick test script for the Pandas Query Agent.

Tests basic functionality without requiring interactive input.
"""

import asyncio
import os
from mcp_client_agent import PandasQueryAgent


async def test_queries():
    """Run a series of test queries."""

    # Check API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        return

    print("="*60)
    print("Pandas Query Agent - Test Mode")
    print("="*60)

    # Test queries
    test_cases = [
        {
            "query": "What is the schema of the dataset?",
            "description": "Schema query - tests get_schema tool"
        },
        {
            "query": "How many total transactions are in the dataset?",
            "description": "Count query - tests get_row_count tool"
        },
        {
            "query": "What are the top 5 merchants by total transaction amount?",
            "description": "Aggregation query - tests group_by_aggregate and get_top_n"
        }
    ]

    # Create agent with Haiku for faster testing
    agent = PandasQueryAgent(model="haiku")

    try:
        async with agent.connect_to_server("mcp_server_pandas.py", "sample_transactions.csv"):
            print(f"\nRunning {len(test_cases)} test queries...\n")

            for i, test in enumerate(test_cases, 1):
                print(f"\n{'='*60}")
                print(f"TEST {i}: {test['description']}")
                print(f"{'='*60}")
                print(f"Query: {test['query']}")
                print(f"\nProcessing...")

                try:
                    response = await agent.query(test['query'])
                    print(f"\nResponse:\n{response}")
                    print(f"\n✓ Test {i} passed")
                except Exception as e:
                    print(f"\n✗ Test {i} failed: {e}")

            print(f"\n{'='*60}")
            print("All tests completed!")
            print(f"{'='*60}\n")

    except Exception as e:
        print(f"\nError: {e}")


if __name__ == "__main__":
    asyncio.run(test_queries())
