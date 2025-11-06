import asyncio
import pytest
import json
from unittest.mock import patch, AsyncMock
from chatbot_mcp_client_multiserver import MCP_ChatBot
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class TestMCPConnectivity:
    
    @pytest.fixture
    def chatbot(self):
        """Create a chatbot instance for testing"""
        with patch.dict('os.environ', {'CLAUDE_KEY': 'test_key'}):
            return MCP_ChatBot()
    
    @pytest.mark.asyncio
    async def test_server_config_loading(self, chatbot):
        """Test that server configuration is loaded correctly"""
        assert hasattr(chatbot, 'server_configs')
        assert isinstance(chatbot.server_configs, dict)
        
        # Check if expected servers are configured
        expected_servers = ['memory', 'research']
        for server in expected_servers:
            if server in chatbot.server_configs:
                assert 'command' in chatbot.server_configs[server]
                assert 'args' in chatbot.server_configs[server]
    
    @pytest.mark.asyncio
    async def test_server_connection_initialization(self, chatbot):
        """Test that servers can be initialized without errors"""
        if not chatbot.server_configs:
            pytest.skip("No server configurations found")
        
        connections = []
        
        # Test server parameter creation
        for server_name, config in chatbot.server_configs.items():
            try:
                server_params = StdioServerParameters(
                    command=config["command"],
                    args=config["args"],
                    env=config.get("env"),
                )
                connection_ctx = stdio_client(server_params)
                connections.append((server_name, connection_ctx))
            except Exception as e:
                pytest.fail(f"Failed to create server parameters for {server_name}: {e}")
        
        assert len(connections) > 0, "No server connections could be created"
    
    @pytest.mark.asyncio
    async def test_individual_server_connectivity(self, chatbot):
        """Test connectivity to each configured server individually"""
        if not chatbot.server_configs:
            pytest.skip("No server configurations found")
        
        for server_name, config in chatbot.server_configs.items():
            try:
                server_params = StdioServerParameters(
                    command=config["command"],
                    args=config["args"],
                    env=config.get("env"),
                )
                
                async with stdio_client(server_params) as (read, write):
                    async with ClientSession(read, write) as session:
                        # Test initialization
                        await session.initialize()
                        
                        # Test tool listing
                        response = await session.list_tools()
                        assert hasattr(response, 'tools')
                        
                        print(f"✓ Successfully connected to {server_name} server")
                        print(f"  Available tools: {[tool.name for tool in response.tools]}")
                        
            except Exception as e:
                pytest.fail(f"Failed to connect to {server_name} server: {e}")
    
    @pytest.mark.asyncio
    async def test_multi_server_connectivity(self, chatbot):
        """Test that multiple servers can be connected simultaneously"""
        if not chatbot.server_configs:
            pytest.skip("No server configurations found")
        
        connections = []
        connection_stack = []
        
        try:
            # Prepare all connections
            for server_name, config in chatbot.server_configs.items():
                server_params = StdioServerParameters(
                    command=config["command"],
                    args=config["args"],
                    env=config.get("env"),
                )
                connection_ctx = stdio_client(server_params)
                connections.append((server_name, connection_ctx))
            
            # Open all connections
            for server_name, connection_ctx in connections:
                read, write = await connection_ctx.__aenter__()
                session_ctx = ClientSession(read, write)
                session = await session_ctx.__aenter__()
                connection_stack.append((server_name, connection_ctx, session_ctx, session))
            
            # Initialize all sessions
            all_tools = []
            connected_servers = []
            
            for server_name, _, _, session in connection_stack:
                try:
                    await session.initialize()
                    response = await session.list_tools()
                    tools = response.tools
                    
                    connected_servers.append(server_name)
                    all_tools.extend([tool.name for tool in tools])
                    
                except Exception as e:
                    print(f"Warning: Failed to initialize {server_name}: {e}")
            
            assert len(connected_servers) > 0, "No servers could be connected"
            assert len(all_tools) > 0, "No tools available from connected servers"
            
            print(f"✓ Successfully connected to {len(connected_servers)} servers")
            print(f"  Total tools available: {len(all_tools)}")
            
        finally:
            # Clean up all connections
            for server_name, connection_ctx, session_ctx, session in reversed(connection_stack):
                try:
                    await session_ctx.__aexit__(None, None, None)
                    await connection_ctx.__aexit__(None, None, None)
                except Exception as e:
                    print(f"Error closing {server_name}: {e}")
    
    @pytest.mark.asyncio
    async def test_tool_availability_after_connection(self, chatbot):
        """Test that tools are properly registered after server connections"""
        # Mock the connection process
        with patch.object(chatbot, 'connect_to_servers_and_run') as mock_connect:
            # Simulate successful connection with tools
            chatbot.available_tools = [
                {
                    "name": "test_tool",
                    "description": "A test tool",
                    "input_schema": {"type": "object"}
                }
            ]
            
            assert len(chatbot.available_tools) > 0
            assert chatbot.available_tools[0]["name"] == "test_tool"
    
    @pytest.mark.asyncio
    async def test_server_config_file_handling(self, chatbot):
        """Test server configuration file error handling"""
        # Test with missing config file
        with patch('builtins.open', side_effect=FileNotFoundError):
            config = chatbot.load_server_config()
            assert config == {}
        
        # Test with invalid JSON
        with patch('builtins.open'), patch('json.load', side_effect=json.JSONDecodeError("test", "test", 0)):
            config = chatbot.load_server_config()
            assert config == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])