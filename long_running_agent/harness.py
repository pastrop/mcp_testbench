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

# --- Pricing / lot-size feasibility ----------------------------------------
DEFAULT_CAPITAL = 100_000.0  # USD assumed for whole-share lot-size check
PRICING_DISCLAIMER = (
    "Prices are fetched from Yahoo Finance via the `yfinance` library and "
    "reflect the most recent available quote (last close or recent "
    "intraday). They may differ from real-time market data, and Yahoo's "
    "unofficial API can occasionally return stale or missing values. "
    "Do NOT rely on these numbers for trading decisions."
)

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


@dataclass
class AdvisorOutput:
    """
    Produced by the Advisor.  Pure advisory — never changes the portfolio.
    Surfaces highly correlated holdings in the FINAL portfolio and offers
    concrete consolidation ideas with explicit trade-offs.
    """
    # List of {"merge_from": [tickers], "merge_into": ticker,
    #          "rationale": str, "tradeoff": str}
    suggestions: list[dict[str, Any]] = field(default_factory=list)
    # List of {"a": ticker_a, "b": ticker_b, "rho": float,
    #          "note": optional str}
    correlation_pairs: list[dict[str, Any]] = field(default_factory=list)
    notes: str = ""
    raw_text: str = ""


@dataclass
class TickerPricing:
    """One row of the pricing / lot-size feasibility table."""
    ticker: str
    weight: float                       # target weight from the final proposal
    status: str = "ok"                  # "ok" | "error"
    price: float | None = None          # last available quote in USD
    target_dollars: float = 0.0         # capital * weight
    shares: int = 0                     # floor(target_dollars / price)
    actual_dollars: float = 0.0         # shares * price
    actual_weight: float = 0.0          # actual_dollars / capital
    weight_drift: float = 0.0           # actual_weight - target weight (signed)
    error: str | None = None


@dataclass
class PricingResult:
    """Aggregated pricing + lot-size feasibility report."""
    capital: float = 0.0
    total_invested: float = 0.0
    leftover_cash: float = 0.0
    max_abs_drift: float = 0.0          # largest |weight_drift| across OK rows
    rows: list[TickerPricing] = field(default_factory=list)
    failed_tickers: list[str] = field(default_factory=list)
    disclaimer: str = ""
    source: str = "yfinance"
    fetched_at: str = ""                # ISO timestamp of the fetch
    error: str | None = None            # set when pricing as a whole could not run


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
      "passed": true/false
    }

    THE "passed" FIELD IS YOUR INDEPENDENT JUDGEMENT (not a derived rule).
    Return passed=true ONLY if you would unconditionally recommend this
    portfolio to a real client TODAY.  Return passed=false — even if the
    average score is ≥ 7 — when you found ANY of:
      • A binding hard-constraint violation (FX hedging, ticker cap,
        sector cap, leverage, instrument restrictions, etc.).
      • A realistic historical scenario that breaches the 5% loss limit.
      • Material methodology gaps that make the loss estimates unreliable.
    Your "passed" value will be combined with the numeric pass rule
    (average ≥ 7 AND no single score ≤ 4) — all three must hold to pass.

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
    # Honor the evaluator's own pass/fail judgement.  The model often spots
    # binding-constraint violations (e.g. FX hedging, ticker count) that the
    # numeric average + min-score rule alone would let through.  Missing
    # field defaults to False — we want an explicit "yes" from the model.
    model_said_passed = bool(data.get("passed", False))
    passed = (
        avg >= PASS_THRESHOLD
        and not any_critical_fail
        and model_said_passed
    )

    return EvaluationResult(
        passed=passed,
        scores=scores,
        average_score=round(avg, 2),
        critique=data.get("critique", ""),
        raw_text=raw,
    )


# ---------------------------------------------------------------------------
# AGENT 4 — REFINER  (post-selection fine-tuner)
# ---------------------------------------------------------------------------
REFINER_SYSTEM = textwrap.dedent("""\
    You are a senior portfolio fine-tuner.  Your input is:
      • An investment specification.
      • A portfolio that has already been selected as the best of several
        candidates.
      • A detailed critique from the QA evaluator pointing out specific
        issues with that portfolio.

    Your job is to produce a REVISED portfolio that addresses every issue
    raised in the critique, while preserving everything the critique did
    NOT flag.  This is a SURGICAL EDIT, not a rewrite.

    Hard rules:
    1. Maintain the ≤5% max annual loss constraint under realistic
       historical scenarios (2008, 2020, 2022).
    2. Aim expected_max_drawdown close to (but under) 5% — do NOT waste
       the risk budget by becoming overly conservative.
    3. Address EVERY distinct issue in the critique.  If the critique
       lists three separate problems, your revision must visibly address
       all three.
    4. Preserve unflagged characteristics of the original portfolio:
       keep instruments and weights that the critique did not call out,
       unless removing them is necessary to fix something that WAS
       flagged.

    Use the rationale field to explain, point by point, how each
    critique item was addressed.  Be concrete: "Issue X — fixed by Y".

    Respond ONLY with a JSON object using the same schema as the Generator:
    {
      "allocations": {"TICKER_OR_ASSET": weight, ...},
      "descriptions": {"TICKER_OR_ASSET": "one-line plain-English description", ...},
      "expected_annual_return": float,
      "expected_max_drawdown": float,
      "methodology": "string",
      "rationale": "string — must address each critique point explicitly"
    }

    The "descriptions" map must contain one entry per ticker.
    Weights must sum to 1.0.  No markdown fences — raw JSON only.
""")


