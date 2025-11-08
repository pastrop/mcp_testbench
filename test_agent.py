#!/usr/bin/env python3
"""
Quick test script for the Pandas Query Agent.

Tests basic functionality without requiring interactive input.
Logs all output to both console and a log file.
"""

import asyncio
import os
import sys
from datetime import datetime
from mcp_client_agent import PandasQueryAgent


class TeeOutput:
    """Writes output to both console and a file."""

    def __init__(self, filename):
        self.terminal = sys.stdout
        self.log = open(filename, 'w', encoding='utf-8')

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):
        self.terminal.flush()
        self.log.flush()

    def close(self):
        self.log.close()


async def test_queries(output_file=None):
    """Run a series of test queries."""

    # Setup output logging
    tee = None
    if output_file:
        tee = TeeOutput(output_file)
        sys.stdout = tee
        sys.stderr = tee

    try:
        # Check API key
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("Error: ANTHROPIC_API_KEY environment variable not set")
            return

        print("="*60)
        print("Pandas Query Agent - Test Mode")
        print(f"Test started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if output_file:
            print(f"Logging to: {output_file}")
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

    finally:
        # Restore stdout/stderr and close log file
        if tee:
            sys.stdout = tee.terminal
            sys.stderr = tee.terminal
            tee.close()


if __name__ == "__main__":
    # Generate output filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f"test_agent_output_{timestamp}.log"

    asyncio.run(test_queries(output_file))

    print(f"\n✓ Test complete! Output saved to: {output_file}")
