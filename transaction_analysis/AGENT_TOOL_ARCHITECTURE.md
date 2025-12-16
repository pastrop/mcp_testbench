# Agent-Tool Interaction Architecture

## Overview of Approaches

There are several architectural patterns for giving LLM agents access to tools. Each has different tradeoffs for complexity, performance, and cost.

---

## Approach 1: Native Claude API Tool Use (Recommended)

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Your Application                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │           Orchestration Layer                     │  │
│  │  • Manages conversation state                     │  │
│  │  • Routes tool calls to implementations           │  │
│  │  • Handles batching & caching                     │  │
│  │  • Error handling & retries                       │  │
│  └────────────────┬─────────────────────────────────┘  │
│                   │                                      │
│                   │ 1. Send message + tool definitions   │
│                   ▼                                      │
│  ┌──────────────────────────────────────────────────┐  │
│  │         Claude API Client                         │  │
│  │  anthropic.messages.create(                       │  │
│  │    model="claude-sonnet-4-5",                     │  │
│  │    tools=[...],                                   │  │
│  │    messages=[...]                                 │  │
│  │  )                                                │  │
│  └────────────────┬─────────────────────────────────┘  │
└───────────────────┼──────────────────────────────────────┘
                    │
                    │ 2. Claude decides which tools to call
                    ▼
┌─────────────────────────────────────────────────────────┐
│              Claude API (Sonnet 4.5)                     │
│  • Analyzes request                                      │
│  • Decides which tools to call                           │
│  • Returns tool_use blocks                               │
└────────────────────┬────────────────────────────────────┘
                     │
                     │ 3. Returns tool_use requests
                     ▼
┌─────────────────────────────────────────────────────────┐
│                  Your Application                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │        Tool Execution Layer                       │  │
│  │                                                   │  │
│  │  for tool_use in response.content:               │  │
│  │    if tool_use.type == "tool_use":               │  │
│  │      result = execute_tool(                      │  │
│  │        tool_use.name,                            │  │
│  │        tool_use.input                            │  │
│  │      )                                           │  │
│  └────────────────┬─────────────────────────────────┘  │
│                   │                                      │
│                   │ 4. Execute tools locally             │
│                   ▼                                      │
│  ┌──────────────────────────────────────────────────┐  │
│  │         Python Tool Functions                     │  │
│  │  • load_contract_data()                          │  │
│  │  • calculate_expected_fees()                     │  │
│  │  • compare_fees()                                │  │
│  │  • map_transaction_fields()                      │  │
│  └────────────────┬─────────────────────────────────┘  │
│                   │                                      │
│                   │ 5. Return results to Claude          │
│                   ▼                                      │
│  ┌──────────────────────────────────────────────────┐  │
│  │     Send tool_result back to Claude              │  │
│  │  messages.append({                               │  │
│  │    "role": "assistant",                          │  │
│  │    "content": response.content                   │  │
│  │  })                                              │  │
│  │  messages.append({                               │  │
│  │    "role": "user",                               │  │
│  │    "content": [tool_results]                     │  │
│  │  })                                              │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### Implementation

