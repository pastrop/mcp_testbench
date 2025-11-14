"""
MCP Server for Text-to-SQL Agent

Exposes the agent's functionality through FastMCP tools.
"""

from mcp.server.fastmcp import FastMCP
from agent import TextToSQLAgent
from typing import Optional
import json


# Initialize FastMCP server
mcp = FastMCP("text-to-sql-agent")

# Global agent instance
agent: Optional[TextToSQLAgent] = None


@mcp.tool()
def initialize_schema(
    schema_path: str = "schema.json",
    table_name: str = "transactions"
) -> str:
    """
    Initialize the text-to-SQL agent with a schema file.

    Args:
        schema_path: Path to the schema JSON file (default: schema.json)
        table_name: Name of the table to query (default: transactions)

    Returns:
        JSON string with initialization results including any ambiguities found
    """
    global agent

    agent = TextToSQLAgent(schema_path=schema_path, table_name=table_name)
    result = agent.initialize()

    return json.dumps(result, indent=2)


@mcp.tool()
def get_schema_summary() -> str:
    """
    Get a summary of the currently loaded schema.

    Returns:
        JSON string with schema summary including column counts by type
    """
    global agent

    if agent is None:
        return json.dumps({"error": "Agent not initialized. Call initialize_schema first."})

    summary = agent.get_schema_summary()
    return json.dumps(summary, indent=2)


@mcp.tool()
def get_ambiguities() -> str:
    """
    Get a list of detected ambiguities in the schema that may need clarification.

    Returns:
        JSON string with list of ambiguities and affected columns
    """
    global agent

    if agent is None:
        return json.dumps({"error": "Agent not initialized. Call initialize_schema first."})

    ambiguities = agent.get_ambiguities_for_review()
    return json.dumps(ambiguities, indent=2)


@mcp.tool()
def add_clarification(column_name: str, clarification: str) -> str:
    """
    Add a user clarification for a specific column to improve query translation.

    Args:
        column_name: Name of the column to clarify
        clarification: Clarification text explaining the column's meaning or usage

    Returns:
        JSON string confirming the clarification was added
    """
    global agent

    if agent is None:
        return json.dumps({"error": "Agent not initialized. Call initialize_schema first."})

    try:
        agent.add_clarification(column_name, clarification)
        return json.dumps({
            "success": True,
            "message": f"Clarification added for column '{column_name}'",
            "column": column_name,
            "clarification": clarification
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        }, indent=2)


@mcp.tool()
def translate_to_sql(query: str) -> str:
    """
    Translate a natural language query to GoogleSQL.

    Args:
        query: Natural language question about the data

    Returns:
        JSON string with the generated SQL query, explanation, confidence level, and any warnings
    """
    global agent

    if agent is None:
        return json.dumps({"error": "Agent not initialized. Call initialize_schema first."})

    result = agent.process_query_with_feedback(query)
    return json.dumps(result, indent=2)


@mcp.tool()
def search_columns(search_term: str) -> str:
    """
    Search for columns in the schema by name or description.

    Args:
        search_term: Term to search for in column names and descriptions

    Returns:
        JSON string with matching columns and their details
    """
    global agent

    if agent is None:
        return json.dumps({"error": "Agent not initialized. Call initialize_schema first."})

    columns = agent.schema_manager.search_columns(search_term)

    results = []
    for col in columns:
        results.append({
            "name": col.name,
            "type": col.type,
            "short_description": col.short_description,
            "detailed_description": col.detailed_description
        })

    return json.dumps({
        "search_term": search_term,
        "matches": len(results),
        "columns": results
    }, indent=2)


@mcp.tool()
def save_schema_with_clarifications(output_path: str = "schema_clarified.json") -> str:
    """
    Save the schema with all user clarifications to a new JSON file.

    Args:
        output_path: Path where the clarified schema should be saved

    Returns:
        JSON string confirming the save operation
    """
    global agent

    if agent is None:
        return json.dumps({"error": "Agent not initialized. Call initialize_schema first."})

    try:
        agent.save_clarifications(output_path)
        return json.dumps({
            "success": True,
            "message": f"Schema with clarifications saved to {output_path}",
            "clarifications_count": len(agent.schema_manager.clarifications)
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        }, indent=2)


@mcp.tool()
def validate_sql(sql_query: str) -> str:
    """
    Validate a SQL query for basic correctness and safety.

    Args:
        sql_query: SQL query to validate

    Returns:
        JSON string with validation results including any errors or warnings
    """
    global agent

    if agent is None:
        return json.dumps({"error": "Agent not initialized. Call initialize_schema first."})

    validation = agent.query_translator.validate_query(sql_query)
    return json.dumps(validation, indent=2)


# Resource to expose the schema
@mcp.resource("schema://current")
def get_current_schema() -> str:
    """
    Get the current schema with all clarifications.

    Returns:
        The enriched schema description as a string
    """
    global agent

    if agent is None:
        return "Error: Agent not initialized. Call initialize_schema first."

    return agent.schema_manager.get_enriched_schema_description()


if __name__ == "__main__":
    # Run the MCP server
    mcp.run()
