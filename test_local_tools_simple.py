#!/usr/bin/env python3
"""
Simple test to verify the tuple handling fix
"""
import asyncio
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test_direct_connection():
    """Test the direct connection to see what type of object we get"""
    print("Testing direct connection to local MCP server...")
    
    try:
        # Connect directly to local server
        local_server_params = StdioServerParameters(
            command="uv",
            args=['run', './mcp_server.py']
        )
        local_tools_client = stdio_client(local_server_params)
        
        print("Created stdio_client, calling __aenter__...")
        result = await local_tools_client.__aenter__()
        
        print(f"Result type: {type(result)}")
        print(f"Result: {result}")
        
        if isinstance(result, tuple):
            print(f"Tuple length: {len(result)}")
            read_stream, write_stream = result
            print(f"Read stream type: {type(read_stream)}")
            print(f"Write stream type: {type(write_stream)}")
            
            # Create ClientSession from streams
            session = ClientSession(read_stream, write_stream)
            print(f"Created ClientSession: {type(session)}")
            
            # Initialize the session
            await session.initialize()
            print("Session initialized successfully")
            
            # Test list_tools
            tools_response = await session.list_tools()
            print(f"Tools response type: {type(tools_response)}")
            print(f"Tools response: {tools_response}")
            
            if hasattr(tools_response, 'tools'):
                print(f"Found {len(tools_response.tools)} tools")
                for tool in tools_response.tools:
                    print(f"  Tool: {tool.name}")
            
        # Clean up
        await local_tools_client.__aexit__(None, None, None)
        print("Connection closed successfully")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

async def main():
    print("="*50)
    print("SIMPLE LOCAL TOOLS CONNECTION TEST")
    print("="*50)
    
    await test_direct_connection()

if __name__ == "__main__":
    asyncio.run(main())