```python
import anthropic
from typing import Dict, List, Callable
import json

class NativeToolAgent:
    """Agent using Claude's native tool use capability."""

    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.tools = []
        self.tool_functions = {}

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: Dict,
        function: Callable
    ):
        """Register a tool with its implementation."""
        self.tools.append({
            "name": name,
            "description": description,
            "input_schema": input_schema
        })
        self.tool_functions[name] = function

    def execute_tool(self, tool_name: str, tool_input: Dict) -> any:
        """Execute a registered tool."""
        if tool_name not in self.tool_functions:
            raise ValueError(f"Unknown tool: {tool_name}")

        try:
            return self.tool_functions[tool_name](**tool_input)
        except Exception as e:
            return {"error": str(e), "tool": tool_name}

    def run(
        self,
        user_message: str,
        system_prompt: str = "",
        max_iterations: int = 10
    ) -> Dict:
        """
        Run the agent with tool use in agentic loop.

        Returns:
            {
                "final_response": str,
                "tool_calls": List[Dict],
                "iterations": int
            }
        """
        messages = [{"role": "user", "content": user_message}]
        tool_calls = []

        for iteration in range(max_iterations):
            # Call Claude
            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=4096,
                system=system_prompt,
                tools=self.tools,
                messages=messages
            )

            # Check stop reason
            if response.stop_reason == "end_turn":
                # Claude is done, extract final response
                text_blocks = [
                    block.text for block in response.content
                    if hasattr(block, "text")
                ]
                return {
                    "final_response": "\n".join(text_blocks),
                    "tool_calls": tool_calls,
                    "iterations": iteration + 1
                }

            elif response.stop_reason == "tool_use":
                # Claude wants to use tools
                tool_uses = [
                    block for block in response.content
                    if block.type == "tool_use"
                ]

                # Execute each tool
                tool_results = []
                for tool_use in tool_uses:
                    # Execute tool
                    result = self.execute_tool(
                        tool_use.name,
                        tool_use.input
                    )

                    # Track for observability
                    tool_calls.append({
                        "iteration": iteration,
                        "tool": tool_use.name,
                        "input": tool_use.input,
                        "result": result
                    })

                    # Prepare result for Claude
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": json.dumps(result)
                    })

                # Add to message history
                messages.append({
                    "role": "assistant",
                    "content": response.content
                })
                messages.append({
                    "role": "user",
                    "content": tool_results
                })

            else:
                # Unexpected stop reason
                raise ValueError(f"Unexpected stop_reason: {response.stop_reason}")

        raise RuntimeError(f"Agent exceeded max iterations ({max_iterations})")


# Usage Example
agent = NativeToolAgent(api_key="your-key")

# Register tools
agent.register_tool(
    name="calculate_expected_fees",
    description="Calculate expected fees based on contract rule",
    input_schema={
        "type": "object",
        "properties": {
            "amount": {"type": "number"},
            "contract_rule": {"type": "object"},
            "transaction_type": {"type": "string"}
        },
        "required": ["amount", "contract_rule", "transaction_type"]
    },
    function=calculate_expected_fees
)

# Run agent
result = agent.run(
    user_message="Verify this transaction: {...}",
    system_prompt=SYSTEM_PROMPT
)

print(result["final_response"])
print(f"Made {len(result['tool_calls'])} tool calls")
```

### Pros
✅ **Simple** - Direct API integration, no framework needed
✅ **Full control** - You control tool execution
✅ **Efficient** - Claude decides optimal tool sequence
✅ **Observable** - Can log all tool calls
✅ **Flexible** - Easy to add new tools

### Cons
❌ **Boilerplate** - Need to write orchestration loop
❌ **No standard** - Custom implementation
❌ **Local only** - Tools must be in same process

---

## Approach 2: MCP (Model Context Protocol)

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│               Your Application                           │
│  ┌──────────────────────────────────────────────────┐  │
│  │         MCP Client                                │  │
│  │  • Discovers MCP servers                         │  │
│  │  • Gets tool definitions                         │  │
│  │  • Routes tool calls to servers                  │  │
│  └────────────────┬─────────────────────────────────┘  │
└───────────────────┼──────────────────────────────────────┘
                    │
                    │ stdio, HTTP, or WebSocket
                    ▼
┌─────────────────────────────────────────────────────────┐
│            MCP Server (Fee Calculator)                   │
│  ┌──────────────────────────────────────────────────┐  │
│  │  from fastmcp import FastMCP                     │  │
│  │                                                   │  │
│  │  mcp = FastMCP("transaction-verifier")           │  │
│  │                                                   │  │
│  │  @mcp.tool()                                     │  │
│  │  def calculate_expected_fees(...):               │  │
│  │      ...                                         │  │
│  │                                                   │  │
│  │  @mcp.tool()                                     │  │
│  │  def compare_fees(...):                          │  │
│  │      ...                                         │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│            MCP Server (Contract Loader)                  │
│  ┌──────────────────────────────────────────────────┐  │
│  │  @mcp.tool()                                     │  │
│  │  def load_contract_data(...):                    │  │
│  │      ...                                         │  │
│  │                                                   │  │
│  │  @mcp.tool()                                     │  │
│  │  def find_contract_rule(...):                    │  │
│  │      ...                                         │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### Implementation

