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
import random
import sys
import textwrap
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any

import anthropic

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL = "claude-opus-4-7"
MAX_TOKENS = 4096
MAX_ITERATIONS = 3          # generator ↔ evaluator rounds
PASS_THRESHOLD = 7          # minimum average score (out of 10) to pass QA
TARGET_MAX_LOSS = 0.05      # 5% — the loss budget we want expected_max_drawdown to land on
UNDER_UTILISATION_BAND = 0.04  # below this we consider the risk budget under-utilised

# --- Retry / backoff config for transient Anthropic API errors -------------
# Sequence of attempts and sleeps when an attempt fails with a retryable
# error (529 Overloaded, 429 rate limit, 5xx, connection / timeout errors):
#
#   attempt 1  →  sleep   2s (±25% jitter) →
#   attempt 2  →  sleep   4s  →
#   attempt 3  →  sleep   8s  →
#   attempt 4  →  sleep  16s  →
#   attempt 5  →  sleep  32s  →
#   attempt 6  →  give up and re-raise
#
# Max wall-clock spent on retries before giving up ≈ 62s (+ jitter).
SDK_MAX_RETRIES = 5                              # SDK-level retries (fast transient blips)
RETRY_MAX_ATTEMPTS = 6                           # outer wrapper attempts on top of SDK
RETRY_INITIAL_BACKOFF_SECONDS = 2.0
RETRY_MAX_BACKOFF_SECONDS = 32.0
RETRYABLE_HTTP_STATUS = {429, 500, 502, 503, 504, 529}

if not os.environ.get("ANTHROPIC_API_KEY"):
    sys.exit(
        "ERROR: ANTHROPIC_API_KEY environment variable is not set. "
        "Export it (e.g. `export ANTHROPIC_API_KEY=sk-ant-...`) and try again."
    )

# Bump SDK retries above the default of 2.  The SDK handles fast transient
# blips silently; our outer wrapper (in call_claude) handles longer overload
# events with visible progress logs.
client = anthropic.Anthropic(max_retries=SDK_MAX_RETRIES)


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
    descriptions: dict[str, str] = field(default_factory=dict)
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
def _is_retryable(exc: BaseException) -> bool:
    """
    Return True for transient Anthropic API errors worth retrying:
      • 429 Rate-limit, 5xx, 529 Overloaded — server-side back-pressure.
      • Connection / timeout errors — network blips.
    Auth, validation, and other 4xx errors are NOT retried.
    """
    if isinstance(exc, (anthropic.APIConnectionError, anthropic.APITimeoutError)):
        return True
    if isinstance(exc, anthropic.APIStatusError):
        return getattr(exc, "status_code", None) in RETRYABLE_HTTP_STATUS
    return False


