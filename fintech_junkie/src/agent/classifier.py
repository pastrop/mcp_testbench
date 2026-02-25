"""Query classification for the conversational agent."""

from enum import Enum

import anthropic


class QueryCategory(Enum):
    """Categories for user queries."""

    CONTRACT_INFO = "contract_info"
    TRANSACTION_ANALYSIS = "transaction_analysis"
    COMBINED_ANALYSIS = "combined_analysis"
    OTHER = "other"


CLASSIFICATION_PROMPT = """You are a query classifier for a financial analysis system.

Classify the user's query into ONE of these categories:

1. CONTRACT_INFO - User is asking ONLY about rates, fees, financial terms, or information from a contract.
   Examples:
   - "What are the rates in the Finthesis contract?"
   - "Show me the fees for Skinvault"
   - "What's the rolling reserve for Blogwizarro?"
   - "Tell me about the Webnorus agreement terms"

2. TRANSACTION_ANALYSIS - User wants to ONLY analyze transaction data, identify rate clusters, or understand commission structures from Excel files.
   Examples:
   - "Analyze the Blogwizarro transactions"
   - "What commission rates are in the codedtea file?"
   - "Show me the rate clusters for lingo ventures payouts"
   - "Help me understand the fees in the acquiring report"

3. COMBINED_ANALYSIS - User wants BOTH contract information AND transaction analysis, or wants to compare contractual rates with actual transaction fees.
   Examples:
   - "Give me the contractual fee for vendor X and compare with their transactions"
   - "What's the contractual rate for Blogwizarro and what rates are in their transaction table?"
   - "Compare the contract rates with actual transaction fees for codedtea"
   - "Show me the agreed rates and actual rates for lingo ventures"
   - "Are the transaction fees matching the contract for Finthesis?"

4. OTHER - Anything that doesn't fit the above categories.
   Examples:
   - "Hello"
   - "What can you do?"
   - "How does the weather look?"

Respond with ONLY the category name: CONTRACT_INFO, TRANSACTION_ANALYSIS, COMBINED_ANALYSIS, or OTHER

User query: {query}

Category:"""


def classify_query(client: anthropic.Anthropic, query: str) -> QueryCategory:
    """Classify a user query into one of the predefined categories.

    Args:
        client: Anthropic client instance.
        query: The user's query text.

    Returns:
        The classified QueryCategory.
    """
    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=50,
        messages=[
            {
                "role": "user",
                "content": CLASSIFICATION_PROMPT.format(query=query),
            }
        ],
    )

    # Extract the classification from the response
    classification_text = response.content[0].text.strip().upper()

    # Check for COMBINED first since it contains both "CONTRACT" and "TRANSACTION" keywords
    if "COMBINED" in classification_text:
        return QueryCategory.COMBINED_ANALYSIS
    elif "CONTRACT" in classification_text:
        return QueryCategory.CONTRACT_INFO
    elif "TRANSACTION" in classification_text:
        return QueryCategory.TRANSACTION_ANALYSIS
    else:
        return QueryCategory.OTHER


def get_entity_from_query(client: anthropic.Anthropic, query: str) -> str | None:
    """Extract the entity (contract name or file name) from a query.

    Args:
        client: Anthropic client instance.
        query: The user's query text.

    Returns:
        The extracted entity name, or None if not found.
    """
    extraction_prompt = """Extract the company name, contract name, or file name from this query.
Return ONLY the name, nothing else. If no specific name is mentioned, return "NONE".

Examples:
- "What are the rates in the Finthesis contract?" → Finthesis
- "Analyze Blogwizarro transactions" → Blogwizarro
- "Show me codedtea fees" → codedtea
- "What can you do?" → NONE

Query: {query}

Name:"""

    response = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=50,
        messages=[
            {
                "role": "user",
                "content": extraction_prompt.format(query=query),
            }
        ],
    )

    entity = response.content[0].text.strip()

    if entity.upper() == "NONE":
        return None

    return entity