def run_refiner(
    spec: InvestmentSpec,
    selected_proposal: PortfolioProposal,
    selected_evaluation: EvaluationResult,
) -> PortfolioProposal:
    """
    Take the harness-selected portfolio plus the evaluator's critique and
    produce a single revised proposal that addresses every critique item.
    """
    print("\n" + "=" * 60)
    print("REFINER — fine-tuning the selected portfolio against critique …")
    print("=" * 60)

    user_msg = (
        f"INVESTMENT SPEC:\n{spec.raw_text}\n\n"
        f"SELECTED PORTFOLIO (currently best of {MAX_ITERATIONS}):\n"
        f"{selected_proposal.raw_text}\n\n"
        f"EVALUATOR SCORES: {selected_evaluation.scores} "
        f"(average {selected_evaluation.average_score})\n"
        f"EVALUATOR PASS JUDGEMENT: {selected_evaluation.passed}\n\n"
        f"DETAILED CRITIQUE TO ADDRESS:\n{selected_evaluation.critique}\n\n"
        f"Produce a revised portfolio that fixes every issue above while "
        f"preserving the rest.  Spell out in `rationale` how each critique "
        f"point was addressed."
    )

    raw = call_claude(REFINER_SYSTEM, user_msg)
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


def _refinement_improvements(
    orig_eval: EvaluationResult,
    refined_eval: EvaluationResult,
    orig_proposal: PortfolioProposal,
    refined_proposal: PortfolioProposal,
) -> dict[str, Any]:
    """Compute a structured before/after diff for the markdown report."""
    score_deltas: dict[str, dict[str, float]] = {}
    all_keys = set(orig_eval.scores) | set(refined_eval.scores)
    for k in all_keys:
        before = orig_eval.scores.get(k, 0)
        after = refined_eval.scores.get(k, 0)
        score_deltas[k] = {
            "before": before,
            "after": after,
            "delta": round(after - before, 2),
        }

    orig_w = orig_proposal.allocations
    new_w = refined_proposal.allocations
    all_tickers = set(orig_w) | set(new_w)
    allocation_changes: list[dict[str, Any]] = []
    for t in sorted(all_tickers, key=lambda x: -abs(new_w.get(x, 0) - orig_w.get(x, 0))):
        before = float(orig_w.get(t, 0))
        after = float(new_w.get(t, 0))
        if abs(after - before) < 1e-9:
            continue  # unchanged
        kind = "added" if before == 0 else "removed" if after == 0 else "changed"
        allocation_changes.append({
            "ticker": t,
            "before": before,
            "after": after,
            "delta": round(after - before, 4),
            "kind": kind,
        })

    return {
        "score_deltas": score_deltas,
        "average_score_before": orig_eval.average_score,
        "average_score_after": refined_eval.average_score,
        "average_score_delta": round(refined_eval.average_score - orig_eval.average_score, 2),
        "expected_return_before": orig_proposal.expected_annual_return,
        "expected_return_after": refined_proposal.expected_annual_return,
        "expected_max_drawdown_before": orig_proposal.expected_max_drawdown,
        "expected_max_drawdown_after": refined_proposal.expected_max_drawdown,
        "passed_before": orig_eval.passed,
        "passed_after": refined_eval.passed,
        "allocation_changes": allocation_changes,
    }


# ---------------------------------------------------------------------------
# AGENT 5 — ADVISOR  (advisory only, never modifies the portfolio)
# ---------------------------------------------------------------------------
ADVISOR_SYSTEM = textwrap.dedent("""\
    You are a portfolio diversification advisor.  You are NOT allowed to
    change the portfolio.  Your single job is to look at the FINAL
    portfolio (which has already passed QA or been chosen as the best
    effort) and surface two things for the human reader:

    1. A pairwise CORRELATION SNAPSHOT for tickers that move similarly.
       For every PAIR of holdings whose long-run correlation is |ρ| ≥ 0.5,
       output an entry.  Use realistic historical correlations (you may
       approximate from memory; this is a snapshot, not a backtest).
       Be honest about uncertainty — these are model-recalled, not
       computed from data.

    2. Concrete SIMPLIFICATION SUGGESTIONS.  For each cluster of highly
       correlated holdings (typically ρ ≥ 0.75) that look redundant,
       propose a specific consolidation.

    HARD RULES for suggestions:
    • Suggest a REAL replacement ticker (e.g., GOVT, AGG, VXUS, BNDX)
      that a US retail investor can buy easily.  Do not invent tickers.
    • Be EXPLICIT about what the user gives up — every suggestion MUST
      include a "tradeoff" string.  Examples of legitimate tradeoffs:
        "Loses the explicit short/intermediate Treasury barbell."
        "Loses tax-exempt muni income exposure."
        "Combines investment-grade credit with Treasuries — credit risk
         becomes implicit rather than sized separately."
    • Do NOT suggest consolidations across genuinely different risk
      factors (e.g., merging LQD into IEF collapses credit and rate
      exposure — flag it as a NOT-recommended merge if you mention it).
    • If the portfolio is already well-consolidated, return an empty
      "suggestions" list rather than inventing weak ideas.

    Respond ONLY with a JSON object:
    {
      "correlation_pairs": [
        {"a": "TICKER_A", "b": "TICKER_B", "rho": 0.85,
         "note": "optional short context"},
        ...
      ],
      "suggestions": [
        {
          "merge_from": ["TICKER_X", "TICKER_Y"],
          "merge_into": "REPLACEMENT_TICKER",
          "rationale": "one-sentence why they overlap",
          "tradeoff": "explicit description of what is lost"
        },
        ...
      ],
      "notes": "optional caveats about correlation estimates / regime sensitivity"
    }

    No markdown fences — raw JSON only.
""")


