"""
Portfolio Optimization Harness
==============================
A three-agent architecture (Planner → Generator → Evaluator) inspired by
Anthropic's "Harness design for long-running application development" blog post.

The key ideas carried over:
1. PLANNER  – Expands a brief user goal into a detailed investment spec.
2. GENERATOR – Builds and optimises the portfolio to meet the spec.
3. EVALUATOR – Independently stress-tests the portfolio and grades it
               against hard criteria.  If it fails, feedback loops back
               to the generator for another iteration.

This is a *concept exploration* — it uses synthetic / freely available data
so you can run it without paid data feeds.
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
from dataclasses import dataclass, field, asdict
from typing import Any

import anthropic

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL = "claude-opus-4-7"
MAX_TOKENS = 4096
MAX_ITERATIONS = 3          # generator ↔ evaluator rounds
PASS_THRESHOLD = 7          # minimum average score (out of 10) to pass QA

if not os.environ.get("ANTHROPIC_API_KEY"):
    sys.exit(
        "ERROR: ANTHROPIC_API_KEY environment variable is not set. "
        "Export it (e.g. `export ANTHROPIC_API_KEY=sk-ant-...`) and try again."
    )

client = anthropic.Anthropic()   # picks up ANTHROPIC_API_KEY from env (validated above)


# ---------------------------------------------------------------------------
# Data classes for structured hand-off between agents
# ---------------------------------------------------------------------------
@dataclass
class InvestmentSpec:
    """Produced by the Planner.  Consumed by Generator & Evaluator."""
    objective: str = ""
    constraints: str = ""
    asset_universe: str = ""
    risk_budget: str = ""
    evaluation_criteria: str = ""
    raw_text: str = ""


@dataclass
class PortfolioProposal:
    """Produced by the Generator.  Consumed by the Evaluator."""
    allocations: dict[str, float] = field(default_factory=dict)
    expected_annual_return: float = 0.0
    expected_max_drawdown: float = 0.0
    methodology: str = ""
    rationale: str = ""
    raw_text: str = ""


@dataclass
class EvaluationResult:
    """Produced by the Evaluator.  Fed back to Generator on failure."""
    passed: bool = False
    scores: dict[str, float] = field(default_factory=dict)
    average_score: float = 0.0
    critique: str = ""
    raw_text: str = ""


# ---------------------------------------------------------------------------
# Helper: call the Anthropic API
# ---------------------------------------------------------------------------
def call_claude(system: str, user: str) -> str:
    """Simple wrapper around the Messages API."""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text


# ---------------------------------------------------------------------------
# AGENT 1 — PLANNER
# ---------------------------------------------------------------------------
PLANNER_SYSTEM = textwrap.dedent("""\
    You are an expert investment planner.  Your job is to take a brief,
    high-level investment goal and expand it into a detailed, actionable
    investment specification that a portfolio construction engine can execute.

    Be ambitious but realistic.  Think about:
    • Which asset classes and specific instruments are available to a US retail
      investor (stocks, ETFs, bonds, REITs, commodities, options overlays, etc.)
    • Concrete risk constraints (max drawdown, volatility targets, correlation
      limits, concentration limits)
    • Benchmark and evaluation criteria (how will we know the portfolio is good?)
    • Time horizon assumptions and rebalancing cadence
    • Tail-risk scenarios the portfolio must survive

    Respond ONLY with a JSON object with these keys:
      objective, constraints, asset_universe, risk_budget, evaluation_criteria

    No markdown fences — raw JSON only.
