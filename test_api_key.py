#!/usr/bin/env python3
"""
Test script to verify ANTHROPIC_API_KEY is set and working.
"""

import os
from anthropic import Anthropic


def test_api_key():
    """Test if the Anthropic API key is set and valid."""

    print("="*60)
    print("Anthropic API Key Test")
    print("="*60)

    # Check if key is set
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        print("❌ ANTHROPIC_API_KEY environment variable is NOT set in this Python process")
        print("\nTo set it:")
        print("  export ANTHROPIC_API_KEY='your-api-key-here'")
        print("\nNote: Make sure you run this script in the SAME terminal where you set the variable:")
        print("  python test_api_key.py")
        print("\nOr set it inline:")
        print("  ANTHROPIC_API_KEY='your-key' python test_api_key.py")
        return False

    print(f"✓ ANTHROPIC_API_KEY is set")
    print(f"  Key prefix: {api_key[:10]}...")
    print(f"  Key length: {len(api_key)} characters")

    # Test API call
    print("\nTesting API connection...")
    try:
        client = Anthropic(api_key=api_key)

        # Make a minimal API call to test authentication
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",  # Using Haiku 4.5 for speed
            max_tokens=10,
            messages=[
                {"role": "user", "content": "Hi"}
            ]
        )

        print("✓ API key is VALID and working!")
        print(f"  Model: {response.model}")
        print(f"  Response: {response.content[0].text}")
        print(f"  Tokens used: {response.usage.input_tokens} input, {response.usage.output_tokens} output")

        return True

    except Exception as e:
        print(f"❌ API key test FAILED: {e}")
        print("\nPossible issues:")
        print("  - Invalid API key")
        print("  - Expired API key")
        print("  - Network connectivity issues")
        print("  - API quota exceeded")
        return False


if __name__ == "__main__":
    print()
    success = test_api_key()
    print("\n" + "="*60)
    if success:
        print("✓ All checks passed - ready to use the agent!")
    else:
        print("✗ Please fix the issues above before using the agent")
    print("="*60 + "\n")
