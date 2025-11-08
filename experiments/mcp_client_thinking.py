
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
            
    async def connect(self):
        """Connect to both MCP servers"""
        print('CONNECTING TO THE SERVERS')
        # Connect to sequential thinking server
        thinking_server_params = StdioServerParameters(
            command=self.thinking_server_command,
            args=self.thinking_server_args
        )
    
        async with stdio_client(thinking_server_params) as thinking_client:
            self.thinking_client = thinking_client


        # Connect to local tools server
        local_server_params = StdioServerParameters(
            #command="python",
            command="uv",
            args=['run',self.local_server_path]
        )
        
        async with stdio_client(local_server_params) as stdio_transport:
            read, write = stdio_transport
            async with ClientSession(read, write) as session:
                self.local_tools_session = session
                await self.local_tools_session.initialize()        


                local_response = await self.local_tools_session.list_tools()
                #local_tools=[]
                for tool in local_response.tools:
                    self.local_tools.append({
                                "name": tool.name,
                                "description": tool.description,
                                "input_schema": tool.inputSchema
                            })

        print(f'line 79: Available Local Tools: {self.local_tools}')

        
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
    
    async def select_tools_and_answer(self, query: str, analysis: Dict[str, Any], 
                                     selected_context: List[str]) -> str:
        """Step 3: Select appropriate tools and produce final answer"""
        print('LINE 178 - SELECT TOOLS AND ANSWER')
        # Get available tools from local MCP server
        try:
            tools_response = await self.local_tools_session.list_tools()
            tools = tools_response.tools if tools_response else []
        except:
            tools = []
        print(f"\n**** Line 185 Tools available: {tools}")

        # Convert MCP Tool objects to Anthropic API format
        anthropic_tools = []
        for tool in tools:  # mcp_tools.tools contains the list of Tool objects
            anthropic_tool = {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema  # This is already a dict/JSON Schema
            }
            anthropic_tools.append(anthropic_tool)


        final_prompt = f"""
        Original query: {query}
        
        Analysis: {json.dumps(analysis)}
        
        Selected context:
        {chr(10).join(selected_context)}
        
        Available tools: {[tool.name for tool in tools]}
        
        Provide a comprehensive answer to the query using the context and tools available.
        """
        
        print("\n" + "="*50)
        print(f'LINE 198 final_prompt:{final_prompt}')
        print("="*50)

        try:
            response = await self.thinking_session.call_tool("sequential_thinking", {
                "thought": final_prompt,
                "nextThoughtNeeded": False,
                "thoughtNumber": 3,
                "totalThoughts": 3
            })
            
            if isinstance(response, str):
                return response
            else:
                return response.get("answer", "Unable to generate response")
                
        except Exception as e:
            # Fallback to Claude
            claude_response = self.claude_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                messages=[{"role": "user", "content": final_prompt}]
            )
            return claude_response.content[0].text

    async def get_local_tools(self) -> List[Dict[str, Any]]:
        """Get available tools from the local MCP server"""
        try:
            tools_response = await self.local_tools_session.list_tools()
            return tools_response.tools if tools_response else []
        except Exception as e:
            print(f"Error getting local tools: {e}")
            return []

    
    async def process_query(self, query: str, text_corpus: List[str] = None) -> Dict[str, Any]:
        """Main method to process a query through all 3 steps"""
        if text_corpus:
            self.text_corpus = text_corpus
            
        # Step 1: Analyze query
        print("Step 1: Analyzing query...")
        analysis = await self.analyze_query(query)
        
        # Step 2: Select context
        #print("Step 2: Selecting relevant context...")
        #selected_context = await self.select_context(analysis, self.text_corpus)
        
        # Step 3: Generate final answer
        #print("Step 3: Generating final answer...")
        #final_answer = await self.select_tools_and_answer(query, analysis, selected_context)
        
        return {
            "query": query,
            "analysis": analysis,
            #"selected_context": selected_context,
            #"final_answer": final_answer
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
            #tools = await client.get_local_tools()
            tools = client.local_tools
            print(f"print in line 288 - Available local tools: {tools}")

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