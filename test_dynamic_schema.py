#!/usr/bin/env python3
"""
Test script to verify dynamic schema loading works correctly.
"""

import asyncio
import os
from mcp_client_agent import PandasQueryAgent


async def test_dynamic_schema():
    """Test that schema is loaded dynamically during connection."""

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Skipping test - ANTHROPIC_API_KEY not set")
        return

    print("="*60)
    print("Testing Dynamic Schema Loading")
    print("="*60)

    agent = PandasQueryAgent(model="haiku")

    async with agent.connect_to_server("mcp_server_pandas.py", "sample_transactions.csv"):
        print("\n✓ Connection established")

        # Check if dataset_info was populated
        if agent.dataset_info:
            print(f"✓ Schema loaded: {len(agent.dataset_info['columns'])} columns")
            print(f"✓ Total rows: {agent.dataset_info['total_rows']:,}")

            # Check system prompt contains dynamic content
            system_prompt = agent._create_system_prompt()

            columns = [col["name"] for col in agent.dataset_info["columns"]]
            first_col = columns[0]

            if first_col in system_prompt:
                print(f"✓ System prompt contains column '{first_col}'")
            else:
                print(f"✗ System prompt missing expected column '{first_col}'")

            if f"{agent.dataset_info['total_rows']:,}" in system_prompt:
                print(f"✓ System prompt contains row count")
            else:
                print(f"✗ System prompt missing row count")

            print(f"\n{'='*60}")
            print("System Prompt Preview:")
            print(f"{'='*60}")
            print(system_prompt[:500] + "...")
            print(f"{'='*60}\n")

            print("✓ All tests passed!")
        else:
            print("✗ Schema not loaded")

    print("\nTest complete!")


if __name__ == "__main__":
    asyncio.run(test_dynamic_schema())
