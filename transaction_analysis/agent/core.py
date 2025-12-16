"""Main agent orchestrator using Claude API with native tool use."""

import anthropic
import json
import logging
from typing import Dict, List, Optional, Callable
from agent.tools.data_loader import load_contract_data, load_transaction_data
from agent.tools.field_mapper import extract_transaction_characteristics, infer_payment_method
from agent.tools.contract_matcher import find_applicable_contract_rule
from agent.tools.fee_calculator import calculate_expected_fees, compare_fees, calculate_confidence_score
from agent.tools.report_generator import generate_text_report

logger = logging.getLogger(__name__)


# System prompt for the agent
SYSTEM_PROMPT = """You are a transaction fee verification agent. Your task is to verify that transaction fees charged match the contractual terms defined in a contract JSON file.

## Your Responsibilities

For each transaction, you must:

1. **Extract characteristics**: Identify currency, payment method, region, amount, etc.
2. **Find contract rule**: Match transaction to applicable contract terms
3. **Calculate expected fee**: Apply contract formula to determine correct fee
4. **Compare fees**: Check if actual fee matches expected fee (within 0.01 tolerance)
5. **Report discrepancies**: If fees don't match, provide detailed reasoning with confidence score

## Important Guidelines

- **Handle ambiguity**: Document assumptions when field names vary
- **Calculate confidence**: Provide scores (0.0-1.0) based on data quality
- **Be thorough**: Check multiple fields to infer payment methods
- **Explain decisions**: Provide clear reasoning for every determination

## Confidence Scoring

**High (0.8-1.0)**: Exact matches, clear data, single rule
**Medium (0.5-0.79)**: Some inference needed, multiple possible rules
**Low (0.0-0.49)**: High ambiguity, missing data

## Output Format

For discrepancies, provide JSON with:
- transaction_id
- actual_commission
- expected_commission
- discrepancy amount
- status (OVERCHARGED/UNDERCHARGED)
- reasoning (detailed explanation)
- assumptions (list of inferences made)
- confidence (0.0-1.0)
- confidence_reasoning (why this confidence level)

Remember: This is an incomplete information task. When uncertain, document your uncertainty in the confidence score."""


