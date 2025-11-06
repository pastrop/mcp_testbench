import asyncio
import json
from typing import Dict, List, Any, Optional
from anthropic import Anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import AsyncExitStack
import os

# Get API key from environment
api_key = os.getenv("CLAUDE_KEY")
if not api_key:
    print("Please set CLAUDE_KEY environment variable")


class SequentialThinkingMCPClient:
    def __init__(self, claude_api_key: str, thinking_server_command: str = "npx", 
                 thinking_server_args: List[str] = ["-y", "@modelcontextprotocol/server-sequential-thinking"],
                 local_server_path: str = "./mcp_server.py"):
        self.claude_client = Anthropic(api_key=api_key)
        self.thinking_session: Optional[ClientSession] = None
        self.local_tools_session: Optional[ClientSession] = None
        self.thinking_server_command = thinking_server_command
        self.thinking_server_args = thinking_server_args
        self.local_server_path = local_server_path
        self.text_corpus = []
        self.exit_stack = AsyncExitStack()
        self.local_tools = []
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()
        await self.exit_stack.aclose()

    '''
    #Template code for loading configs for MCP servers
    def load_server_config(self):
        """Load server configuration from JSON file"""
        try:
            with open('server_config_.json', 'r') as f:
                config = json.load(f)
                print("Loaded server configuration:", config)
                return config.get('mcpServers', {})
        except FileNotFoundError:
            print("server_config_memory.json not found")
            return {}
        except json.JSONDecodeError:
            print("Error parsing server_config_memory.json")
            return {}    
    '''

    async def connect(self):
        """Connect to both MCP servers"""
        print('CONNECTING TO THE SERVERS')
        # Connect to sequential thinking server
        thinking_server_params = StdioServerParameters(
            command=self.thinking_server_command,
            args=self.thinking_server_args
        )

        # Keep thinking client alive using exit_stack
        self.thinking_client = await self.exit_stack.enter_async_context(
            stdio_client(thinking_server_params)
        )

        # Connect to local tools server
        local_server_params = StdioServerParameters(
            #command="python",
            command="uv",
            args=['run',self.local_server_path]
        )
        
        # Keep session alive using exit_stack
        stdio_transport = await self.exit_stack.enter_async_context(
            stdio_client(local_server_params)
        )
        read, write = stdio_transport
        self.local_tools_session = await self.exit_stack.enter_async_context(
            ClientSession(read, write)
        )
        await self.local_tools_session.initialize()


        local_response = await self.local_tools_session.list_tools()
        #local_tools=[]
        for tool in local_response.tools:
            self.local_tools.append({
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.inputSchema
                    })

        #print(f'line 94: Available Local Tools: {self.local_tools}')

        
        print("Connected to Sequential Thinking MCP server and local tools server")
        
    async def disconnect(self):
        """Disconnect from both MCP servers"""
        print("Disconnected from servers")
        
    async def analyze_query(self, query: str) -> Dict[str, Any]:
        """Step 1: Analyze the user query to understand intent and requirements"""
        analysis_prompt = f"""
        Analyze this query and break it down:
        Query: {query}
        
        Please provide:
        1. Intent (what the user wants to accomplish)
        2. Key concepts or topics involved
        3. Information needs (what data/context would be helpful)
        4. Tool needs (what tools would be useful to have access to)
        
        Return as JSON with keys: intent, concepts, information_needs, tools
        """
        
        try:
            response = await self.thinking_session.call_tool("sequential_thinking", {
                "thought": analysis_prompt,
                "nextThoughtNeeded": True,
                "thoughtNumber": 1,
                "totalThoughts": 3
            })
            return response
        except Exception as e:
            # Fallback to Claude if MCP tool unavailable
            claude_response = self.claude_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1000,
                messages=[{"role": "user", "content": analysis_prompt}]
            )
            
            try:
                return json.loads(claude_response.content[0].text)
            except:
                return {
                    "intent": "analyze query",
                    "concepts": [query],
                    "information_needs": ["relevant context"],
                    "output_format": "comprehensive answer"
                }
    
    async def select_context(self, analysis: Dict[str, Any], text_corpus: List[str]) -> List[str]:
        """Step 2: Select relevant context from the text corpus based on analysis"""
        concepts = analysis.get("concepts", [])
        information_needs = analysis.get("information_needs", [])
        
        context_selection_prompt = f"""
        Based on this analysis:
        - Concepts: {concepts}
        - Information needs: {information_needs}
        
        Select the most relevant pieces from this text corpus:
        {json.dumps(text_corpus[:10])}  # Limit for prompt size
        
        Return indices of relevant texts as JSON array.
        """
        
        try:
            response = await self.thinking_session.call_tool("sequential_thinking", {
                "thought": context_selection_prompt,
                "nextThoughtNeeded": True,
                "thoughtNumber": 2,
                "totalThoughts": 3
            })
            
            if isinstance(response, list):
                selected_indices = response
            else:
                selected_indices = response.get("selected_indices", [0, 1, 2])
                
            return [text_corpus[i] for i in selected_indices if i < len(text_corpus)]
            
        except Exception as e:
            # Fallback: select first few relevant items
            return text_corpus[:3] if text_corpus else []
    
    async def select_tools_and_answer(self, query: str, analysis: Dict[str, Any],tools) -> str:
        """Step 3: Select appropriate tools and produce final answer"""
        print('LINE 181 - SELECT TOOLS AND ANSWER')
        # Get available tools from local MCP server

        #print(f"\n**** Line 184 Tools available: {self.local_tools}")

        # Convert MCP Tool objects to Anthropic API format
        anthropic_tools = []
        for tool in tools:  
            anthropic_tool = {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["input_schema"]  # This is already a dict/JSON Schema
            }
            anthropic_tools.append(anthropic_tool)

        print(f"\n**** Line 196 Anthropic Tools available: {anthropic_tools}")

        #Analysis: {json.dumps(analysis)}


        analysis_prompt = f"""
        Analyze this query and break it down:
        Query: {query}
        
        Please provide:
        1. Intent (what the user wants to accomplish)
        2. Key concepts or topics involved
        3. Information needs (what data/context would be helpful)
        4. Tool needs (what tools would be useful to have access to)
        
        Return as JSON with keys: intent, concepts, information_needs, tools
        """

        final_prompt = f"""
        Original query: {query}
        

        
        Provide a comprehensive answer to the query using the context and tools available.
        """
        
        print("\n" + "="*50)
        print(f'LINE 198 final_prompt:{final_prompt}')
        print("="*50)

        claude_response = self.claude_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=2000,
            messages=[{"role": "user", "content": analysis_prompt}]
        )
        print("\n" + "="*50)
        print(f'LINE 218 claude call response-analysis prompt:{claude_response.content[0].text}')
        print("="*50)

        return claude_response.content[0].text
    
    async def process_query(self, query: str, text_corpus: List[str] = None) -> Dict[str, Any]:
        """Main method to process a query through all 3 steps"""
        if text_corpus:
            self.text_corpus = text_corpus
            
        # Step 1: Analyze query (Line 103)
        print("Step 1: Analyzing query...")
        analysis = await self.analyze_query(query)
        
        # Step 2: Select context
        #print("Step 2: Selecting relevant context...")
        #selected_context = await self.select_context(analysis, self.text_corpus)
        
        # Step 3: Generate final answer (Line 179)
        print("Step 3: Generating final answer...")
        final_answer = await self.select_tools_and_answer(query, analysis, self.local_tools)
        
        return {
            "query": query,
            "analysis": analysis,
            #"selected_context": selected_context,
            "final_answer": final_answer
        }


async def main():
    """Example usage of the Sequential Thinking MCP Client"""
    
    
    # Sample text corpus
    sample_corpus = [
        "Machine learning is a subset of artificial intelligence that focuses on algorithms.",
        "Neural networks are inspired by biological neural networks in animal brains.",
        "Deep learning uses multiple layers of neural networks for complex pattern recognition.",
        "Natural language processing helps computers understand and generate human language.",
        "Computer vision enables machines to interpret and understand visual information."
    ]
    
    # Initialize and use client with proper async context management
    async with SequentialThinkingMCPClient(api_key) as client:
        try:
            # Get and display available tools from local server
            tools = client.local_tools
            #print(f"print in line 266 - Available local tools: {tools}")

            # Process a sample query
            query = "What is the relationship between machine learning and neural networks?"
            result = await client.process_query(query, sample_corpus)
            
            print("\n" + "="*50)
            print("QUERY PROCESSING COMPLETE")
            print("="*50)
            print(f"Query: {result['query']}")
            print(f"\nAnalysis: {json.dumps(result['analysis'], indent=2)}")
            #print(f"\nSelected Context: {result['selected_context']}")
            #print(f"\nFinal Answer: {result['final_answer']}")
            
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())