def run_advisor(final_proposal: PortfolioProposal) -> AdvisorOutput:
    """
    Inspect the final portfolio and produce advisory consolidation
    suggestions plus a pairwise correlation snapshot.  Never modifies
    the portfolio itself.
    """
    print("\n" + "=" * 60)
    print("ADVISOR — scanning final portfolio for correlation / simplification …")
    print("=" * 60)

    # Build a compact view of the holdings (ticker, weight, description)
    rows = []
    descs = final_proposal.descriptions or {}
    for ticker, weight in final_proposal.allocations.items():
        desc = descs.get(ticker, "")
        rows.append(f"  {ticker:30s}  {float(weight):.2%}   {desc}")
    holdings_block = "\n".join(rows) if rows else "  (empty)"

    user_msg = (
        f"FINAL PORTFOLIO (do NOT modify — advise only):\n{holdings_block}\n\n"
        f"Produce the correlation snapshot and simplification suggestions "
        f"per the system prompt schema.  Focus on pairs that move together "
        f"in normal regimes; flag (in notes) any pairs whose correlation "
        f"changes materially in stress."
    )

    raw = call_claude(ADVISOR_SYSTEM, user_msg)
    print(raw[:500], "…\n" if len(raw) > 500 else "\n")

    try:
        data = json.loads(raw, strict=False)
    except json.JSONDecodeError:
        import re
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(m.group(), strict=False) if m else {}

    return AdvisorOutput(
        suggestions=data.get("suggestions", []) or [],
        correlation_pairs=data.get("correlation_pairs", []) or [],
        notes=data.get("notes", "") or "",
        raw_text=raw,
    )


