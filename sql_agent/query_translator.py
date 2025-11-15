"""
Query Translator Module

Translates natural language queries to GoogleSQL using Claude API.
"""

import os
import re
from typing import Optional, Dict, Any
from anthropic import Anthropic


class QueryTranslator:
    """Translates natural language queries to SQL using Claude."""

    def __init__(self, model: str = "claude-sonnet-4-5-20250929"):
        """
        Initialize the query translator.

        Args:
            model: The Claude model to use. Default is Claude Sonnet 4.5
                   which excels at complex reasoning and SQL generation.
        """
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")

        self.client = Anthropic(api_key=api_key)
        self.model = model

    def translate(
        self,
        natural_language_query: str,
        schema_description: str,
        table_name: str = "transactions"
    ) -> Dict[str, Any]:
        """
        Translate a natural language query to GoogleSQL.

        Args:
            natural_language_query: The user's question in natural language
            schema_description: Detailed schema description including clarifications
            table_name: Name of the table to query

        Returns:
            Dictionary containing:
                - sql: The generated SQL query
                - explanation: Explanation of what the query does
                - confidence: Confidence level (high/medium/low)
                - warnings: Any warnings or caveats
        """
        system_prompt = self._build_system_prompt(schema_description, table_name)
        user_prompt = self._build_user_prompt(natural_language_query)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                temperature=0,  # Use 0 for deterministic SQL generation
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )

            # Parse the response
            result = self._parse_response(response.content[0].text)
            return result

        except Exception as e:
            return {
                "sql": None,
                "explanation": f"Error generating SQL: {str(e)}",
                "confidence": "low",
                "warnings": [str(e)],
                "error": True
            }

    def _build_system_prompt(self, schema_description: str, table_name: str) -> str:
        """Build the system prompt for Claude."""
        return f"""You are an expert SQL query generator specializing in GoogleSQL (BigQuery SQL dialect).

Your task is to convert natural language questions into executable GoogleSQL queries.

IMPORTANT GUIDELINES:
1. Generate ONLY GoogleSQL-compatible queries (BigQuery dialect)
2. The database has a SINGLE table named '{table_name}' - NEVER use JOINs
3. Use proper GoogleSQL syntax for dates, timestamps, and functions
4. Always use appropriate aggregations when needed
5. Handle NULL values appropriately
6. Use GoogleSQL-specific functions like FORMAT_DATE, TIMESTAMP_TRUNC, etc.
7. For date/time operations, use GoogleSQL date functions
8. Return results in a clear, logical order using ORDER BY when appropriate
9. Use LIMIT when the query might return many rows

RESPONSE FORMAT:
You must respond in the following format:

SQL:
```sql
[Your SQL query here]
```

EXPLANATION:
[A clear explanation of what the query does and why you made certain choices]

CONFIDENCE: [high/medium/low]

WARNINGS:
[Any caveats, assumptions, or potential issues the user should know about]

{schema_description}

Remember: You are working with GoogleSQL (BigQuery) syntax, not standard SQL or MySQL or PostgreSQL.
"""

    def _build_user_prompt(self, natural_language_query: str) -> str:
        """Build the user prompt."""
        return f"""Convert the following natural language question into a GoogleSQL query:

QUESTION: {natural_language_query}

Generate the SQL query following the format specified in the system prompt.
"""

    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse Claude's response into structured format."""
        result = {
            "sql": None,
            "explanation": "",
            "confidence": "medium",
            "warnings": [],
            "error": False
        }

        lines = response_text.split('\n')
        current_section = None
        sql_lines = []
        explanation_lines = []
        warning_lines = []

        for line in lines:
            line_upper = line.strip().upper()

            if line_upper.startswith('SQL:'):
                current_section = 'sql'
                continue
            elif line_upper.startswith('EXPLANATION:'):
                current_section = 'explanation'
                continue
            elif line_upper.startswith('CONFIDENCE:'):
                current_section = 'confidence'
                confidence_text = line.split(':', 1)[1].strip().lower()
                if confidence_text in ['high', 'medium', 'low']:
                    result['confidence'] = confidence_text
                continue
            elif line_upper.startswith('WARNINGS:'):
                current_section = 'warnings'
                continue

            # Collect lines for current section
            if current_section == 'sql':
                # Skip markdown code blocks
                if line.strip() not in ['```sql', '```']:
                    sql_lines.append(line)
            elif current_section == 'explanation':
                if line.strip():
                    explanation_lines.append(line.strip())
            elif current_section == 'warnings':
                if line.strip() and not line.strip().startswith('-'):
                    warning_lines.append(line.strip())
                elif line.strip().startswith('-'):
                    warning_lines.append(line.strip()[1:].strip())

        # Assemble results
        result['sql'] = '\n'.join(sql_lines).strip()
        result['explanation'] = ' '.join(explanation_lines)
        result['warnings'] = [w for w in warning_lines if w]

        # Validate SQL was generated
        if not result['sql']:
            result['error'] = True
            result['explanation'] = "Failed to generate SQL query"
            result['confidence'] = "low"

        return result

    def validate_query(self, sql_query: str) -> Dict[str, Any]:
        """
        Perform basic validation on the generated SQL query.

        Args:
            sql_query: The SQL query to validate

        Returns:
            Dictionary with validation results
        """
        validation = {
            "valid": True,
            "errors": [],
            "warnings": []
        }

        sql_upper = sql_query.upper()

        # Check for JOINs (should not be present)
        # Use word boundary to avoid false positives like "DISJOINT"
        if re.search(r'\bJOIN\b', sql_upper):
            validation["errors"].append("Query contains JOIN - only single table queries are allowed")
            validation["valid"] = False

        # Check for destructive operations using word boundaries
        # This prevents false positives like "CREATE" in "TIMESTAMP_TRUNC"
        destructive_ops = ['DROP', 'DELETE', 'TRUNCATE', 'ALTER', 'CREATE']
        for op in destructive_ops:
            if re.search(rf'\b{op}\b', sql_upper):
                validation["errors"].append(f"Destructive operation {op} not allowed")
                validation["valid"] = False

        # Check if it starts with SELECT
        if not sql_upper.strip().startswith('SELECT'):
            validation["warnings"].append("Query does not start with SELECT")

        # Check for basic SQL injection patterns
        suspicious_patterns = ['--', '/*', '*/', ';']
        for pattern in suspicious_patterns:
            if pattern in sql_query and not (pattern == ';' and sql_query.strip().endswith(';')):
                validation["warnings"].append(f"Suspicious pattern found: {pattern}")

        return validation

    def rebuild_query(
        self,
        natural_language_query: str,
        failed_sql: str,
        validation_errors: list,
        schema_description: str,
        table_name: str = "transactions"
    ) -> Dict[str, Any]:
        """
        Rebuild a query that failed validation.

        Args:
            natural_language_query: Original user question
            failed_sql: The SQL that failed validation
            validation_errors: List of validation error messages
            schema_description: Schema description
            table_name: Table name

        Returns:
            Dictionary with rebuilt query result
        """
        # Build a specific prompt for query rebuilding
        rebuild_prompt = f"""The following SQL query failed validation. Please fix it according to the constraints.

ORIGINAL QUESTION: {natural_language_query}

FAILED SQL:
```sql
{failed_sql}
```

VALIDATION ERRORS:
{chr(10).join(f"- {error}" for error in validation_errors)}

CONSTRAINTS YOU MUST FOLLOW:
1. NO JOIN operations - this is a SINGLE TABLE query only
2. NO destructive operations (DROP, DELETE, TRUNCATE, ALTER, CREATE statements)
3. Query must start with SELECT
4. Use GoogleSQL (BigQuery) syntax only

Please rewrite the SQL query to satisfy these constraints while still answering the original question.
If the question REQUIRES a JOIN (multiple tables), explain that it cannot be answered with a single table.

Return your response in the same format as before:
SQL:
```sql
[Fixed query here]
```

EXPLANATION:
[Explain what you changed and why]

CONFIDENCE: [high/medium/low]

WARNINGS:
[Any warnings or limitations]
"""

        system_prompt = self._build_system_prompt(schema_description, table_name)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                temperature=0,  # Keep deterministic for fixes
                system=system_prompt,
                messages=[
                    {"role": "user", "content": rebuild_prompt}
                ]
            )

            result = self._parse_response(response.content[0].text)
            result["rebuilt"] = True
            return result

        except Exception as e:
            return {
                "sql": None,
                "explanation": f"Error rebuilding query: {str(e)}",
                "confidence": "low",
                "warnings": [str(e)],
                "error": True,
                "rebuilt": False
            }