def call_claude(system: str, user: str) -> str:
    """
    Wrapper around the Messages API with exponential-backoff retry on
    transient errors (529 Overloaded, 429 rate limits, 5xx, connection
    blips).  Re-raises immediately on terminal errors (auth, bad request,
    etc.) so we fail fast on real bugs.
    """
    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return resp.content[0].text
        except Exception as exc:
            if attempt == RETRY_MAX_ATTEMPTS or not _is_retryable(exc):
                raise
            backoff = min(
                RETRY_INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1)),
                RETRY_MAX_BACKOFF_SECONDS,
            )
            backoff *= 1 + random.random() * 0.25  # +0–25% jitter
            kind = type(exc).__name__
            status = getattr(exc, "status_code", None)
            status_suffix = f" (HTTP {status})" if status else ""
            print(
                f"  ⚠️  Anthropic API {kind}{status_suffix} on attempt "
                f"{attempt}/{RETRY_MAX_ATTEMPTS} — retrying in {backoff:.1f}s",
                flush=True,
            )
            time.sleep(backoff)
    # The loop only exits via return or raise — this is unreachable but
    # satisfies static analysers.
    raise RuntimeError("call_claude retry loop exited unexpectedly")


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

    RISK BUDGET DISCIPLINE — IMPORTANT:
    Treat the 5% max annual loss as a budget to be USED, not avoided.
    A portfolio with a 2% expected_max_drawdown is wasting risk capacity
    and almost certainly leaving return on the table.  Aim your
    expected_max_drawdown as close to 5% as you honestly can WITHOUT
    crossing it.  If prior feedback indicated you were over 5%, your top
    priority this round is bringing the drawdown down — even at some cost
    to expected return.  If prior feedback indicated you were well under
    5%, raise the return profile by deploying more risk-bearing exposure
    until your drawdown is near (but under) 5%.

    Respond ONLY with a JSON object:
    {
      "allocations": {"TICKER_OR_ASSET": weight, ...},
      "descriptions": {"TICKER_OR_ASSET": "one-line plain-English description", ...},
      "expected_annual_return": float,
      "expected_max_drawdown": float,
      "methodology": "string",
      "rationale": "string"
    }

    The "descriptions" map must contain one entry for EVERY ticker in
    "allocations".  Each description should be a single concise sentence
    (≤ 15 words) that tells a non-expert what the instrument is, e.g.:
      "VOO": "Vanguard S&P 500 ETF — tracks the 500 largest US companies",
      "TLT": "iShares 20+ Year Treasury ETF — long-duration US government bonds",
      "SPX_PUT_SPREAD": "Protective put spread on the S&P 500 index — tail-risk hedge"
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
        descriptions=data.get("descriptions", {}),
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
       ALSO score ≤ 6 if the expected_max_drawdown is materially BELOW 5%
       (e.g., under ~4%) without a specific constraint forcing that level
       of conservatism — under-utilising the 5% risk budget is a flaw,
       not a virtue, because it sacrifices return for no good reason.
       A portfolio that lands near (but under) 5% should score highest
       on this criterion; one that lands far below it should be marked
       down for wasting risk capacity.

    2. RETURN POTENTIAL — Is the expected return realistic and competitive
       given the constraints?  Penalise both overestimation and unnecessary
       conservatism.

    3. DIVERSIFICATION — Are risks well-spread across uncorrelated sources?
       Penalise concentration and hidden correlations (e.g., all equity-like).
       Penalize the agent for proposing multiple highly correlated assets.

    4. IMPLEMENTABILITY — Can a US retail investor actually buy these
       instruments easily and cheaply?  Penalise illiquids, high-fee
       products, or instruments requiring institutional access. Penalize
       proposing strategies with a total number of tickers > 15.

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
def _build_feedback(evaluation: EvaluationResult, proposal: PortfolioProposal) -> str:
    """
    Produce the next round's feedback string based on the current evaluation.

    Three regimes:
      • Failed QA          → pass the critique through unchanged (today's behaviour).
      • Passed but over 5% → tell the generator to bring drawdown down to ~5%
                              without sacrificing scores.
      • Passed but well
        under 5%           → tell the generator the risk budget is being wasted
                              and to push drawdown closer to (but under) 5%.
      • Passed and near 5% → still ask for a refinement attempt — the selector
                              will keep the best across iterations.
    """
    if not evaluation.passed:
        return evaluation.critique

    dd = proposal.expected_max_drawdown
    if dd > TARGET_MAX_LOSS:
        overshoot_pct = (dd - TARGET_MAX_LOSS) * 100
        return (
            f"QA PASSED with average score {evaluation.average_score}, "
            f"BUT expected_max_drawdown is {dd:.2%}, which exceeds the "
            f"{TARGET_MAX_LOSS:.0%} loss target by {overshoot_pct:.1f} "
            f"percentage points. Your top priority this round is to "
            f"REDUCE expected_max_drawdown as close to {TARGET_MAX_LOSS:.0%} "
            f"as possible WITHOUT crossing it, while keeping every QA "
            f"score ≥ {PASS_THRESHOLD}. Accept lower expected return if "
            f"necessary. Prior critique for reference:\n{evaluation.critique}"
        )
    if dd < UNDER_UTILISATION_BAND:
        return (
            f"QA PASSED with average score {evaluation.average_score} and "
            f"expected_max_drawdown of {dd:.2%}, which is well UNDER the "
            f"{TARGET_MAX_LOSS:.0%} loss budget. You are leaving return on "
            f"the table. This round, deploy more risk-bearing exposure to "
            f"raise expected_max_drawdown closer to (but still under) "
            f"{TARGET_MAX_LOSS:.0%}, while keeping every QA score "
            f"≥ {PASS_THRESHOLD}. Prior critique for reference:\n"
            f"{evaluation.critique}"
        )
    return (
        f"QA PASSED with average score {evaluation.average_score} and "
        f"expected_max_drawdown of {dd:.2%}, which is close to the "
        f"{TARGET_MAX_LOSS:.0%} target. Attempt one more refinement: try "
        f"to either raise expected_annual_return without exceeding "
        f"{TARGET_MAX_LOSS:.0%} drawdown, or improve the QA scores while "
        f"holding drawdown near {TARGET_MAX_LOSS:.0%}. Prior critique:\n"
        f"{evaluation.critique}"
    )


