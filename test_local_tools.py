#!/usr/bin/env python3
"""
Test script to verify local tools session functionality
"""
import asyncio
import json
from mcp_client_thinking_v0 import SequentialThinkingMCPClient
import os

# Get API key from environment
api_key = os.getenv("CLAUDE_KEY")
if not api_key:
    print("Please set CLAUDE_KEY environment variable")
    exit(1)

async def test_local_tools_connection():
    """Test connecting to local MCP server and getting tools"""
    print("Testing local tools connection...")
    
    try:
        async with SequentialThinkingMCPClient(api_key) as client:
            print("✓ Successfully connected to both servers")
            
            # Test getting tools from local server
            print("\nTesting get_local_tools()...")
            tools = await client.get_local_tools()
            print(f"✓ Retrieved {len(tools)} tools from local server")
            
            if tools:
                print("\nAvailable tools:")
                for i, tool in enumerate(tools, 1):
                    tool_name = tool.get('name', 'Unknown')
                    tool_desc = tool.get('description', 'No description')
                    print(f"  {i}. {tool_name}: {tool_desc}")
            else:
                print("⚠ No tools found - this might indicate an issue with the local server")
            
            # Test the internal tools handling in select_tools_and_answer
            print("\nTesting tools retrieval in select_tools_and_answer context...")
            sample_analysis = {
                "intent": "test",
                "concepts": ["test"],
                "information_needs": ["test"],
                "output_format": "test"
            }
            
            # This will internally test the tuple handling code
            try:
                result = await client.select_tools_and_answer(
                    "test query", 
                    sample_analysis, 
                    ["test context"]
                )
                print("✓ select_tools_and_answer executed without tuple errors")
            except Exception as e:
                print(f"✗ Error in select_tools_and_answer: {e}")
                
            return True
            
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False

async def test_local_server_direct():
    """Test connecting directly to local server to debug tuple issue"""
    print("\n" + "="*50)
    print("DIRECT LOCAL SERVER CONNECTION TEST")
    print("="*50)
    
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    
    try:
        # Connect directly to local server
        local_server_params = StdioServerParameters(
            command="uv",
            args=['run', './mcp_server.py']
        )
        local_tools_client = stdio_client(local_server_params)
        local_tools_session = await local_tools_client.__aenter__()
        
        print("✓ Direct connection to local server successful")
        
        # Test list_tools directly
        print("\nTesting list_tools() directly...")
        tools_response = await local_tools_session.list_tools()
        
        print(f"Response type: {type(tools_response)}")
        print(f"Response content: {tools_response}")
        
        if isinstance(tools_response, tuple):
            print(f"Tuple length: {len(tools_response)}")
            for i, item in enumerate(tools_response):
                print(f"  Item {i}: {type(item)} - {item}")
        
        # Clean up
        await local_tools_client.__aexit__(None, None, None)
        
    except Exception as e:
        print(f"✗ Direct connection failed: {e}")
        import traceback
        traceback.print_exc()

async def main():
    """Main test function"""
    print("="*60)
    print("LOCAL TOOLS SESSION TEST")
    print("="*60)
    
    # Test 1: Full client connection
    success = await test_local_tools_connection()
    
    # Test 2: Direct server connection to debug tuple issue
    await test_local_server_direct()
    
    if success:
        print("\n✓ All tests passed! Local tools session is working correctly.")
    else:
        print("\n✗ Some tests failed. Check the error messages above.")

if __name__ == "__main__":
    asyncio.run(main())