```python
# server.py - MCP Server
from fastmcp import FastMCP
import pandas as pd
import json

mcp = FastMCP("transaction-fee-verifier")

# Tool 1: Load contract
@mcp.tool()
def load_contract_data(file_path: str) -> dict:
    """Load and parse contract fee structures from JSON file."""
    with open(file_path, 'r') as f:
        data = json.load(f)
    return {
        "card_fees": data.get("card_fees", {}),
        "apm_fees": data.get("apm_open_banking_fees", {}),
        # ... etc
    }

# Tool 2: Calculate fees
@mcp.tool()
def calculate_expected_fees(
    amount: float,
    contract_rule: dict,
    transaction_type: str = "payment"
) -> dict:
    """Calculate expected fees based on contract rule."""
    wl_rate = contract_rule.get("wl_rate", 0.0)
    fixed_fee = contract_rule.get("fixed_fee", 0.0)

    percentage_fee = amount * wl_rate
    total = percentage_fee + fixed_fee

    return {
        "breakdown": {
            "percentage_fee": round(percentage_fee, 2),
            "fixed_fee": fixed_fee,
            "total": round(total, 2)
        },
        "calculation_method": f"({amount} × {wl_rate}) + {fixed_fee}"
    }

# Tool 3: Compare fees
@mcp.tool()
def compare_fees(
    actual_fee: float,
    expected_fee: float,
    tolerance: float = 0.01
) -> dict:
    """Compare actual vs expected fees."""
    difference = actual_fee - expected_fee
    within_tolerance = abs(difference) <= tolerance

    if within_tolerance:
        status = "CORRECT"
    elif difference > 0:
        status = "OVERCHARGED"
    else:
        status = "UNDERCHARGED"

    return {
        "is_correct": within_tolerance,
        "difference_amount": round(difference, 2),
        "status": status
    }

# Run server
if __name__ == "__main__":
    mcp.run()
```

```python
# client.py - Your application
import anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def run_with_mcp():
    """Run agent with MCP tools."""

    # Connect to MCP server
    server_params = StdioServerParameters(
        command="python",
        args=["server.py"]
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize
            await session.initialize()

            # List available tools
            tools_list = await session.list_tools()

            # Convert to Claude tool format
            claude_tools = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema
                }
                for tool in tools_list.tools
            ]

            # Now use with Claude
            client = anthropic.Anthropic()

            messages = [{
                "role": "user",
                "content": "Verify transaction: {...}"
            }]

            # Agentic loop
            while True:
                response = client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=4096,
                    tools=claude_tools,
                    messages=messages
                )

                if response.stop_reason == "tool_use":
                    tool_uses = [
                        b for b in response.content
                        if b.type == "tool_use"
                    ]

                    # Execute tools via MCP
                    tool_results = []
                    for tool_use in tool_uses:
                        result = await session.call_tool(
                            tool_use.name,
                            tool_use.input
                        )

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": result.content
                        })

                    # Continue loop
                    messages.append({
                        "role": "assistant",
                        "content": response.content
                    })
                    messages.append({
                        "role": "user",
                        "content": tool_results
                    })
                else:
                    # Done
                    break

            return response

# Run
import asyncio
result = asyncio.run(run_with_mcp())
```

### Pros
✅ **Standardized** - MCP is an industry standard
✅ **Modular** - Tools can be separate services
✅ **Reusable** - Same tools work with any MCP client
✅ **Remote-capable** - Tools can run on different machines
✅ **Discovery** - Tools self-describe their capabilities

### Cons
❌ **Complexity** - More moving parts
❌ **Async** - Requires async programming
❌ **Overhead** - IPC communication overhead
❌ **Debugging** - Harder to debug across process boundaries

---

## Approach 3: Hybrid - Native + MCP

### Best of Both Worlds