def _select_best_iteration(history: list[dict]) -> int | None:
    """
    Return the 1-based iteration index of the best passing iteration, or None
    if no iteration passed.

    Selection key (smaller is better):
      1. |expected_max_drawdown - TARGET_MAX_LOSS|   — closeness to the 5% target
      2. expected_max_drawdown                       — prefer smaller drawdown on tie
      3. -average_score                              — prefer higher score on tie
    """
    passing = [h for h in history if h["passed"]]
    if not passing:
        return None
    best = min(
        passing,
        key=lambda h: (
            abs(h["expected_max_drawdown"] - TARGET_MAX_LOSS),
            h["expected_max_drawdown"],
            -h["average_score"],
        ),
    )
    return best["iteration"]


def run_harness(user_goal: str) -> dict[str, Any]:
    """
    Main entry point.  Runs the full Planner → Generator ↔ Evaluator loop.

    Unlike the original harness, this version ALWAYS runs MAX_ITERATIONS
    rounds, even if QA passes earlier.  After the loop completes, it
    selects the passing iteration whose expected_max_drawdown is closest
    to TARGET_MAX_LOSS.  If no iteration passes, the last iteration is
    returned (matching the original "max iterations without passing"
    behaviour).
    """
    # --- Step 1: Plan ---
    spec = run_planner(user_goal)

    history: list[dict] = []
    proposals: list[PortfolioProposal] = []
    evaluations: list[EvaluationResult] = []
    feedback: str | None = None

    for i in range(1, MAX_ITERATIONS + 1):
        # --- Step 2: Generate ---
        proposal = run_generator(spec, feedback=feedback, iteration=i)

        # --- Step 3: Evaluate ---
        evaluation = run_evaluator(spec, proposal)

        proposals.append(proposal)
        evaluations.append(evaluation)

        history.append({
            "iteration": i,
            "allocations": proposal.allocations,
            "descriptions": proposal.descriptions,
            "expected_return": proposal.expected_annual_return,
            "expected_max_drawdown": proposal.expected_max_drawdown,
            "scores": evaluation.scores,
            "average_score": evaluation.average_score,
            "passed": evaluation.passed,
            "critique_snippet": evaluation.critique[:300],
            "selected": False,
        })

        print(f"\n--- Iteration {i} result ---")
        print(f"  Scores              : {evaluation.scores}")
        print(f"  Average             : {evaluation.average_score}")
        print(f"  Passed              : {evaluation.passed}")
        print(f"  Expected max loss   : {proposal.expected_max_drawdown:.2%}")
        print(f"  Target max loss     : {TARGET_MAX_LOSS:.0%}")

        if i == MAX_ITERATIONS:
            # No need to compute feedback after the last round.
            continue

        if evaluation.passed:
            dd = proposal.expected_max_drawdown
            if dd > TARGET_MAX_LOSS:
                print("✅  Passed QA but drawdown OVER target — pushing for lower drawdown next round.\n")
            elif dd < UNDER_UTILISATION_BAND:
                print("✅  Passed QA but drawdown WELL UNDER target — pushing for more risk budget use next round.\n")
            else:
                print("✅  Passed QA and drawdown near target — attempting one more refinement.\n")
        else:
            print("❌  Failed QA — feeding critique back to generator.\n")

        feedback = _build_feedback(evaluation, proposal)

    # --- Step 4: Select the best passing iteration ---
    selected_idx = _select_best_iteration(history)

    if selected_idx is not None:
        history[selected_idx - 1]["selected"] = True
        final_proposal = proposals[selected_idx - 1]
        final_evaluation = evaluations[selected_idx - 1]
        print(
            f"\n🎯  Selected iteration {selected_idx} of {MAX_ITERATIONS}: "
            f"passing portfolio with expected_max_drawdown "
            f"{final_proposal.expected_max_drawdown:.2%} "
            f"(closest to {TARGET_MAX_LOSS:.0%} target).\n"
        )
    else:
        # Fall back to the last iteration when nothing passed.
        history[-1]["selected"] = True
        final_proposal = proposals[-1]
        final_evaluation = evaluations[-1]
        print(
            f"\n⚠️  Reached max iterations ({MAX_ITERATIONS}) without any "
            f"passing portfolio. Returning last iteration.\n"
        )

    return {
        "spec": asdict(spec),
        "final_proposal": asdict(final_proposal),
        "final_evaluation": asdict(final_evaluation),
        "selected_iteration": selected_idx,
        "target_max_loss": TARGET_MAX_LOSS,
        "iteration_history": history,
    }