# ---------------------------------------------------------------------------
# STEP — PRICING & LOT-SIZE FEASIBILITY (yfinance, no LLM call)
# ---------------------------------------------------------------------------
def _fetch_one_price(ticker: str) -> tuple[float | None, str | None]:
    """
    Fetch the latest available price for one ticker via yfinance.
    Returns (price, error_message).  On success: (float, None).
    On any failure (unknown ticker, network blip, NaN result):
    (None, "human-readable reason").  Never raises.
    """
    try:
        import yfinance as yf
    except ImportError as exc:
        return None, f"yfinance not installed ({exc})"
    try:
        t = yf.Ticker(ticker)
        price: float | None = None
        # fast_info is the cheap path; supports dict and attribute access
        # across yfinance versions.
        try:
            fi = t.fast_info
            try:
                price = fi["last_price"]
            except (KeyError, TypeError):
                price = getattr(fi, "last_price", None)
        except Exception:
            price = None
        # NaN guard (yfinance sometimes returns NaN for unknown tickers).
        if price is not None and isinstance(price, float) and price != price:
            price = None
        # Fall back to a 1-day history pull if fast_info gave us nothing.
        if price is None:
            try:
                hist = t.history(period="1d")
                if not hist.empty:
                    price = float(hist["Close"].iloc[-1])
            except Exception:
                price = None
        if price is None or price <= 0:
            return None, "no price returned (ticker may be unrecognised)"
        return float(price), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def run_pricing(
    final_proposal: PortfolioProposal,
    capital: float,
) -> PricingResult:
    """
    Fetch the latest price for each ticker in the final portfolio and
    compute a whole-share lot-size feasibility check:

        target_$  = capital * weight
        shares    = floor(target_$ / price)
        actual_$  = shares * price
        actual_w  = actual_$ / capital
        drift     = actual_w - weight

    Failures are per-ticker and never crash the pipeline.  Model-invented
    pseudo-tickers (e.g. "SPX_PUT_SPREAD") are recorded as failed rows
    with their target_$ preserved for context.
    """
    print("\n" + "=" * 60)
    print(
        f"PRICING — fetching latest prices from yfinance "
        f"(capital=${capital:,.0f}) …"
    )
    print("=" * 60)

    # Up-front import check — if yfinance is missing, return a marker
    # result so the report can render a helpful note instead of a stack trace.
    try:
        import yfinance as _yf  # noqa: F401
        import logging
        # yfinance is chatty about failed tickers — quiet it down so the
        # harness log stays readable.  We surface per-ticker errors ourselves.
        logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    except ImportError as exc:
        msg = (
            f"yfinance is not installed ({exc}). Run `uv sync` from the "
            f"testbench root to install it."
        )
        print(f"  ⚠️  {msg}")
        return PricingResult(
            capital=capital,
            disclaimer=PRICING_DISCLAIMER,
            error=msg,
            fetched_at=datetime.now().isoformat(timespec="seconds"),
        )

    rows: list[TickerPricing] = []
    failed: list[str] = []

    for ticker, weight in final_proposal.allocations.items():
        w = float(weight)
        target_dollars = capital * w
        price, err = _fetch_one_price(ticker)
        if price is None:
            print(f"  ✗ {ticker:25s}  {err}")
            rows.append(TickerPricing(
                ticker=ticker,
                weight=w,
                status="error",
                target_dollars=round(target_dollars, 2),
                error=err,
            ))
            failed.append(ticker)
            continue
        shares = int(target_dollars // price)
        actual_dollars = shares * price
        print(
            f"  ✓ {ticker:25s}  ${price:>10,.2f}   "
            f"{shares:>6d} sh   ${actual_dollars:>12,.2f}"
        )
        rows.append(TickerPricing(
            ticker=ticker,
            weight=w,
            status="ok",
            price=round(price, 4),
            target_dollars=round(target_dollars, 2),
            shares=shares,
            actual_dollars=round(actual_dollars, 2),
        ))

    total_invested = sum(r.actual_dollars for r in rows)
    leftover_cash = capital - total_invested
    # Fill in actual_weight / weight_drift now that the totals are known.
    for r in rows:
        if r.status == "ok" and capital > 0:
            r.actual_weight = round(r.actual_dollars / capital, 6)
            r.weight_drift = round(r.actual_weight - r.weight, 6)
    max_abs_drift = max(
        (abs(r.weight_drift) for r in rows if r.status == "ok"),
        default=0.0,
    )

    print(f"\n  Total invested  : ${total_invested:>12,.2f}")
    print(f"  Leftover cash   : ${leftover_cash:>12,.2f}")
    print(f"  Max |Δ weight|  : {max_abs_drift:.2%}")
    if failed:
        print(f"  Failed tickers  : {', '.join(failed)}")

    return PricingResult(
        capital=capital,
        total_invested=round(total_invested, 2),
        leftover_cash=round(leftover_cash, 2),
        max_abs_drift=round(max_abs_drift, 6),
        rows=rows,
        failed_tickers=failed,
        disclaimer=PRICING_DISCLAIMER,
        source="yfinance",
        fetched_at=datetime.now().isoformat(timespec="seconds"),
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


def run_harness(
    user_goal: str,
    *,
    refine: bool = True,
    advise: bool = True,
    price: bool = True,
    capital: float = DEFAULT_CAPITAL,
) -> dict[str, Any]:
    """
    Main entry point.  Runs the full Planner → Generator ↔ Evaluator loop,
    then (by default) a post-selection REFINER pass, an ADVISOR pass, and
    a PRICING / lot-size feasibility pass.

    Flow:
      1. Planner expands the goal into a full investment spec.
      2. MAX_ITERATIONS rounds of Generator ↔ Evaluator.  Always runs
         all rounds; never breaks early.
      3. Select the best PASSING iteration whose expected_max_drawdown
         is closest to TARGET_MAX_LOSS.  Falls back to the last iteration
         if nothing passed.
      4. If `refine=True`, run a single Refiner pass on the selected
         portfolio: Refiner addresses every critique point, then the
         Evaluator re-scores.  If the refined version passes QA, it is
         PROMOTED to `final_proposal`; otherwise the selected one stays
         as the final answer.
      5. If `advise=True`, run a single ADVISOR pass on the final
         portfolio.  The Advisor is read-only — it never modifies the
         portfolio.  It returns a pairwise correlation snapshot and a
         list of structured "merge X+Y into Z" suggestions with explicit
         trade-offs, so the human reader can decide whether to apply any.
      6. If `price=True`, fetch the latest price for each ticker in the
         final portfolio via yfinance and compute a whole-share lot-size
         feasibility check against `capital` USD.  Per-ticker failures
         (unknown ticker, network blip, model-invented pseudo-ticker) are
         recorded gracefully and never abort the pipeline.
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
        selected_proposal = proposals[selected_idx - 1]
        selected_evaluation = evaluations[selected_idx - 1]
        print(
            f"\n🎯  Selected iteration {selected_idx} of {MAX_ITERATIONS}: "
            f"passing portfolio with expected_max_drawdown "
            f"{selected_proposal.expected_max_drawdown:.2%} "
            f"(closest to {TARGET_MAX_LOSS:.0%} target).\n"
        )
    else:
        # Fall back to the last iteration when nothing passed.
        history[-1]["selected"] = True
        selected_proposal = proposals[-1]
        selected_evaluation = evaluations[-1]
        print(
            f"\n⚠️  Reached max iterations ({MAX_ITERATIONS}) without any "
            f"passing portfolio. Returning last iteration.\n"
        )

    # --- Step 5: Post-selection Refinement ---
    final_proposal = selected_proposal
    final_evaluation = selected_evaluation
    refinement_block: dict[str, Any] = {
        "performed": False,
        "skipped_reason": None,
        "promoted": False,
        "refined_proposal": None,
        "refined_evaluation": None,
        "improvements": None,
    }

    if not refine:
        refinement_block["skipped_reason"] = "disabled via --no-refine / --test"
        print("\n(Refinement step skipped.)\n")
    elif not selected_evaluation.critique:
        refinement_block["skipped_reason"] = "no critique available to refine against"
        print("\n(Refinement step skipped — no critique available.)\n")
    else:
        refined_proposal = run_refiner(spec, selected_proposal, selected_evaluation)
        refined_evaluation = run_evaluator(spec, refined_proposal)

        print(f"\n--- Refinement result ---")
        print(f"  Scores              : {refined_evaluation.scores}")
        print(f"  Average             : {refined_evaluation.average_score}")
        print(f"  Passed              : {refined_evaluation.passed}")
        print(f"  Expected max loss   : {refined_proposal.expected_max_drawdown:.2%}")

        improvements = _refinement_improvements(
            selected_evaluation, refined_evaluation,
            selected_proposal, refined_proposal,
        )

        # Promote the refined version only if it passes QA AND its drawdown
        # is still within the target (we don't want refinement to wander out
        # of the risk budget while "fixing" things).
        refined_dd = float(refined_proposal.expected_max_drawdown or 0)
        promote = (
            refined_evaluation.passed
            and refined_dd <= TARGET_MAX_LOSS
        )

        refinement_block.update({
            "performed": True,
            "promoted": promote,
            "refined_proposal": asdict(refined_proposal),
            "refined_evaluation": asdict(refined_evaluation),
            "improvements": improvements,
        })

        if promote:
            final_proposal = refined_proposal
            final_evaluation = refined_evaluation
            print(
                f"\n✨  Refined portfolio PROMOTED to final "
                f"(passed QA, drawdown {refined_dd:.2%} ≤ {TARGET_MAX_LOSS:.0%}).\n"
            )
        else:
            reasons = []
            if not refined_evaluation.passed:
                reasons.append("failed QA")
            if refined_dd > TARGET_MAX_LOSS:
                reasons.append(f"drawdown {refined_dd:.2%} > target")
            print(
                f"\n🔒  Refined version NOT promoted ({', '.join(reasons)}). "
                f"Keeping selected iteration {selected_idx} as final.\n"
            )

    # --- Step 6: Advisor (read-only, advisory only) ---
    advisor_block: dict[str, Any] = {
        "performed": False,
        "skipped_reason": None,
        "suggestions": [],
        "correlation_pairs": [],
        "notes": "",
        "raw_text": "",
    }
    if not advise:
        advisor_block["skipped_reason"] = "disabled via --no-advisor / --test"
        print("\n(Advisor step skipped.)\n")
    elif not final_proposal.allocations:
        advisor_block["skipped_reason"] = "no allocations to advise on"
        print("\n(Advisor step skipped — no allocations.)\n")
    else:
        advisor_output = run_advisor(final_proposal)
        advisor_block.update({
            "performed": True,
            "suggestions": advisor_output.suggestions,
            "correlation_pairs": advisor_output.correlation_pairs,
            "notes": advisor_output.notes,
            "raw_text": advisor_output.raw_text,
        })
        n_pairs = len(advisor_output.correlation_pairs)
        n_sugg = len(advisor_output.suggestions)
        print(
            f"\n💡  Advisor returned {n_pairs} correlated pair(s) and "
            f"{n_sugg} consolidation suggestion(s).  The portfolio was "
            f"NOT modified — see the report for details.\n"
        )

    # --- Step 7: Pricing & lot-size feasibility (yfinance) ---
    pricing_block: dict[str, Any] = {
        "performed": False,
        "skipped_reason": None,
        "capital": capital,
        "total_invested": 0.0,
        "leftover_cash": 0.0,
        "max_abs_drift": 0.0,
        "rows": [],
        "failed_tickers": [],
        "disclaimer": PRICING_DISCLAIMER,
        "source": "yfinance",
        "fetched_at": "",
        "error": None,
    }
    if not price:
        pricing_block["skipped_reason"] = "disabled via --no-prices / --test"
        print("\n(Pricing step skipped.)\n")
    elif not final_proposal.allocations:
        pricing_block["skipped_reason"] = "no allocations to price"
        print("\n(Pricing step skipped — no allocations.)\n")
    else:
        pricing_result = run_pricing(final_proposal, capital)
        pricing_block = {
            "performed": True,
            "skipped_reason": None,
            **asdict(pricing_result),
        }

    return {
        "spec": asdict(spec),
        "final_proposal": asdict(final_proposal),
        "final_evaluation": asdict(final_evaluation),
        "selected_iteration": selected_idx,
        "selected_proposal": asdict(selected_proposal),
        "selected_evaluation": asdict(selected_evaluation),
        "target_max_loss": TARGET_MAX_LOSS,
        "iteration_history": history,
        "refinement": refinement_block,
        "advisor": advisor_block,
        "pricing": pricing_block,
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
    refinement = result.get("refinement") or {}
    refined_promoted = bool(refinement.get("promoted"))

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
    if refinement.get("performed"):
        if refined_promoted:
            push("- **Refinement:** performed — refined portfolio PROMOTED to final")
        else:
            push("- **Refinement:** performed — refined version NOT promoted (kept selected as final)")
    elif refinement.get("skipped_reason"):
        push(f"- **Refinement:** skipped ({refinement['skipped_reason']})")
    advisor_hdr = result.get("advisor") or {}
    if advisor_hdr.get("performed"):
        n_sugg = len(advisor_hdr.get("suggestions") or [])
        n_pairs = len(advisor_hdr.get("correlation_pairs") or [])
        push(
            f"- **Advisor:** performed — {n_sugg} consolidation "
            f"suggestion(s), {n_pairs} correlated pair(s) (advisory only)"
        )
    elif advisor_hdr.get("skipped_reason"):
        push(f"- **Advisor:** skipped ({advisor_hdr['skipped_reason']})")
    pricing_hdr = result.get("pricing") or {}
    if pricing_hdr.get("performed"):
        n_failed = len(pricing_hdr.get("failed_tickers") or [])
        cap_h = pricing_hdr.get("capital", 0.0) or 0.0
        suffix = f", {n_failed} ticker(s) unpriced" if n_failed else ""
        push(
            f"- **Pricing:** performed — yfinance quotes for "
            f"${cap_h:,.0f} capital lot-size check{suffix}"
        )
    elif pricing_hdr.get("skipped_reason"):
        push(f"- **Pricing:** skipped ({pricing_hdr['skipped_reason']})")
    push(f"- **Target max loss:** {target:.1%}")
    push(f"- **Pass threshold:** average score ≥ {PASS_THRESHOLD} with no single score ≤ 4 AND evaluator says passed")
    push("")

    # ---- Final portfolio ----
    if refined_promoted:
        push("## Final Portfolio (refined)")
    else:
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

    # ---- Post-selection refinement ----
    if refinement.get("performed"):
        push("## Post-Selection Refinement")
        push("")
        if refined_promoted:
            push(
                "The Refiner addressed every critique point above and the "
                "Evaluator re-scored the result. **The refined portfolio "
                "passed QA and was promoted to `Final Portfolio` (top of "
                "this report).** Section below shows the before/after."
            )
        else:
            push(
                "The Refiner addressed every critique point above, but the "
                "refined portfolio **did not pass QA on re-evaluation** (or "
                "exceeded the 5% drawdown target), so the originally "
                "selected portfolio was kept as the final answer. Section "
                "below shows what the Refiner produced for comparison."
            )
        push("")

        imp = refinement.get("improvements") or {}
        ref_p = refinement.get("refined_proposal") or {}
        ref_e = refinement.get("refined_evaluation") or {}

        # Score deltas table
        score_deltas = imp.get("score_deltas") or {}
        if score_deltas:
            push("### Score deltas (Selected → Refined)")
            push("")
            push("| Criterion | Selected | Refined | Δ |")
            push("|-----------|---------:|--------:|--:|")
            for k, d in score_deltas.items():
                delta = d.get("delta", 0)
                sign = "+" if delta > 0 else ""
                push(
                    f"| {k.replace('_', ' ')} | {d.get('before', '?')} | "
                    f"{d.get('after', '?')} | {sign}{delta} |"
                )
            avg_b = imp.get("average_score_before", 0)
            avg_a = imp.get("average_score_after", 0)
            avg_d = imp.get("average_score_delta", 0)
            sign = "+" if avg_d > 0 else ""
            push(f"| **Average** | **{avg_b}** | **{avg_a}** | **{sign}{avg_d}** |")
            push("")

        # Headline metric deltas
        push("### Portfolio metric deltas")
        push("")
        try:
            er_b = float(imp.get("expected_return_before", 0))
            er_a = float(imp.get("expected_return_after", 0))
            dd_b = float(imp.get("expected_max_drawdown_before", 0))
            dd_a = float(imp.get("expected_max_drawdown_after", 0))
            push("| Metric | Selected | Refined | Δ |")
            push("|--------|---------:|--------:|--:|")
            push(
                f"| Expected annual return | {er_b:.2%} | {er_a:.2%} | "
                f"{'+' if er_a >= er_b else ''}{(er_a - er_b):.2%} |"
            )
            push(
                f"| Expected max drawdown | {dd_b:.2%} | {dd_a:.2%} | "
                f"{'+' if dd_a >= dd_b else ''}{(dd_a - dd_b):.2%} |"
            )
            push(
                f"| Distance to {target:.0%} target | "
                f"{abs(dd_b - target):.2%} | {abs(dd_a - target):.2%} | "
                f"{'+' if abs(dd_a - target) >= abs(dd_b - target) else ''}"
                f"{(abs(dd_a - target) - abs(dd_b - target)):.2%} |"
            )
            push(
                f"| Passed QA | {imp.get('passed_before')} | "
                f"{imp.get('passed_after')} | — |"
            )
            push("")
        except (TypeError, ValueError):
            push("_(Could not compute metric deltas — see raw values below.)_")
            push("")

        # Allocation changes
        changes = imp.get("allocation_changes") or []
        if changes:
            push("### Allocation changes")
            push("")
            push("| Ticker | Selected | Refined | Δ Weight | Kind |")
            push("|--------|---------:|--------:|---------:|------|")
            for c in changes:
                before = float(c.get("before", 0))
                after = float(c.get("after", 0))
                delta = float(c.get("delta", 0))
                sign = "+" if delta > 0 else ""
                before_s = f"{before:.2%}" if before > 0 else "—"
                after_s = f"{after:.2%}" if after > 0 else "—"
                push(
                    f"| `{c.get('ticker')}` | {before_s} | {after_s} | "
                    f"{sign}{delta:.2%} | {c.get('kind')} |"
                )
            push("")

        # Refined methodology / rationale
        if ref_p.get("methodology"):
            push("### Refined methodology")
            push("")
            push(_format_value(ref_p["methodology"]))
            push("")
        if ref_p.get("rationale"):
            push("### Refined rationale (point-by-point response to critique)")
            push("")
            push(_format_value(ref_p["rationale"]))
            push("")

        # Refined evaluator report
        if ref_e.get("scores"):
            push("### Re-evaluator scores")
            push("")
            push("| Criterion | Score |")
            push("|-----------|------:|")
            for k, v in ref_e["scores"].items():
                push(f"| {k.replace('_', ' ')} | {v} |")
            push(f"| **Average** | **{ref_e.get('average_score', 0)}** |")
            push(f"| **Passed** | **{ref_e.get('passed', False)}** |")
            push("")
        if ref_e.get("critique"):
            push("### Re-evaluator critique")
            push("")
            push(_format_value(ref_e["critique"]))
            push("")

        if ref_p.get("raw_text") or ref_e.get("raw_text"):
            push("<details><summary>Refiner & re-evaluator raw responses</summary>")
            push("")
            if ref_p.get("raw_text"):
                push("```")
                push("--- Refiner raw response ---")
                push(ref_p["raw_text"].rstrip())
                push("```")
                push("")
            if ref_e.get("raw_text"):
                push("```")
                push("--- Re-evaluator raw response ---")
                push(ref_e["raw_text"].rstrip())
                push("```")
                push("")
            push("</details>")
            push("")

    # ---- Advisor (simplification suggestions + correlation snapshot) ----
    advisor = result.get("advisor") or {}
    if advisor.get("performed"):
        push("## Simplification Suggestions (advisory — not applied)")
        push("")
        push(
            "The Advisor inspected the **final portfolio** and produced "
            "the suggestions below.  These are advisory only — the "
            "portfolio above has NOT been modified.  Decide which (if "
            "any) to apply yourself."
        )
        push("")

        suggestions = advisor.get("suggestions") or []
        if suggestions:
            for idx, s in enumerate(suggestions, start=1):
                merge_from = s.get("merge_from") or []
                merge_into = s.get("merge_into") or ""
                from_str = ", ".join(f"`{t}`" for t in merge_from) or "_(none)_"
                push(f"### Suggestion {idx}: {from_str} → `{merge_into}`")
                push("")
                if s.get("rationale"):
                    push(f"- **Why:** {s['rationale']}")
                if s.get("tradeoff"):
                    push(f"- **Tradeoff:** {s['tradeoff']}")
                push("")
        else:
            push("_The Advisor did not propose any consolidations — the "
                 "portfolio is already well-organised by this measure._")
            push("")

        pairs = advisor.get("correlation_pairs") or []
        if pairs:
            push("### Correlation snapshot")
            push("")
            push(
                "Approximate long-run correlations (model-recalled, not "
                "computed).  Pairs with |ρ| ≥ 0.5 are shown; sorted by "
                "strongest first."
            )
            push("")
            push("| Ticker A | Ticker B | ρ | Note |")
            push("|----------|----------|---:|------|")
            try:
                pairs_sorted = sorted(
                    pairs,
                    key=lambda p: -abs(float(p.get("rho", 0))),
                )
            except (TypeError, ValueError):
                pairs_sorted = pairs
            for p in pairs_sorted:
                try:
                    rho = float(p.get("rho", 0))
                    rho_s = f"{rho:+.2f}"
                except (TypeError, ValueError):
                    rho_s = str(p.get("rho", ""))
                push(
                    f"| `{p.get('a', '')}` | `{p.get('b', '')}` | "
                    f"{rho_s} | {p.get('note', '') or ''} |"
                )
            push("")

        if advisor.get("notes"):
            push("### Advisor notes")
            push("")
            push(_format_value(advisor["notes"]))
            push("")

        if advisor.get("raw_text"):
            push("<details><summary>Advisor raw response</summary>")
            push("")
            push("```")
            push(advisor["raw_text"].rstrip())
            push("```")
            push("")
            push("</details>")
            push("")
    elif advisor.get("skipped_reason"):
        push("## Simplification Suggestions (advisory)")
        push("")
        push(f"_Advisor pass skipped — {advisor['skipped_reason']}._")
        push("")

    # ---- Pricing & lot-size feasibility ----
    pricing = result.get("pricing") or {}
    if pricing.get("performed"):
        push("## Latest Prices & Lot-Size Feasibility")
        push("")
        if pricing.get("disclaimer"):
            push(f"> ⚠️ **Data source disclaimer.** {pricing['disclaimer']}")
            push("")

        cap = float(pricing.get("capital", 0) or 0)
        total_inv = float(pricing.get("total_invested", 0) or 0)
        leftover = float(pricing.get("leftover_cash", 0) or 0)
        max_drift = float(pricing.get("max_abs_drift", 0) or 0)
        fetched = pricing.get("fetched_at", "")
        failed_tickers = pricing.get("failed_tickers") or []

        push(f"- **Assumed capital:** ${cap:,.2f}")
        push(f"- **Total invested (whole shares):** ${total_inv:,.2f}")
        push(f"- **Leftover cash:** ${leftover:,.2f}")
        push(f"- **Max |weight drift|:** {max_drift:.2%}")
        if fetched:
            push(f"- **Fetched at:** {fetched}")
        if failed_tickers:
            ft = ", ".join(f"`{t}`" for t in failed_tickers)
            push(f"- **Unpriced tickers:** {ft}")
        push("")

        rows_p = pricing.get("rows") or []
        if rows_p:
            push("| Ticker | Price | Target W. | Target $ | Shares | "
                 "Actual $ | Actual W. | Δ Weight | Status |")
            push("|--------|------:|----------:|---------:|------:|"
                 "---------:|----------:|---------:|--------|")
            for r in rows_p:
                ticker = r.get("ticker", "")
                status = r.get("status", "ok")
                weight = float(r.get("weight", 0) or 0)
                target_d = float(r.get("target_dollars", 0) or 0)
                if status == "ok":
                    price_v = float(r.get("price", 0) or 0)
                    shares_v = int(r.get("shares", 0) or 0)
                    actual_d = float(r.get("actual_dollars", 0) or 0)
                    actual_w = float(r.get("actual_weight", 0) or 0)
                    drift = float(r.get("weight_drift", 0) or 0)
                    sign = "+" if drift > 0 else ""
                    push(
                        f"| `{ticker}` | ${price_v:,.2f} | "
                        f"{weight:.2%} | ${target_d:,.2f} | "
                        f"{shares_v:,d} | ${actual_d:,.2f} | "
                        f"{actual_w:.2%} | {sign}{drift:.2%} | ok |"
                    )
                else:
                    err = r.get("error") or "unpriced"
                    push(
                        f"| `{ticker}` | — | {weight:.2%} | "
                        f"${target_d:,.2f} | — | — | — | — | {err} |"
                    )
            push("")
    elif pricing.get("skipped_reason"):
        push("## Latest Prices & Lot-Size Feasibility")
        push("")
        push(f"_Pricing pass skipped — {pricing['skipped_reason']}._")
        push("")
    elif pricing.get("error"):
        push("## Latest Prices & Lot-Size Feasibility")
        push("")
        push(f"_Pricing pass could not run — {pricing['error']}_")
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
              uv run python long_running_agent/harness.py --no-refine
              uv run python long_running_agent/harness.py --no-advisor
              uv run python long_running_agent/harness.py --no-prices
              uv run python long_running_agent/harness.py --capital 250000
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
    parser.add_argument(
        "--no-refine",
        action="store_true",
        help=(
            "Skip the post-selection Refiner pass. By default, after the best "
            "iteration is selected, a Refiner agent addresses every critique "
            "point and the Evaluator re-scores; --no-refine disables that. "
            "--test implies --no-refine."
        ),
    )
    parser.add_argument(
        "--no-advisor",
        action="store_true",
        help=(
            "Skip the post-selection Advisor pass. By default, after the "
            "final portfolio is determined, an Advisor agent produces a "
            "pairwise correlation snapshot and concrete consolidation "
            "suggestions (advisory only — never modifies the portfolio). "
            "--test implies --no-advisor."
        ),
    )
    parser.add_argument(
        "--no-prices",
        action="store_true",
        help=(
            "Skip the post-selection Pricing pass. By default, after the "
            "final portfolio is determined, the latest prices for each "
            "ticker are fetched from Yahoo Finance via yfinance and a "
            "whole-share lot-size feasibility check is performed using "
            "--capital. Per-ticker failures degrade gracefully. "
            "--test implies --no-prices."
        ),
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=DEFAULT_CAPITAL,
        metavar="USD",
        help=(
            f"Assumed investable capital in USD for the lot-size "
            f"feasibility check (default ${DEFAULT_CAPITAL:,.0f}). Only "
            f"used when pricing is enabled."
        ),
    )
    args = parser.parse_args()

    # Apply --test first (it takes precedence), then individual overrides.
    refine = not args.no_refine
    advise = not args.no_advisor
    price = not args.no_prices
    capital = args.capital
    if args.test:
        MODEL = _MODEL_ALIASES["haiku"]
        MAX_ITERATIONS = 1
        refine = False   # --test always implies --no-refine
        advise = False   # --test always implies --no-advisor
        price = False    # --test always implies --no-prices
        print(
            f"[TEST MODE] model={MODEL}  iterations={MAX_ITERATIONS}  "
            f"refine={refine}  advise={advise}  price={price}"
        )
    else:
        if args.model:
            MODEL = _MODEL_ALIASES.get(args.model, args.model)
            print(f"[model override] {MODEL}")
        if args.iterations is not None:
            if args.iterations < 1:
                parser.error("--iterations must be ≥ 1")
            MAX_ITERATIONS = args.iterations
            print(f"[iterations override] {MAX_ITERATIONS}")
        if capital <= 0:
            parser.error("--capital must be > 0")
        if not refine:
            print("[refinement disabled]")
        if not advise:
            print("[advisor disabled]")
        if not price:
            print("[pricing disabled]")
        else:
            print(f"[pricing enabled  capital=${capital:,.0f}]")

    goal = (
        "Optimise a portfolio for a US-based retail investor. "
        "Maximise annual return while ensuring the portfolio can lose "
        "no more than 5% of its invested value in any given year. "
        "Use any instruments available to a typical retail investor "
        "(stocks, ETFs, bonds, options overlays, etc.)."
    )

    result = run_harness(
        goal,
        refine=refine,
        advise=advise,
        price=price,
        capital=capital,
    )

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

    pricing_summary = result.get("pricing") or {}
    if pricing_summary.get("performed"):
        n_failed = len(pricing_summary.get("failed_tickers") or [])
        print("\n  Lot-size feasibility (yfinance):")
        print(
            f"    capital=${pricing_summary.get('capital', 0):,.0f}  "
            f"invested=${pricing_summary.get('total_invested', 0):,.2f}  "
            f"leftover=${pricing_summary.get('leftover_cash', 0):,.2f}  "
            f"max|Δw|={pricing_summary.get('max_abs_drift', 0):.2%}  "
            f"unpriced={n_failed}"
        )

    print("\nFull trace saved to:")
    print("  - harness_output.json   (machine-readable)")
    print("  - harness_output.md     (human-readable)")