```python
class HybridToolAgent:
    """
    Use native tool use for orchestration,
    but support both local and MCP tools.
    """

    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.local_tools = {}
        self.mcp_sessions = {}
        self.all_tools = []

    def register_local_tool(self, name: str, function: Callable, schema: Dict):
        """Register a local Python function as a tool."""
        self.local_tools[name] = function
        self.all_tools.append({
            "name": name,
            "description": schema["description"],
            "input_schema": schema["input_schema"],
            "source": "local"
        })

    async def register_mcp_server(self, server_params: StdioServerParameters):
        """Connect to an MCP server and register its tools."""
        async with stdio_client(server_params) as (read, write):
            session = ClientSession(read, write)
            await session.initialize()

            # Get tools from MCP server
            tools_list = await session.list_tools()

            for tool in tools_list.tools:
                self.all_tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema,
                    "source": "mcp"
                })

            # Keep session alive
            self.mcp_sessions[server_params.command] = session

    async def execute_tool(self, tool_name: str, tool_input: Dict) -> any:
        """Execute tool (local or MCP)."""
        # Find tool
        tool_info = next(
            (t for t in self.all_tools if t["name"] == tool_name),
            None
        )

        if not tool_info:
            raise ValueError(f"Unknown tool: {tool_name}")

        if tool_info["source"] == "local":
            # Execute locally
            return self.local_tools[tool_name](**tool_input)

        elif tool_info["source"] == "mcp":
            # Execute via MCP
            for session in self.mcp_sessions.values():
                try:
                    result = await session.call_tool(tool_name, tool_input)
                    return json.loads(result.content[0].text)
                except:
                    continue

            raise ValueError(f"Tool {tool_name} not found in MCP servers")

    async def run(self, user_message: str, system_prompt: str = "") -> Dict:
        """Run with hybrid tool execution."""
        messages = [{"role": "user", "content": user_message}]

        for _ in range(10):
            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=4096,
                system=system_prompt,
                tools=self.all_tools,
                messages=messages
            )

            if response.stop_reason == "tool_use":
                tool_uses = [
                    b for b in response.content if b.type == "tool_use"
                ]

                tool_results = []
                for tool_use in tool_uses:
                    # Execute (local or MCP)
                    result = await self.execute_tool(
                        tool_use.name,
                        tool_use.input
                    )

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": json.dumps(result)
                    })

                messages.append({
                    "role": "assistant",
                    "content": response.content
                })
                messages.append({
                    "role": "user",
                    "content": tool_results
                })
            else:
                break

        return response


# Usage - Mix local and MCP tools
agent = HybridToolAgent(api_key="your-key")

# Register local tools (fast, no IPC)
agent.register_local_tool(
    name="calculate_expected_fees",
    function=calculate_expected_fees,
    schema={...}
)

# Register MCP tools (can be remote)
await agent.register_mcp_server(
    StdioServerParameters(
        command="python",
        args=["contract_loader_server.py"]
    )
)

# Run agent (uses both local and MCP tools transparently)
result = await agent.run("Verify transaction: {...}")
```

---

## Approach 4: Framework-Based (LangChain, etc.)

### Using LangChain

```python
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool

# Define tools
@tool
def calculate_expected_fees(
    amount: float,
    wl_rate: float,
    fixed_fee: float
) -> dict:
    """Calculate expected fees based on contract rule."""
    percentage_fee = amount * wl_rate
    total = percentage_fee + fixed_fee
    return {"total": total, "breakdown": {...}}

# Create agent
llm = ChatAnthropic(model="claude-sonnet-4-5-20250929")
tools = [calculate_expected_fees, compare_fees, ...]
agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools)

# Run
result = agent_executor.invoke({
    "input": "Verify transaction: {...}"
})
```

### Pros
✅ **Battle-tested** - Framework handles edge cases
✅ **Rich ecosystem** - Many pre-built integrations
✅ **Abstractions** - Don't worry about low-level details

### Cons
❌ **Heavy** - Large dependency
❌ **Opinionated** - Framework way or highway
❌ **Overhead** - More abstraction layers
❌ **Updates** - Framework changes can break things

---

## Recommendation for Transaction Verification

### **Approach: Hybrid Native + MCP**

```
┌─────────────────────────────────────────────────────┐
│          Your Application                            │
│  ┌──────────────────────────────────────────────┐  │
│  │   Native Tool Agent (orchestrator)            │  │
│  │   • Handles Claude API                        │  │
│  │   • Manages conversation                      │  │
│  │   • Routes tools                              │  │
│  └──────────────┬───────────────────────────────┘  │
│                 │                                    │
│                 ├──────────┬──────────┬─────────┐  │
│                 ▼          ▼          ▼         ▼  │
│  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐  │
│  │ Local  │  │ Local  │  │  MCP   │  │  MCP   │  │
│  │ Tool 1 │  │ Tool 2 │  │ Tool 3 │  │ Tool 4 │  │
│  │        │  │        │  │        │  │        │  │
│  │ Fast   │  │ Simple │  │Complex │  │Remote  │  │
│  │ Calc   │  │ Logic  │  │ Data   │  │ API    │  │
│  └────────┘  └────────┘  └────────┘  └────────┘  │
└─────────────────────────────────────────────────────┘
```