# ---------------------------------------------------------------------------
# Human-readable Markdown report writer
# ---------------------------------------------------------------------------
def _format_value(v: Any) -> str:
    """Render a JSON-ish value as a readable markdown fragment."""
    if v is None:
        return "_(none)_"
    if isinstance(v, str):
        return v.strip() or "_(empty)_"
    if isinstance(v, (list, dict)):
        return "```json\n" + json.dumps(v, indent=2) + "\n```"
    return str(v)


def _format_weight(w: Any) -> str:
    try:
        return f"{float(w):.2%}"
    except (TypeError, ValueError):
        return str(w)


def write_markdown_report(result: dict[str, Any], path: str) -> None:
    """
    Write a human-readable Markdown report mirroring the JSON trace.
    Preserves every structured field; raw model text is tucked into
    collapsible <details> blocks so the file stays scannable.
    """
    spec = result.get("spec") or {}
    final_p = result.get("final_proposal") or {}
    final_e = result.get("final_evaluation") or {}
    history = result.get("iteration_history") or []
    sel = result.get("selected_iteration")
    target = result.get("target_max_loss", TARGET_MAX_LOSS)

    out: list[str] = []
    push = out.append

    # ---- Header ----
    push("# Portfolio Optimization Harness — Report")
    push("")
    push(f"- **Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    push(f"- **Model:** `{MODEL}`")
    push(f"- **Iterations run:** {len(history)} of {MAX_ITERATIONS}")
    if sel is not None:
        push(f"- **Selected iteration:** {sel} — best passing portfolio, closest to {target:.1%} target")
    else:
        push("- **Selected iteration:** last (no iteration passed QA — see fallback note below)")
    push(f"- **Target max loss:** {target:.1%}")
    push(f"- **Pass threshold:** average score ≥ {PASS_THRESHOLD} with no single score ≤ 4")
    push("")

    # ---- Final portfolio ----
    push("## Final Portfolio (selected)")
    push("")
    allocs = final_p.get("allocations") or {}
    descs = final_p.get("descriptions") or {}
    if allocs:
        if descs:
            push("| Ticker | Weight | Description |")
            push("|--------|-------:|-------------|")
            for ticker, weight in allocs.items():
                desc = descs.get(ticker, "")
                push(f"| `{ticker}` | {_format_weight(weight)} | {desc} |")
        else:
            push("| Ticker | Weight |")
            push("|--------|-------:|")
            for ticker, weight in allocs.items():
                push(f"| `{ticker}` | {_format_weight(weight)} |")
        push("")
    try:
        er = float(final_p.get("expected_annual_return", 0))
        dd = float(final_p.get("expected_max_drawdown", 0))
        push(f"- **Expected annual return:** {er:.2%}")
        push(f"- **Expected max drawdown:** {dd:.2%}  (target ≤ {target:.1%})")
    except (TypeError, ValueError):
        push(f"- **Expected annual return:** {final_p.get('expected_annual_return')}")
        push(f"- **Expected max drawdown:** {final_p.get('expected_max_drawdown')}")
    push(f"- **Passed QA:** {final_e.get('passed', False)}")
    push(f"- **Average QA score:** {final_e.get('average_score', 0)}")
    push("")

    # ---- Iteration summary ----
    push("## Iteration Summary")
    push("")
    push("| # | Avg Score | Exp. Return | Max Loss | Δ to target | Passed | Selected |")
    push("|--:|----------:|------------:|---------:|------------:|:------:|:--------:|")
    for h in history:
        try:
            dd_i = float(h.get("expected_max_drawdown", 0))
            er_i = float(h.get("expected_return", 0))
        except (TypeError, ValueError):
            dd_i, er_i = 0.0, 0.0
        dist = abs(dd_i - target)
        passed = "YES" if h.get("passed") else "NO"
        sel_mark = "★" if h.get("selected") else ""
        push(
            f"| {h.get('iteration')} | {h.get('average_score', 0):.2f} | "
            f"{er_i:.2%} | {dd_i:.2%} | {dist:.2%} | {passed} | {sel_mark} |"
        )
    push("")

    # ---- Investment spec ----
    push("## Investment Spec (from Planner)")
    push("")
    for key in ("objective", "constraints", "asset_universe", "risk_budget", "evaluation_criteria"):
        if key in spec and spec[key] not in (None, ""):
            label = key.replace("_", " ").title()
            push(f"### {label}")
            push("")
            push(_format_value(spec[key]))
            push("")
    if spec.get("raw_text"):
        push("<details><summary>Planner raw response</summary>")
        push("")
        push("```")
        push(spec["raw_text"].rstrip())
        push("```")
        push("")
        push("</details>")
        push("")

    # ---- Selected portfolio methodology / rationale ----
    push("## Selected Portfolio — Methodology & Rationale")
    push("")
    if final_p.get("methodology"):
        push("### Methodology")
        push("")
        push(_format_value(final_p["methodology"]))
        push("")
    if final_p.get("rationale"):
        push("### Rationale")
        push("")
        push(_format_value(final_p["rationale"]))
        push("")
    if final_p.get("raw_text"):
        push("<details><summary>Generator raw response</summary>")
        push("")
        push("```")
        push(final_p["raw_text"].rstrip())
        push("```")
        push("")
        push("</details>")
        push("")

    # ---- Selected portfolio evaluation ----
    push("## Selected Portfolio — Evaluator Report")
    push("")
    scores = final_e.get("scores") or {}
    if scores:
        push("### Scores")
        push("")
        push("| Criterion | Score |")
        push("|-----------|------:|")
        for k, v in scores.items():
            push(f"| {k.replace('_', ' ')} | {v} |")
        push(f"| **Average** | **{final_e.get('average_score', 0)}** |")
        push("")
    if final_e.get("critique"):
        push("### Critique")
        push("")
        push(_format_value(final_e["critique"]))
        push("")
    if final_e.get("raw_text"):
        push("<details><summary>Evaluator raw response</summary>")
        push("")
        push("```")
        push(final_e["raw_text"].rstrip())
        push("```")
        push("")
        push("</details>")
        push("")

    # ---- Per-iteration detail ----
    push("## Iteration History (detailed)")
    push("")
    for h in history:
        sel_mark = " — ★ selected" if h.get("selected") else ""
        push(f"### Iteration {h.get('iteration')}{sel_mark}")
        push("")
        try:
            dd_i = float(h.get("expected_max_drawdown", 0))
            er_i = float(h.get("expected_return", 0))
            push(f"- **Passed:** {h.get('passed')}")
            push(f"- **Average score:** {h.get('average_score', 0):.2f}")
            push(f"- **Expected return:** {er_i:.2%}")
            push(f"- **Expected max drawdown:** {dd_i:.2%}")
        except (TypeError, ValueError):
            push(f"- **Passed:** {h.get('passed')}")
            push(f"- **Average score:** {h.get('average_score')}")
            push(f"- **Expected return:** {h.get('expected_return')}")
            push(f"- **Expected max drawdown:** {h.get('expected_max_drawdown')}")
        push("")
        scores_i = h.get("scores") or {}
        if scores_i:
            push("**Scores:**")
            push("")
            push("| Criterion | Score |")
            push("|-----------|------:|")
            for k, v in scores_i.items():
                push(f"| {k.replace('_', ' ')} | {v} |")
            push("")
        allocs_i = h.get("allocations") or {}
        descs_i = h.get("descriptions") or {}
        if allocs_i:
            push("**Allocations:**")
            push("")
            if descs_i:
                push("| Ticker | Weight | Description |")
                push("|--------|-------:|-------------|")
                for ticker, weight in allocs_i.items():
                    desc = descs_i.get(ticker, "")
                    push(f"| `{ticker}` | {_format_weight(weight)} | {desc} |")
            else:
                push("| Ticker | Weight |")
                push("|--------|-------:|")
                for ticker, weight in allocs_i.items():
                    push(f"| `{ticker}` | {_format_weight(weight)} |")
            push("")
        snip = h.get("critique_snippet")
        if snip:
            push("**Critique snippet (first 300 chars):**")
            push("")
            for line in snip.splitlines():
                push(f"> {line}")
            push("")

    with open(path, "w") as f:
        f.write("\n".join(out))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    _MODEL_ALIASES: dict[str, str] = {
        "haiku":  "claude-haiku-4-5-20251001",
        "sonnet": "claude-sonnet-4-6",
        "opus":   "claude-opus-4-7",
    }

    parser = argparse.ArgumentParser(
        description="Portfolio Optimization Harness — Planner → Generator ↔ Evaluator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            examples:
              uv run python long_running_agent/harness.py
              uv run python long_running_agent/harness.py --test
              uv run python long_running_agent/harness.py --model sonnet
              uv run python long_running_agent/harness.py --model haiku --iterations 1
        """),
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help=(
            "Test mode: use claude-haiku-4-5-20251001 with 1 iteration to smoke-test "
            "the full pipeline quickly and cheaply. Useful when Opus is overloaded or "
            "you just want to verify the plumbing."
        ),
    )
    parser.add_argument(
        "--model",
        metavar="MODEL",
        help=(
            "Override the model. Accepts short aliases (haiku, sonnet, opus) or a "
            "full Anthropic model ID. Ignored when --test is also set."
        ),
    )
    parser.add_argument(
        "--iterations",
        type=int,
        metavar="N",
        help=(
            "Override the number of generator ↔ evaluator rounds (default "
            f"{MAX_ITERATIONS}). Ignored when --test is also set."
        ),
    )
    args = parser.parse_args()

    # Apply --test first (it takes precedence), then individual overrides.
    if args.test:
        MODEL = _MODEL_ALIASES["haiku"]
        MAX_ITERATIONS = 1
        print(f"[TEST MODE] model={MODEL}  iterations={MAX_ITERATIONS}")
    else:
        if args.model:
            MODEL = _MODEL_ALIASES.get(args.model, args.model)
            print(f"[model override] {MODEL}")
        if args.iterations is not None:
            if args.iterations < 1:
                parser.error("--iterations must be ≥ 1")
            MAX_ITERATIONS = args.iterations
            print(f"[iterations override] {MAX_ITERATIONS}")

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

    # Also write a human-readable Markdown report
    write_markdown_report(result, "harness_output.md")

    print("\n" + "=" * 60)
    print("FINAL PORTFOLIO")
    print("=" * 60)
    sel = result.get("selected_iteration")
    if sel is not None:
        print(f"  Selected iteration : {sel} of {MAX_ITERATIONS} (best passing)")
    else:
        print(f"  Selected iteration : last of {MAX_ITERATIONS} (no iteration passed)")
    print(f"  Target max loss    : {result['target_max_loss']:.1%}\n")

    if result["final_proposal"]:
        for ticker, weight in result["final_proposal"]["allocations"].items():
            print(f"  {ticker:20s}  {weight:6.1%}")
        print(f"\n  Expected return    : {result['final_proposal']['expected_annual_return']:.1%}")
        print(f"  Expected max loss  : {result['final_proposal']['expected_max_drawdown']:.1%}")
    print(f"\n  Passed QA          : {result['final_evaluation']['passed']}")
    print(f"  Final avg score    : {result['final_evaluation']['average_score']}")

    print("\n  Iteration summary:")
    for h in result["iteration_history"]:
        mark = "★" if h["selected"] else " "
        passed_str = "PASS" if h["passed"] else "FAIL"
        print(
            f"   {mark} #{h['iteration']}  "
            f"avg={h['average_score']:.2f}  "
            f"max_loss={h['expected_max_drawdown']:.2%}  "
            f"{passed_str}"
        )

    print("\nFull trace saved to:")
    print("  - harness_output.json   (machine-readable)")
    print("  - harness_output.md     (human-readable)")