class TransactionVerificationAgent:
    """Agent that verifies transaction fees using Claude with native tool use."""

    def __init__(self, api_key: str, contract_file: str):
        """
        Initialize the agent.

        Args:
            api_key: Anthropic API key
            contract_file: Path to contract JSON file
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.contract_file = contract_file
        self.contract_data = None
        self.discrepancies = []

        # Define tools with their schemas
        self.tools = [
            {
                "name": "extract_transaction_characteristics",
                "description": "Extract and normalize key characteristics from a transaction including amount, currency, payment method, region, etc. Handles field mapping and payment method inference.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "transaction": {
                            "type": "object",
                            "description": "Raw transaction dictionary from CSV"
                        }
                    },
                    "required": ["transaction"]
                }
            },
            {
                "name": "find_applicable_contract_rule",
                "description": "Find the contract rule that applies to a transaction based on currency, payment method, region, card brand, and transaction type.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "contract_data": {
                            "type": "object",
                            "description": "Loaded contract data"
                        },
                        "currency": {
                            "type": "string",
                            "description": "Transaction currency (e.g., EUR, USD)"
                        },
                        "payment_method": {
                            "type": "string",
                            "description": "Payment method (card, sepa, apple_pay, etc.)"
                        },
                        "region": {
                            "type": "string",
                            "description": "Country code or region"
                        },
                        "card_brand": {
                            "type": "string",
                            "description": "Card brand if applicable (Visa, Mastercard, etc.)"
                        },
                        "transaction_type": {
                            "type": "string",
                            "description": "Transaction type (payment, payout, refund, chargeback)"
                        }
                    },
                    "required": ["contract_data", "currency", "payment_method", "transaction_type"]
                }
            },
            {
                "name": "calculate_expected_fees",
                "description": "Calculate expected fees based on contract rule. Applies formulas like (amount × wl_rate) + fixed_fee for payments, or flat fees for refunds/chargebacks.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "amount": {
                            "type": "number",
                            "description": "Transaction amount"
                        },
                        "contract_rule": {
                            "type": "object",
                            "description": "Contract rule from find_applicable_contract_rule"
                        },
                        "transaction_type": {
                            "type": "string",
                            "description": "Transaction type (payment, payout, refund, chargeback)"
                        }
                    },
                    "required": ["amount", "contract_rule", "transaction_type"]
                }
            },
            {
                "name": "compare_fees",
                "description": "Compare actual charged fee with expected fee. Returns comparison result with status (CORRECT/OVERCHARGED/UNDERCHARGED) and differences.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "actual_fee": {
                            "type": "number",
                            "description": "Fee that was actually charged"
                        },
                        "expected_fee": {
                            "type": "number",
                            "description": "Fee calculated from contract"
                        },
                        "tolerance": {
                            "type": "number",
                            "description": "Acceptable difference (default 0.01)"
                        }
                    },
                    "required": ["actual_fee", "expected_fee"]
                }
            }
        ]

        # Map tool names to functions
        self.tool_functions = {
            "extract_transaction_characteristics": extract_transaction_characteristics,
            "find_applicable_contract_rule": find_applicable_contract_rule,
            "calculate_expected_fees": calculate_expected_fees,
            "compare_fees": compare_fees
        }

    def initialize(self):
        """Load contract data and validate API key."""
        # Test API key first
        logger.info("Validating API key...")
        try:
            # Make a minimal test call to verify the API key works
            test_response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=10,
                messages=[{"role": "user", "content": "test"}]
            )
            logger.info("✓ API key validated successfully")
        except anthropic.AuthenticationError as e:
            logger.error(f"❌ Authentication failed: {e}")
            print("\n" + "="*60)
            print("❌ INVALID API KEY")
            print("="*60)
            print("Your Anthropic API key is invalid or missing.")
            print("\nPlease check:")
            print("1. Create .env file: cp .env.example .env")
            print("2. Add your key: ANTHROPIC_API_KEY=sk-ant-your-key-here")
            print("3. Get a key at: https://console.anthropic.com/")
            print("\nCurrent .env status:")
            import os
            if os.path.exists(".env"):
                print("  ✓ .env file exists")
                api_key = os.getenv("ANTHROPIC_API_KEY", "")
                if api_key:
                    print(f"  ✓ ANTHROPIC_API_KEY is set (starts with: {api_key[:10]}...)")
                else:
                    print("  ❌ ANTHROPIC_API_KEY is not set in .env")
            else:
                print("  ❌ .env file not found")
            print("="*60 + "\n")
            raise SystemExit(1)
        except anthropic.PermissionDeniedError as e:
            logger.error(f"❌ Permission denied: {e}")
            print("\n" + "="*60)
            print("❌ INSUFFICIENT PERMISSIONS")
            print("="*60)
            print("Your API key doesn't have the required permissions.")
            print("\nPlease check:")
            print("1. Your account has sufficient credits")
            print("2. Your API key has access to Claude Sonnet 4.5")
            print("3. Visit: https://console.anthropic.com/settings/plans")
            print("="*60 + "\n")
            raise SystemExit(1)
        except Exception as e:
            logger.error(f"❌ API validation error: {e}")
            print("\n" + "="*60)
            print("❌ API VALIDATION ERROR")
            print("="*60)
            print(f"Error: {e}")
            print("\nPlease check:")
            print("1. Your internet connection")
            print("2. Anthropic API status: https://status.anthropic.com/")
            print("="*60 + "\n")
            raise SystemExit(1)

        logger.info(f"Loading contract data from {self.contract_file}")
        self.contract_data = load_contract_data(self.contract_file)
        logger.info(f"Contract loaded: {len(self.contract_data['currencies'])} currencies, "
                   f"{len(self.contract_data['payment_methods'])} payment methods")

    def execute_tool(self, tool_name: str, tool_input: Dict) -> any:
        """Execute a tool by name."""
        if tool_name not in self.tool_functions:
            raise ValueError(f"Unknown tool: {tool_name}")

        try:
            result = self.tool_functions[tool_name](**tool_input)
            logger.debug(f"Tool {tool_name} executed successfully")
            return result
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            return {"error": str(e), "tool": tool_name}

    def verify_transaction_with_claude(self, transaction: Dict) -> Optional[Dict]:
        """
        Use Claude to verify a single transaction.

        Args:
            transaction: Transaction dictionary

        Returns:
            Discrepancy report if fee is incorrect, None if correct
        """
        # Skip declined transactions (they should have 0 fee)
        if transaction.get("status") == "declined":
            actual_commission = float(transaction.get("comission_eur", 0))
            if actual_commission != 0:
                return {
                    "transaction_id": transaction.get("transaction_id"),
                    "error": "Fee charged on declined transaction",
                    "actual_commission": actual_commission,
                    "expected_commission": 0.0,
                    "confidence": 1.0
                }
            return None  # Correctly no fee on declined

        # Prepare message for Claude
        messages = [{
            "role": "user",
            "content": f"""Verify this transaction against contract terms:

Transaction:
{json.dumps(transaction, indent=2)}

Instructions:
1. Use extract_transaction_characteristics to get normalized characteristics
2. Use find_applicable_contract_rule to find the matching contract rule (pass contract_data as provided)
3. Use calculate_expected_fees to calculate what the fee should be
4. Use compare_fees to check if actual matches expected
5. If discrepancy found, provide detailed JSON report with reasoning and confidence

Contract data is available in the contract_data variable."""
        }]

        # Agentic loop
        for iteration in range(10):
            try:
                response = self.client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=4096,
                    system=SYSTEM_PROMPT,
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
                    final_text = "\n".join(text_blocks)

                    # Try to extract JSON report
                    if "discrepancy" in final_text.lower() or "overcharged" in final_text.lower() or "undercharged" in final_text.lower():
                        # Try to parse JSON from response
                        import re
                        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', final_text, re.DOTALL)
                        if json_match:
                            try:
                                report = json.loads(json_match.group())
                                return report
                            except json.JSONDecodeError:
                                pass

                        # If no valid JSON, create basic report
                        return {
                            "transaction_id": transaction.get("transaction_id"),
                            "response": final_text,
                            "note": "Claude found discrepancy but response format needs parsing"
                        }

                    # No discrepancy found
                    return None

                elif response.stop_reason == "tool_use":
                    # Claude wants to use tools
                    tool_uses = [
                        block for block in response.content
                        if block.type == "tool_use"
                    ]

                    # Execute each tool
                    tool_results = []
                    for tool_use in tool_uses:
                        # Special handling for contract_data parameter
                        tool_input = dict(tool_use.input)
                        if "contract_data" in tool_input and tool_input["contract_data"] is None:
                            tool_input["contract_data"] = self.contract_data

                        # Execute tool
                        result = self.execute_tool(tool_use.name, tool_input)

                        # Prepare result for Claude
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": json.dumps(result, default=str)
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
                    logger.warning(f"Unexpected stop_reason: {response.stop_reason}")
                    break

            except anthropic.AuthenticationError as e:
                logger.error(f"❌ Authentication failed: {e}")
                print("\n" + "="*60)
                print("❌ AUTHENTICATION ERROR")
                print("="*60)
                print("Your Anthropic API key is invalid or missing.")
                print("\nPlease check:")
                print("1. Your .env file has: ANTHROPIC_API_KEY=sk-ant-...")
                print("2. The API key is valid and active")
                print("3. Get a key at: https://console.anthropic.com/")
                print("="*60 + "\n")
                raise SystemExit(1)

            except anthropic.PermissionDeniedError as e:
                logger.error(f"❌ Permission denied: {e}")
                print("\n" + "="*60)
                print("❌ PERMISSION DENIED")
                print("="*60)
                print("Your API key doesn't have permission for this operation.")
                print("\nPlease check:")
                print("1. Your API key has access to Claude Sonnet 4.5")
                print("2. Your account has sufficient credits")
                print("3. Check your account at: https://console.anthropic.com/")
                print("="*60 + "\n")
                raise SystemExit(1)

            except anthropic.RateLimitError as e:
                logger.error(f"⚠️  Rate limit exceeded: {e}")
                print("\n" + "="*60)
                print("⚠️  RATE LIMIT EXCEEDED")
                print("="*60)
                print("You've hit the API rate limit.")
                print("\nOptions:")
                print("1. Wait a few minutes and try again")
                print("2. Reduce --batch-size to process slower")
                print("3. Upgrade your API plan at: https://console.anthropic.com/")
                print("="*60 + "\n")
                raise SystemExit(1)

            except anthropic.InternalServerError as e:
                logger.error(f"❌ Anthropic API error: {e}")
                print("\n" + "="*60)
                print("❌ ANTHROPIC API ERROR")
                print("="*60)
                print("There's an issue with Anthropic's servers.")
                print("\nWhat to do:")
                print("1. Wait a few minutes and try again")
                print("2. Check status at: https://status.anthropic.com/")
                print("="*60 + "\n")
                raise SystemExit(1)

            except anthropic.APIConnectionError as e:
                logger.error(f"❌ Network connection error: {e}")
                print("\n" + "="*60)
                print("❌ CONNECTION ERROR")
                print("="*60)
                print("Cannot connect to Anthropic API.")
                print("\nPlease check:")
                print("1. Your internet connection")
                print("2. Firewall/proxy settings")
                print("3. Try again in a few moments")
                print("="*60 + "\n")
                raise SystemExit(1)

            except Exception as e:
                logger.error(f"Error in verification loop: {e}")
                return {
                    "transaction_id": transaction.get("transaction_id"),
                    "error": str(e)
                }

        # Max iterations exceeded
        return {
            "transaction_id": transaction.get("transaction_id"),
            "error": "Agent exceeded maximum iterations"
        }

    def run(
        self,
        transaction_file: str,
        batch_size: int = 10,
        max_transactions: Optional[int] = None
    ) -> List[Dict]:
        """
        Run verification on transactions from CSV file.

        Args:
            transaction_file: Path to transaction CSV
            batch_size: Number of transactions to process per batch
            max_transactions: Optional limit on total transactions

        Returns:
            List of discrepancy reports
        """
        self.initialize()

        logger.info(f"Starting verification (batch_size={batch_size})")

        total_processed = 0
        batch_number = 0

        while True:
            # Load batch
            logger.info(f"Processing batch {batch_number + 1}...")
            batch_data = load_transaction_data(
                transaction_file,
                limit=batch_size,
                offset=batch_number * batch_size,
                filters={"status": "approved"}  # Only approved transactions
            )

            if not batch_data["transactions"]:
                break

            # Process each transaction
            for transaction in batch_data["transactions"]:
                try:
                    discrepancy = self.verify_transaction_with_claude(transaction)
                    if discrepancy:
                        self.discrepancies.append(discrepancy)
                        logger.info(f"Discrepancy found: {discrepancy.get('transaction_id')}")

                    total_processed += 1

                    # Check limit
                    if max_transactions and total_processed >= max_transactions:
                        break
                except Exception as e:
                    logger.error(f"Error processing transaction: {e}")
                    continue

            # Check if should continue
            if not batch_data["has_more"] or (max_transactions and total_processed >= max_transactions):
                break

            batch_number += 1

        logger.info(f"\nVerification complete!")
        logger.info(f"Total processed: {total_processed}")
        logger.info(f"Discrepancies found: {len(self.discrepancies)}")

        return self.discrepancies

    def export_results(self, output_file: str = "output/discrepancy_report.json"):
        """Export results to both JSON and human-readable text files."""
        import os
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        # Export JSON (structured data)
        with open(output_file, 'w') as f:
            json.dump({
                "summary": {
                    "total_discrepancies": len(self.discrepancies),
                    "total_discrepancy_amount": sum(
                        d.get("discrepancy_amount", d.get("discrepancy", 0)) for d in self.discrepancies
                        if isinstance(d.get("discrepancy_amount", d.get("discrepancy", 0)), (int, float))
                    )
                },
                "discrepancies": self.discrepancies
            }, f, indent=2)

        logger.info(f"✓ JSON report exported to {output_file}")

        # Export human-readable text report
        text_file = output_file.replace('.json', '.txt')
        generate_text_report(self.discrepancies, text_file)
        logger.info(f"✓ Text report exported to {text_file}")

        print(f"\nReports generated:")
        print(f"  - JSON: {output_file}")
        print(f"  - Text: {text_file}")