### **Guidelines**

**Use Local Tools For:**
- Fast calculations (fee calculations)
- Simple data transformations (field mapping)
- In-memory operations (caching)
- Performance-critical paths

**Use MCP Tools For:**
- Data loading (file I/O)
- External API calls (currency conversion)
- Complex operations (ML inference)
- Shared services (multiple agents)

### **Implementation Strategy**

```python
# Phase 1: Start with Native (Simple)
agent = NativeToolAgent(api_key="...")
agent.register_tool("calculate_fees", calculate_expected_fees, schema)
agent.register_tool("compare_fees", compare_fees, schema)

# Phase 2: Add MCP for data loading (Modularity)
# Move file I/O to MCP server
mcp_server = FastMCP("data-loader")
@mcp_server.tool()
def load_contract_data(file_path: str):
    ...

# Phase 3: Optimize (Performance)
# Keep hot-path calculations local
# Move cold-path operations to MCP
```

---

## Performance Comparison

| Approach | Latency | Complexity | Flexibility | Cost |
|----------|---------|------------|-------------|------|
| Native | ⚡ Low | 🟢 Low | 🟡 Medium | 💰 Low |
| MCP Only | 🐢 Medium | 🔴 High | 🟢 High | 💰 Medium |
| Hybrid | ⚡ Low | 🟡 Medium | 🟢 High | 💰 Low |
| Framework | 🐢 Medium | 🟢 Low | 🔴 Low | 💰 High |

---

## Production Considerations

### 1. Observability

```python
class ObservableToolAgent(NativeToolAgent):
    """Agent with built-in observability."""

    def execute_tool(self, tool_name: str, tool_input: Dict) -> any:
        import time

        start = time.time()
        try:
            result = super().execute_tool(tool_name, tool_input)
            duration = time.time() - start

            # Log to your observability platform
            logger.info("tool_execution", extra={
                "tool": tool_name,
                "duration_ms": duration * 1000,
                "success": True,
                "input_size": len(json.dumps(tool_input))
            })

            return result

        except Exception as e:
            duration = time.time() - start
            logger.error("tool_execution_error", extra={
                "tool": tool_name,
                "duration_ms": duration * 1000,
                "error": str(e)
            })
            raise
```

### 2. Caching

```python
from functools import lru_cache

class CachedToolAgent(NativeToolAgent):
    """Agent with tool result caching."""

    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.cache = {}

    def execute_tool(self, tool_name: str, tool_input: Dict) -> any:
        # Generate cache key
        cache_key = (tool_name, json.dumps(tool_input, sort_keys=True))

        # Check cache
        if cache_key in self.cache:
            logger.info(f"Cache hit for {tool_name}")
            return self.cache[cache_key]

        # Execute and cache
        result = super().execute_tool(tool_name, tool_input)
        self.cache[cache_key] = result

        return result
```

### 3. Error Handling

```python
def execute_tool_with_retry(
    self,
    tool_name: str,
    tool_input: Dict,
    max_retries: int = 3
) -> any:
    """Execute tool with retry logic."""

    for attempt in range(max_retries):
        try:
            return self.execute_tool(tool_name, tool_input)

        except RetryableError as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(f"Tool {tool_name} failed, retrying in {wait_time}s")
                time.sleep(wait_time)
            else:
                raise

        except NonRetryableError as e:
            logger.error(f"Tool {tool_name} failed permanently: {e}")
            raise
```

---

## Summary

### For Transaction Verification Agent:

**Recommended: Hybrid Native + MCP**

**Start with:**
1. Native tool use for orchestration
2. Local Python functions for calculations
3. Consider MCP later for modularity

**Code Structure:**
```
agent/
├── core/
│   ├── native_agent.py      # Main agent using Claude API
│   └── tool_registry.py     # Tool management
├── tools/
│   ├── local/
│   │   ├── calculator.py    # Fast local tools
│   │   └── validator.py
│   └── mcp/
│       └── data_loader.py   # MCP server for file I/O
└── main.py
```

**Benefits:**
- Start simple, scale when needed
- Performance where it matters
- Flexibility for future needs
- Standard protocols (MCP)
- Full control over orchestration
