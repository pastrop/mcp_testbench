#!/usr/bin/env python3
"""
MCP Client Agent with Reasoning for Pandas Query Operations

This client connects to the MCP Pandas server and uses Claude's extended thinking
capabilities to reason about user queries and select appropriate tools.

Supports Claude Sonnet 4.5 and Haiku 4.5 models.
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from anthropic import Anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class PandasQueryAgent:
    """Agent that uses MCP tools and Claude's reasoning to answer queries about data."""

    # Model configurations
    MODELS = {
        "sonnet": "claude-sonnet-4-20250514",      # Claude Sonnet 4 (latest)
        "haiku": "claude-haiku-4-5-20251001",      # Claude Haiku 4.5 (latest)
    }

    def __init__(
        self,
        model: str = "sonnet",
        api_key: Optional[str] = None,
        max_tokens: int = 4096
    ):
        """
        Initialize the agent.

        Args:
            model: Model to use - 'sonnet' for Sonnet 4.5 or 'haiku' for Haiku 4.5
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            max_tokens: Maximum tokens for response generation
        """
        if model not in self.MODELS:
            raise ValueError(f"Invalid model: {model}. Choose 'sonnet' or 'haiku'")

        self.model_name = self.MODELS[model]
        self.model_type = model
        self.max_tokens = max_tokens

        # Initialize Anthropic client
        self.anthropic = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

        # MCP session (initialized when connecting)
        self.session: Optional[ClientSession] = None
        self.available_tools: List[Dict[str, Any]] = []
        self.dataset_info: Optional[Dict[str, Any]] = None  # Cached schema info

    @asynccontextmanager
    async def connect_to_server(self, server_script: str, data_file: str):
        """
        Connect to MCP server as async context manager.

        Args:
            server_script: Path to the MCP server script
            data_file: Path to the data file to load

        Usage:
            async with agent.connect_to_server("server.py", "data.csv"):
                response = await agent.query("What is the schema?")
        """
        server_params = StdioServerParameters(
            command="python",
            args=[server_script, data_file],
            env=None
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                self.session = session

                # Initialize session
                await session.initialize()

                # List available tools
                tools_list = await session.list_tools()
                self.available_tools = [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.inputSchema
                    }
                    for tool in tools_list.tools
                ]

                print(f"Connected to MCP server. Available tools: {len(self.available_tools)}")

                # Load dataset schema immediately after connection
                try:
                    print("Loading dataset schema...")
                    schema_result = await session.call_tool("get_schema", {})
                    schema_json = "".join(
                        item.text if hasattr(item, "text") else str(item)
                        for item in schema_result.content
                    )
                    self.dataset_info = json.loads(schema_json)

                    columns = [col["name"] for col in self.dataset_info["columns"]]
                    print(f"Dataset loaded: {self.dataset_info['total_rows']} rows, {len(columns)} columns")
                except Exception as e:
                    print(f"Warning: Could not load schema: {e}")
                    self.dataset_info = None

                try:
                    yield self
                finally:
                    self.session = None
                    self.available_tools = []
                    self.dataset_info = None

    def _create_system_prompt(self) -> str:
        """Create system prompt with tool descriptions and reasoning instructions."""

        # Build dataset information dynamically
        if self.dataset_info:
            columns = [col["name"] for col in self.dataset_info["columns"]]
            total_rows = self.dataset_info["total_rows"]

            dataset_description = f"""- You have access to MCP tools that can query a dataset with {total_rows:,} rows and the following columns:
  {", ".join(columns)}"""
        else:
            # Fallback if schema wasn't loaded
            dataset_description = """- You have access to MCP tools that can query a dataset.
- Use the get_schema tool first to understand the available columns and data structure."""

        return f"""You are an expert data analyst assistant that helps users query and analyze data stored in a Pandas DataFrame.

Your capabilities:
{dataset_description}

- You can perform SQL-like operations: filtering, aggregation, grouping, sorting, searching, etc.

Your reasoning process:
1. UNDERSTAND the user's query and intent
2. DETERMINE if the query can be answered with the available data
3. If NOT answerable: Politely explain why and ask for clarification
4. If answerable:
   - Break down the query into logical steps
   - Select the appropriate tool(s) to use
   - Execute tool calls in the right order
   - Synthesize results into a clear, natural language response

Important guidelines:
- Use extended thinking to reason through complex queries
- The column information is provided above - you don't need to call get_schema unless you need detailed column statistics
- For complex queries, you may need multiple tool calls
- Present results clearly with relevant context
- If results are truncated, mention this to the user
- Stay focused on the data - don't answer questions outside the dataset scope

When you're unsure or the query is ambiguous, ask clarifying questions before proceeding.
"""

    def _convert_tools_for_claude(self) -> List[Dict[str, Any]]:
        """Convert MCP tools to Claude-compatible tool format."""
        claude_tools = []

        for tool in self.available_tools:
            claude_tool = {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["input_schema"]
            }
            claude_tools.append(claude_tool)

        return claude_tools

    async def _execute_tool_call(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """Execute a tool call via MCP and return the result."""
        if not self.session:
            raise RuntimeError("Not connected to MCP server")

        result = await self.session.call_tool(tool_name, tool_input)

        # Extract content from result
        if result.content:
            return "".join(
                item.text if hasattr(item, "text") else str(item)
                for item in result.content
            )
        return ""

    async def query(self, user_query: str, conversation_history: Optional[List[Dict]] = None) -> str:
        """
        Process a user query and return a response.

        Args:
            user_query: Natural language query from the user
            conversation_history: Optional list of previous messages for context

        Returns:
            Natural language response to the query
        """
        if not self.session:
            raise RuntimeError("Not connected to MCP server. Use 'async with agent.connect_to_server(...)'")

        # Build messages
        messages = conversation_history or []
        messages.append({
            "role": "user",
            "content": user_query
        })

        # Convert tools to Claude format
        claude_tools = self._convert_tools_for_claude()

        # Enable extended thinking for Sonnet
        thinking_config = {
            "type": "enabled",
            "budget_tokens": 2000
        } if self.model_type == "sonnet" else {"type": "disabled"}

        # Make initial API call
        response = self.anthropic.messages.create(
            model=self.model_name,
            max_tokens=self.max_tokens,
            system=self._create_system_prompt(),
            messages=messages,
            tools=claude_tools,
            thinking=thinking_config
        )

        # Process response and handle tool calls
        max_iterations = 10
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            # Check stop reason
            if response.stop_reason == "end_turn":
                # Extract final text response
                final_response = ""
                for block in response.content:
                    if block.type == "text":
                        final_response += block.text
                return final_response.strip()

            elif response.stop_reason == "tool_use":
                # Execute tool calls
                tool_results = []

                for block in response.content:
                    if block.type == "tool_use":
                        print(f"[Tool Call] {block.name} with input: {json.dumps(block.input, indent=2)}")

                        try:
                            # Execute tool via MCP
                            result = await self._execute_tool_call(block.name, block.input)
                            print(f"[Tool Result] Success: {len(result)} characters")

                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result
                            })
                        except Exception as e:
                            print(f"[Tool Error] {str(e)}")
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": f"Error: {str(e)}",
                                "is_error": True
                            })

                # Add assistant response and tool results to messages
                messages.append({
                    "role": "assistant",
                    "content": response.content
                })
                messages.append({
                    "role": "user",
                    "content": tool_results
                })

                # Continue conversation
                response = self.anthropic.messages.create(
                    model=self.model_name,
                    max_tokens=self.max_tokens,
                    system=self._create_system_prompt(),
                    messages=messages,
                    tools=claude_tools,
                    thinking=thinking_config
                )

            else:
                # Unexpected stop reason
                return f"Unexpected stop reason: {response.stop_reason}"

        return "Max iterations reached. The query may be too complex."

    async def interactive_session(self):
        """Run an interactive query session."""
        print(f"\n{'='*60}")
        print(f"Pandas Query Agent - Interactive Mode")
        print(f"Model: {self.model_name} ({self.model_type.upper()})")
        print(f"{'='*60}\n")

        conversation_history = []

        while True:
            try:
                # Get user input
                user_input = input("\n🔍 Your query (or 'quit' to exit): ").strip()

                if not user_input:
                    continue

                if user_input.lower() in ["quit", "exit", "q"]:
                    print("\nGoodbye!")
                    break

                # Special commands
                if user_input.lower() == "clear":
                    conversation_history = []
                    print("Conversation history cleared.")
                    continue

                if user_input.lower() == "history":
                    print(f"\nConversation has {len(conversation_history)} messages")
                    continue

                # Process query
                print("\n💭 Thinking...")
                response = await self.query(user_input, conversation_history)

                # Display response
                print(f"\n{'='*60}")
                print("📊 Response:")
                print(f"{'='*60}")
                print(response)
                print(f"{'='*60}\n")

                # Update conversation history
                conversation_history.append({
                    "role": "user",
                    "content": user_input
                })
                conversation_history.append({
                    "role": "assistant",
                    "content": response
                })

            except KeyboardInterrupt:
                print("\n\nInterrupted. Type 'quit' to exit.")
            except Exception as e:
                print(f"\n❌ Error: {e}")


async def main():
    """Main entry point for the client."""
    import sys

    if len(sys.argv) < 3:
        print("Usage: python mcp_client_agent.py <mcp_server_script> <data_file> [model]")
        print("  model: 'sonnet' (default) or 'haiku'")
        print("\nExample:")
        print("  python mcp_client_agent.py mcp_server_pandas.py data.csv sonnet")
        sys.exit(1)

    server_script = sys.argv[1]
    data_file = sys.argv[2]
    model = sys.argv[3] if len(sys.argv) > 3 else "sonnet"

    # Validate files exist
    if not os.path.exists(server_script):
        print(f"Error: Server script not found: {server_script}")
        sys.exit(1)

    if not os.path.exists(data_file):
        print(f"Error: Data file not found: {data_file}")
        sys.exit(1)

    # Check API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        sys.exit(1)

    # Create agent
    try:
        agent = PandasQueryAgent(model=model)

        # Connect to server and run interactive session
        async with agent.connect_to_server(server_script, data_file):
            await agent.interactive_session()

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