""")


def run_planner(user_goal: str) -> InvestmentSpec:
    print("\n" + "=" * 60)
    print("PLANNER — expanding user goal into investment spec …")
    print("=" * 60)

    raw = call_claude(PLANNER_SYSTEM, user_goal)
    print(raw[:500], "…\n" if len(raw) > 500 else "\n")

    try:
        data = json.loads(raw, strict=False)
    except json.JSONDecodeError:
        # Model sometimes wraps in markdown fences
        import re
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(m.group(), strict=False) if m else {}

    return InvestmentSpec(
        objective=data.get("objective", ""),
        constraints=data.get("constraints", ""),
        asset_universe=data.get("asset_universe", ""),
        risk_budget=data.get("risk_budget", ""),
        evaluation_criteria=data.get("evaluation_criteria", ""),
        raw_text=raw,
    )


# ---------------------------------------------------------------------------
# AGENT 2 — GENERATOR
# ---------------------------------------------------------------------------
GENERATOR_SYSTEM = textwrap.dedent("""\
    You are an expert quantitative portfolio constructor.
    You receive a detailed investment specification and (optionally) feedback
    from a previous QA round.  Your job is to produce a concrete portfolio
    allocation that meets ALL constraints.

    Think step-by-step:
    1. Reason about which instruments best satisfy the objective under the
       constraints.
    2. Use a mental model of mean-variance optimisation with a drawdown
       overlay.  Reference realistic historical statistics (you may
       approximate from memory — this is an exploration, not live trading).
    3. Stress-test your own proposal against the tail-risk scenarios in the
       spec BEFORE submitting.
    4. If you received evaluator feedback, address every point raised.

    Respond ONLY with a JSON object:
    {
      "allocations": {"TICKER_OR_ASSET": weight, ...},
      "expected_annual_return": float,
      "expected_max_drawdown": float,
      "methodology": "string",
      "rationale": "string"
    }

    Weights must sum to 1.0.  No markdown fences — raw JSON only.
""")


def run_generator(
    spec: InvestmentSpec,
    feedback: str | None = None,
    iteration: int = 1,
) -> PortfolioProposal:
    print("\n" + "=" * 60)
    print(f"GENERATOR — building portfolio (iteration {iteration}) …")
    print("=" * 60)

    user_msg = f"INVESTMENT SPEC:\n{spec.raw_text}\n"
    if feedback:
        user_msg += f"\nEVALUATOR FEEDBACK FROM PREVIOUS ROUND:\n{feedback}\n"
        user_msg += "\nAddress every issue raised.  Revise the portfolio accordingly."

    raw = call_claude(GENERATOR_SYSTEM, user_msg)
    print(raw[:600], "…\n" if len(raw) > 600 else "\n")

    try:
        data = json.loads(raw, strict=False)
    except json.JSONDecodeError:
        import re
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(m.group(), strict=False) if m else {}

    return PortfolioProposal(
        allocations=data.get("allocations", {}),
        expected_annual_return=data.get("expected_annual_return", 0),
        expected_max_drawdown=data.get("expected_max_drawdown", 0),
        methodology=data.get("methodology", ""),
        rationale=data.get("rationale", ""),
        raw_text=raw,
    )


# ---------------------------------------------------------------------------
# AGENT 3 — EVALUATOR
# ---------------------------------------------------------------------------
EVALUATOR_SYSTEM = textwrap.dedent("""\
    You are a skeptical, rigorous portfolio risk analyst — the QA agent.
    Your job is to independently evaluate a proposed portfolio against an
    investment specification.  You must be TOUGH.  Do NOT give the benefit
    of the doubt.

    Grade each criterion on a 1-10 scale.  Be specific about failures.

    CRITERIA (graded 1-10):
    1. CONSTRAINT COMPLIANCE — Does the portfolio truly stay within the
       ≤5% max annual loss constraint under realistic historical scenarios?
       Check: 2008 GFC, 2020 COVID crash, 2022 rate-hike drawdown.
       Score ≤ 4 if ANY scenario likely breaches the 5% loss limit.

    2. RETURN POTENTIAL — Is the expected return realistic and competitive
       given the constraints?  Penalise both overestimation and unnecessary
       conservatism.

    3. DIVERSIFICATION — Are risks well-spread across uncorrelated sources?
       Penalise concentration and hidden correlations (e.g., all equity-like).

    4. IMPLEMENTABILITY — Can a US retail investor actually buy these
       instruments easily and cheaply?  Penalise illiquids, high-fee
       products, or instruments requiring institutional access.

    5. METHODOLOGY RIGOUR — Is the construction approach sound, or does it
       hand-wave?  Are the return / risk estimates grounded in data?

    Respond ONLY with a JSON object:
    {
      "scores": {
        "constraint_compliance": int,
        "return_potential": int,
        "diversification": int,
        "implementability": int,
        "methodology_rigour": int
      },
      "critique": "Detailed critique addressing each criterion …",
      "passed": true/false   // true only if average >= 7 AND no single score <= 4
    }

    No markdown fences — raw JSON only.
