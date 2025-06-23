#from dotenv import load_dotenv
from anthropic import Anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from typing import List, Dict
import asyncio
import nest_asyncio
import os
import json

nest_asyncio.apply()

#load_dotenv()

# Check if the environment variable is set
try:
    api_key = os.environ['CLAUDE_KEY']
    print(f"api_key read")
except KeyError:
    print("API_KEY not found in environment")

class MCP_ChatBot:

    def __init__(self):
        # Initialize session and client objects
        self.sessions: Dict[str, ClientSession] = {}
        self.anthropic = Anthropic(api_key=api_key)
        self.available_tools: List[dict] = []
        self.server_configs = self.load_server_config()
        self.conversation_history: List[Dict] = []

    def load_server_config(self):
        """Load server configuration from JSON file"""
        try:
            with open('server_config_memory.json', 'r') as f:
                config = json.load(f)
                print("Loaded server configuration:", config)
                return config.get('mcpServers', {})
        except FileNotFoundError:
            print("server_config_memory.json not found")
            return {}
        except json.JSONDecodeError:
            print("Error parsing server_config_memory.json")
            return {}

    async def call_tool_on_appropriate_server(self, tool_name, tool_args):
        """Call a tool on the appropriate server based on available tools"""
        for server_name, session in self.sessions.items():
            try:
                result = await session.call_tool(tool_name, arguments=tool_args)
                return result
            except Exception as e:
                # If tool not found on this server, try the next one
                continue
        raise Exception(f"Tool '{tool_name}' not found on any connected server")

    async def process_query(self, query):
        # Add user query to conversation history
        self.conversation_history.append({'role':'user', 'content':query})
        
        # Use complete conversation history for context
        messages = self.conversation_history.copy()
        response = self.anthropic.messages.create(max_tokens = 2024,
                                      model = 'claude-3-7-sonnet-20250219', 
                                      tools = self.available_tools, # tools exposed to the LLM
                                      messages = messages)
        process_query = True
        while process_query:
            assistant_content = []
            for content in response.content:
                if content.type =='text':
                    print(content.text)
                    assistant_content.append(content)
                    if(len(response.content) == 1):
                        # Add assistant response to conversation history
                        self.conversation_history.append({'role':'assistant', 'content':assistant_content})
                        process_query= False
                elif content.type == 'tool_use':
                    assistant_content.append(content)
                    messages.append({'role':'assistant', 'content':assistant_content})
                    tool_id = content.id
                    tool_args = content.input
                    tool_name = content.name
    
                    print(f"Calling tool {tool_name} with args {tool_args}")
                    
                    # Call a tool
                    #result = execute_tool(tool_name, tool_args): not anymore needed
                    # tool invocation through the appropriate client session
                    result = await self.call_tool_on_appropriate_server(tool_name, tool_args)
                    messages.append({"role": "user", 
                                      "content": [
                                          {
                                              "type": "tool_result",
                                              "tool_use_id":tool_id,
                                              "content": result.content
                                          }
                                      ]
                                    })
                    response = self.anthropic.messages.create(max_tokens = 2024,
                                      model = 'claude-3-7-sonnet-20250219', 
                                      tools = self.available_tools,
                                      messages = messages) 
                    
                    if(len(response.content) == 1 and response.content[0].type == "text"):
                        print(response.content[0].text)
                        # Add final assistant response to conversation history
                        self.conversation_history.append({'role':'assistant', 'content':[response.content[0]]})
                        process_query= False

    
    
    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Chatbot Started!")
        print("Type your queries or 'quit' to exit.")
        
        # Load any existing memories and add system message
        if not self.conversation_history:
            # First try to load existing memories
            try:
                memory_result = await self.call_tool_on_appropriate_server('read_graph', {})
                if memory_result.content:
                    memory_context = f"I have some memories from previous conversations: {memory_result.content}"
                    context_message = {
                        'role': 'assistant',
                        'content': [{'type': 'text', 'text': memory_context}]
                    }
                    self.conversation_history.append(context_message)
                    #print(f"Loaded previous memories: {memory_result.content}")
            except:
                pass  # No existing memories or memory server not available
            
            system_message = {
                'role': 'assistant', 
                'content': [{'type': 'text', 'text': 'Hello! I can remember information about you across conversations using my memory tools. When you share personal details, I\'ll automatically store them for future sessions.'}]
            }
            self.conversation_history.append(system_message)
            print(system_message['content'][0]['text'])
        
        while True:
            try:
                query = input("\nQuery: ").strip()
        
                if query.lower() == 'quit':
                    break
                    
                await self.process_query(query)
                print("\n")
                    
            except Exception as e:
                print(f"\nError: {str(e)}")
    
    async def connect_to_servers_and_run(self):
        """Connect to multiple MCP servers and run the chat loop"""
        if not self.server_configs:
            print("No server configurations found")
            return

        connections = []
        
        # Connect to each server
        for server_name, config in self.server_configs.items():
            try:
                server_params = StdioServerParameters(
                    command=config["command"],
                    args=config["args"],
                    env=None,
                )
                
                # Store the connection context for later cleanup
                connection_ctx = stdio_client(server_params)
                connections.append((server_name, connection_ctx))
                
            except Exception as e:
                print(f"Failed to configure server {server_name}: {e}")
        
        # Open all connections
        async def run_with_connections():
            connection_stack = []
            try:
                # Enter all stdio_client contexts
                for server_name, connection_ctx in connections:
                    read, write = await connection_ctx.__aenter__()
                    session_ctx = ClientSession(read, write)
                    session = await session_ctx.__aenter__()
                    connection_stack.append((server_name, connection_ctx, session_ctx, session))
                
                # Initialize all sessions and collect tools
                all_tools = []
                for server_name, _, _, session in connection_stack:
                    try:
                        await session.initialize()
                        response = await session.list_tools()
                        tools = response.tools
                        print(f"\nConnected to {server_name} server with tools:", [tool.name for tool in tools])
                        
                        # Store the session
                        self.sessions[server_name] = session
                        
                        # Add tools to the master list
                        for tool in tools:
                            all_tools.append({
                                "name": tool.name,
                                "description": tool.description,
                                "input_schema": tool.inputSchema
                            })
                    except Exception as e:
                        print(f"Failed to initialize {server_name} server: {e}")
                
                self.available_tools = all_tools
                print(f"\nTotal tools available: {len(all_tools)}")
                
                # Run the chat loop
                await self.chat_loop()
                
            finally:
                # Clean up all connections in reverse order
                for server_name, connection_ctx, session_ctx, session in reversed(connection_stack):
                    try:
                        await session_ctx.__aexit__(None, None, None)
                        await connection_ctx.__aexit__(None, None, None)
                    except Exception as e:
                        print(f"Error closing connection to {server_name}: {e}")
        
        await run_with_connections()


async def main():
    chatbot = MCP_ChatBot()
    await chatbot.connect_to_servers_and_run()
  

if __name__ == "__main__":
    asyncio.run(main())