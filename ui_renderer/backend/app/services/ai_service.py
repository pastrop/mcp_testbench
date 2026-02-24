"""AI service for generating UI component specifications using Claude."""

import json
import logging
from typing import Any, Dict

from anthropic import Anthropic
from json_repair import repair_json

logger = logging.getLogger(__name__)

from app.core.config import settings
from app.schemas.component_spec import UIComponentSpec


class AIService:
    """Service for AI-powered UI generation using Claude Haiku."""

    # System prompt defining available components and generation rules
    SYSTEM_PROMPT = """You are a UI specification generator for financial contract data.
Your task is to analyze JSON contract data and generate a structured component specification that describes how to render the data in a user interface.

Available Component Types:
1. Container - Generic container for grouping components
2. Grid - Grid layout (props: columns)
3. Card - Card container with optional title/subtitle
4. Section - Named section with heading
5. Tabs - Tabbed interface (props: tabs array)
6. Accordion - Expandable accordion sections
7. Table - Data table (props: columns array with {key, label} objects, showHeader, sortable)
   IMPORTANT: Table columns MUST use this format: [{"key": "field_name", "label": "Display Name"}]
   CRITICAL: Bind table data using "data" prop name (NOT "rows")
   Example:
   - columns: [{"key": "amount", "label": "Fee Amount"}, {"key": "currency", "label": "Currency"}]
   - data_bindings: {"data": {"path": "fees_and_rates"}}
8. KeyValueList - List of key-value pairs (expects object or array)
   IMPORTANT: Bind entire object to "items" prop - do NOT put data paths inside props.items structure
   Example: data_bindings: {"items": {"path": "payment_terms"}}
   WRONG: props.items with nested {"path": "..."} objects
9. BadgeList - List of badges/tags
10. MetricCard - Single metric display with label and value
11. FeeCard - Specialized card for displaying fee information
12. TieredPricing - Display tiered pricing structures
13. Heading - Text heading (props: level 1-6)
14. Text - Plain text display
15. Label - Small label text

Data Binding:
- Use the "data_bindings" field to map component props to JSON paths
- Example: {"value": {"path": "fees_and_rates[0].amount"}}
- Paths use dot notation for nested objects and bracket notation for arrays
- Apply transforms like "formatCurrency", "formatPercentage", "formatDate" when appropriate

Component Selection Guidelines:
- Use FeeCard for individual fee items from "fees_and_rates" arrays
- Use Table for arrays of similar structured objects
- Use KeyValueList for simple object properties
- Use TieredPricing for pricing structures with tiers
- Use Tabs or Accordion to organize multiple sections
- Use MetricCard for important standalone values
- Use BadgeList for arrays of simple strings (like currencies, regions)
- Always include a Section or Card as a container for related data

Style Guidelines:
- Use appropriate color variants: "success" for positive, "warning" for conditions, "error" for fees/charges
- Size options: "small", "medium", "large"

Output Format:
Generate a valid JSON object matching the UIComponentSpec schema with:
- contract_id: identifier from filename
- title: human-readable title
- description: brief description
- components: array of component specifications
- metadata: any relevant metadata

Be intelligent about data organization:
- Group related fees together
- Highlight important information (like document info, payment terms)
- Use appropriate visualizations for the data type
- Create a clear hierarchy"""

    def __init__(self):
        """Initialize the AI service with Anthropic client."""
        self.client = Anthropic(api_key=settings.anthropic_api_key)

    def _repair_json(self, json_str: str) -> str:
        """
        Attempt to repair common JSON syntax errors using json_repair library.

        Args:
            json_str: Malformed JSON string

        Returns:
            Repaired JSON string
        """
        try:
            # Use json_repair library for robust JSON fixing
            return repair_json(json_str)
        except Exception as e:
            logger.warning(f"json_repair failed: {e}, falling back to regex repair")

            # Fallback to simple regex repair
            import re
            json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
            json_str = re.sub(r'//.*?$', '', json_str, flags=re.MULTILINE)
            json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
            return json_str

    async def generate_ui_spec(
        self, contract_data: Dict[str, Any], filename: str
    ) -> UIComponentSpec:
        """
        Generate UI component specification from contract data using Claude Haiku.

        Args:
            contract_data: The parsed contract JSON data
            filename: The contract filename for identification

        Returns:
            UIComponentSpec with generated component structure

        Raises:
            ValueError: If AI generation fails or returns invalid JSON
        """
        # Prepare the user prompt with contract data
        user_prompt = f"""Generate a UI component specification for this financial contract data:

Filename: {filename}

Contract Data:
{json.dumps(contract_data, indent=2)}

Analyze the structure and content, then generate a comprehensive UIComponentSpec JSON that:
1. Organizes the data into logical sections
2. Uses appropriate components for each data type
3. Binds data correctly using JSON paths
4. Applies proper styling and formatting
5. Creates an intuitive, user-friendly layout

Return ONLY the JSON specification, no additional text."""

        try:
            # Call Claude Haiku for generation with prefill
            message = self.client.messages.create(
                model="claude-haiku-4-5-20251001",  # Use Haiku 4.5
                max_tokens=4096,
                system=self.SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": "{"}  # Prefill to force JSON
                ],
                temperature=0.3,  # Lower temperature for more consistent output
            )

            # Extract the response text and prepend the prefill
            response_text = message.content[0].text.strip()

            # Add back the opening brace from prefill
            if not response_text.startswith("{"):
                response_text = "{" + response_text

            # Debug: Log the response
            logger.debug(f"AI response length: {len(response_text)}")
            logger.debug(f"AI response preview: {response_text[:200]}...")

            # Parse JSON response (handle markdown code blocks)
            if response_text.startswith("```"):
                # Remove markdown code fence (```json ... ``` or ``` ... ```)
                lines = response_text.split("\n")
                # Remove first line (```json or ```) and last line (```)
                if len(lines) >= 3:
                    response_text = "\n".join(lines[1:-1])
                response_text = response_text.strip()

            # Try to parse JSON, with repair attempt if it fails
            try:
                spec_dict = json.loads(response_text)
            except json.JSONDecodeError as first_error:
                # Attempt to fix common JSON issues
                logger.warning(f"Initial JSON parse failed, attempting repair: {first_error}")
                cleaned_json = self._repair_json(response_text)

                # json_repair returns a string, parse it
                try:
                    spec_dict = json.loads(cleaned_json)
                    logger.info("JSON repair successful")
                except json.JSONDecodeError as repair_error:
                    # If repair fails, log both errors and raise the original
                    logger.error(f"JSON repair also failed: {repair_error}")
                    logger.error(f"Repaired JSON preview: {cleaned_json[:200]}...")
                    raise first_error

            # Validate and convert to Pydantic model
            ui_spec = UIComponentSpec(**spec_dict)

            return ui_spec

        except json.JSONDecodeError as e:
            # Log the problematic JSON for debugging
            logger.error(f"JSON decode error at line {e.lineno} col {e.colno}: {e.msg}")
            logger.error(f"Context around error: ...{response_text[max(0, e.pos-100):e.pos+100]}...")
            raise ValueError(f"AI returned invalid JSON at line {e.lineno}: {e.msg}")
        except Exception as e:
            raise ValueError(f"Failed to generate UI specification: {e}")

    def generate_ui_spec_sync(
        self, contract_data: Dict[str, Any], filename: str
    ) -> UIComponentSpec:
        """
        Generate UI spec using Claude's structured output (tool use) - 100% reliable.

        Args:
            contract_data: The parsed contract JSON data
            filename: The contract filename for identification

        Returns:
            UIComponentSpec with generated component structure
        """
        # Define the tool schema for structured output with proper enum constraints
        tools = [
            {
                "name": "create_ui_spec",
                "description": "Create a UI component specification for displaying contract data",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Human-readable title for the contract"},
                        "description": {"type": "string", "description": "Brief description of the contract"},
                        "contract_id": {"type": "string", "description": "Contract identifier/filename"},
                        "components": {
                            "type": "array",
                            "description": "List of UI components to display the contract data",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "enum": [
                                            "Container", "Grid", "Card", "Section", "Tabs", "Accordion",
                                            "Table", "KeyValueList", "BadgeList", "MetricCard", "FeeCard", "TieredPricing",
                                            "Heading", "Text", "Label", "Chart", "ProgressBar"
                                        ],
                                        "description": "Component type - MUST be one of the allowed enum values"
                                    },
                                    "props": {
                                        "type": "object",
                                        "description": "Static props for the component"
                                    },
                                    "data_bindings": {
                                        "type": "object",
                                        "description": "Dynamic data bindings - each value must have 'path' (required), 'transform' (optional), 'default_value' (optional)",
                                        "additionalProperties": {
                                            "type": "object",
                                            "properties": {
                                                "path": {"type": "string", "description": "JSON path to data (e.g., 'fees_and_rates[0].amount')"},
                                                "transform": {"type": "string", "description": "Optional transform function (e.g., 'formatCurrency')"},
                                                "default_value": {"description": "Default value if path doesn't exist"}
                                            },
                                            "required": ["path"]
                                        }
                                    },
                                    "style": {
                                        "type": "object",
                                        "description": "Styling configuration"
                                    },
                                    "children": {
                                        "type": "array",
                                        "description": "Child components (for nested layouts)",
                                        "items": {"type": "object"}
                                    }
                                },
                                "required": ["type"]
                            }
                        },
                        "metadata": {
                            "type": "object",
                            "description": "Optional metadata about the contract"
                        }
                    },
                    "required": ["title", "description", "contract_id", "components"]
                }
            }
        ]

        user_prompt = f"""Analyze this contract data and create a UI specification.

Contract: {filename}

Data (first 3000 chars):
{json.dumps(contract_data, indent=2)[:3000]}...

IMPORTANT RULES:
1. Component types - use ONLY these exact values:
   - Layout: Container, Grid, Card, Section, Tabs, Accordion
   - Data Display: Table, KeyValueList, BadgeList, MetricCard, FeeCard, TieredPricing
   - Text: Heading, Text, Label
   - Visualization: Chart, ProgressBar

2. Data bindings format - each binding MUST be an object with "path" key:
   CORRECT: {{"data_bindings": {{"value": {{"path": "fees_and_rates[0].amount"}}}}}}
   WRONG: {{"data_bindings": {{"value": "fees_and_rates[0].amount"}}}}

3. Table component columns format - MUST use "key" and "label" properties:
   CORRECT: {{"columns": [{{"key": "amount", "label": "Fee Amount"}}, {{"key": "currency", "label": "Currency"}}]}}
   WRONG: {{"columns": [{{"field": "amount", "header": "Fee Amount"}}]}}

4. Table component data binding - MUST bind array to "data" prop (NOT "rows"):
   CORRECT: {{"data_bindings": {{"data": {{"path": "fees_and_rates"}}}}}}
   WRONG: {{"data_bindings": {{"rows": {{"path": "fees_and_rates"}}}}}}

5. KeyValueList component - bind entire object to "items", do NOT put paths inside props:
   CORRECT: {{"data_bindings": {{"items": {{"path": "payment_terms"}}}}}}
   WRONG: {{"props": {{"items": [{{"label": "X", "value": {{"path": "..."}}}}]}}}}

6. Keep it simple - focus on displaying the key contract information clearly."""

        try:
            # Call Claude with tool use for guaranteed valid JSON
            message = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                tools=tools,
                tool_choice={"type": "tool", "name": "create_ui_spec"},
                messages=[{"role": "user", "content": user_prompt}]
            )

            # Extract tool use response (guaranteed valid JSON from API)
            tool_use = next((block for block in message.content if block.type == "tool_use"), None)

            if not tool_use:
                raise ValueError("No tool use in response")

            spec_dict = tool_use.input
            logger.info(f"✓ Structured output: {len(spec_dict.get('components', []))} components")

            # Validate and convert to Pydantic model
            ui_spec = UIComponentSpec(**spec_dict)
            return ui_spec

        except Exception as e:
            logger.error(f"Structured output generation failed: {e}")
            raise ValueError(f"Failed to generate UI specification: {e}")