""")


def run_evaluator(
    spec: InvestmentSpec,
    proposal: PortfolioProposal,
) -> EvaluationResult:
    print("\n" + "=" * 60)
    print("EVALUATOR — stress-testing the portfolio …")
    print("=" * 60)

    user_msg = (
        f"INVESTMENT SPEC:\n{spec.raw_text}\n\n"
        f"PROPOSED PORTFOLIO:\n{proposal.raw_text}\n"
    )

    raw = call_claude(EVALUATOR_SYSTEM, user_msg)
    print(raw[:600], "…\n" if len(raw) > 600 else "\n")

    try:
        data = json.loads(raw, strict=False)
    except json.JSONDecodeError:
        import re
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(m.group(), strict=False) if m else {}

    scores = data.get("scores", {})
    avg = sum(scores.values()) / len(scores) if scores else 0
    any_critical_fail = any(v <= 4 for v in scores.values())
    passed = avg >= PASS_THRESHOLD and not any_critical_fail

    return EvaluationResult(
        passed=passed,
        scores=scores,
        average_score=round(avg, 2),
        critique=data.get("critique", ""),
        raw_text=raw,
    )


# ---------------------------------------------------------------------------
# ORCHESTRATOR — the harness loop
# ---------------------------------------------------------------------------
def run_harness(user_goal: str) -> dict[str, Any]:
    """
    Main entry point.  Runs the full Planner → Generator ↔ Evaluator loop.
    Returns a summary dict with the final portfolio and all iteration history.
    """
    # --- Step 1: Plan ---
    spec = run_planner(user_goal)

    history: list[dict] = []
    proposal = None
    evaluation = None
    feedback = None

    for i in range(1, MAX_ITERATIONS + 1):
        # --- Step 2: Generate ---
        proposal = run_generator(spec, feedback=feedback, iteration=i)

        # --- Step 3: Evaluate ---
        evaluation = run_evaluator(spec, proposal)

        history.append({
            "iteration": i,
            "allocations": proposal.allocations,
            "expected_return": proposal.expected_annual_return,
            "expected_max_drawdown": proposal.expected_max_drawdown,
            "scores": evaluation.scores,
            "average_score": evaluation.average_score,
            "passed": evaluation.passed,
            "critique_snippet": evaluation.critique[:300],
        })

        print(f"\n--- Iteration {i} result ---")
        print(f"  Scores : {evaluation.scores}")
        print(f"  Average: {evaluation.average_score}")
        print(f"  Passed : {evaluation.passed}")

        if evaluation.passed:
            print("\n✅  Portfolio PASSED evaluation — stopping.\n")
            break

        print("❌  Portfolio FAILED — feeding critique back to generator …\n")
        feedback = evaluation.critique

    else:
        print(f"\n⚠️  Reached max iterations ({MAX_ITERATIONS}) without passing.\n")

    return {
        "spec": asdict(spec),
        "final_proposal": asdict(proposal) if proposal else None,
        "final_evaluation": asdict(evaluation) if evaluation else None,
        "iteration_history": history,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    goal = (
        "Optimise a portfolio for a US-based retail investor. "
        "Maximise annual return while ensuring the portfolio can lose "
        "no more than 5% of its invested value in any given year. "
        "Use any instruments available to a typical retail investor "
        "(stocks, ETFs, bonds, options overlays, etc.)."
    )

    result = run_harness(goal)

    # Dump full trace to a JSON file for inspection
    with open("harness_output.json", "w") as f:
        json.dump(result, f, indent=2, default=str)

    print("\n" + "=" * 60)
    print("FINAL PORTFOLIO")
    print("=" * 60)
    if result["final_proposal"]:
        for ticker, weight in result["final_proposal"]["allocations"].items():
            print(f"  {ticker:20s}  {weight:6.1%}")
        print(f"\n  Expected return   : {result['final_proposal']['expected_annual_return']:.1%}")
        print(f"  Expected max loss : {result['final_proposal']['expected_max_drawdown']:.1%}")
    print(f"\n  Passed QA         : {result['final_evaluation']['passed']}")
    print(f"  Final avg score   : {result['final_evaluation']['average_score']}")
    print(f"\nFull trace saved to harness_output.json")
