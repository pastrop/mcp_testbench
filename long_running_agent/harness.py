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
import re
import sys
import textwrap
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any

import anthropic

from pricing import DEFAULT_CAPITAL, PRICING_DISCLAIMER, run_pricing
from report import write_markdown_report

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL = "claude-opus-4-7"
# Per-agent model overrides.  The Planner is mostly recall + JSON
# structuring and the Advisor is pattern-matching against training
# memory — neither needs Opus.  Generator / Evaluator / Refiner do the
# real reasoning work and stay on MODEL (Opus by default).
PLANNER_MODEL = "claude-sonnet-4-6"
ADVISOR_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 4096
# The Refiner emits a full portfolio (allocations + descriptions + numbers)
# AND a point-by-point response to every critique item — by far the most
# output-heavy agent.  4096 tokens regularly truncates mid-string, which
# previously crashed the JSON parser.  Give it more headroom.
REFINER_MAX_TOKENS = 8192
MAX_ITERATIONS = 3          # generator ↔ evaluator rounds
PASS_THRESHOLD = 7          # minimum average score (out of 10) to pass QA
TARGET_MAX_LOSS = 0.05      # 5% — the loss budget we want expected_max_drawdown to land on
UNDER_UTILISATION_BAND = 0.04  # below this we consider the risk budget under-utilised
# Threshold for which Advisor-flagged correlation pairs count as
# actionable feedback for the next Generator iteration.  The Advisor
# surfaces pairs at |ρ| ≥ 0.5 for the report, but for prompt feedback
# we only want the egregious overlaps (≥ 0.7) so the next prompt
# isn't cluttered with marginal pairs.
ADVISOR_FEEDBACK_RHO_THRESHOLD = 0.7

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


def call_claude(
    system: str,
    user: str,
    *,
    model: str | None = None,
    max_tokens: int = MAX_TOKENS,
) -> str:
    """
    Wrapper around the Messages API with exponential-backoff retry on
    transient errors (529 Overloaded, 429 rate limits, 5xx, connection
    blips).  Re-raises immediately on terminal errors (auth, bad request,
    etc.) so we fail fast on real bugs.

    ``model`` defaults to the module-level ``MODEL`` (resolved at call
    time so CLI patches still apply) but individual agents can request
    a cheaper / faster tier — the Planner runs on Sonnet and the Advisor
    on Haiku by default, since neither needs Opus's reasoning depth.

    ``max_tokens`` defaults to ``MAX_TOKENS`` but agents that emit
    larger outputs (notably the Refiner) can request more so their JSON
    responses don't truncate mid-string.
    """
    # Resolve the model at call time, not at function-definition time —
    # otherwise the CLI's --model / --test patches to the MODEL global
    # would be invisible here.
    effective_model = model if model is not None else MODEL
    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
        try:
            resp = client.messages.create(
                model=effective_model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            # Surface truncation explicitly — otherwise it presents as
            # malformed JSON downstream and is hard to diagnose.  Include
            # the model name so mixed-model runs are easier to debug.
            if getattr(resp, "stop_reason", None) == "max_tokens":
                print(
                    f"  ⚠️  {effective_model}: response hit "
                    f"max_tokens={max_tokens} — output likely truncated. "
                    f"Consider raising max_tokens for this call.",
                    flush=True,
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
# Helper: best-effort JSON parse for model responses
# ---------------------------------------------------------------------------
def _parse_json_response(raw: str, *, agent: str = "agent") -> dict[str, Any]:
    """
    Parse a model response that's supposed to be JSON.  Two attempts:

      1. Strict ``json.loads`` on the whole string.
      2. Greedy ``{...}`` regex extract, then ``json.loads`` on that span.

    If BOTH fail (e.g., the response was truncated mid-string by
    ``max_tokens`` and the regex picks up a partial slice), this function
    logs a clear diagnostic and returns ``{}`` so the caller can degrade
    gracefully — the orchestrator already handles empty/missing fields
    via dataclass defaults.

    The ``agent`` label is only used for the log message.
    """
    # Attempt 1: strict parse
    try:
        return json.loads(raw, strict=False)
    except json.JSONDecodeError:
        pass

    # Attempt 2: greedy regex fallback
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(), strict=False)
        except json.JSONDecodeError:
            pass

    # Total failure — log and degrade gracefully.
    print(
        f"  ⚠️  {agent}: could not parse JSON from response "
        f"({len(raw):,} chars). Returning empty dict so the pipeline "
        f"continues. First 300 chars of response follow:\n"
        f"  {raw[:300]!r}",
        flush=True,
    )
    return {}


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

    raw = call_claude(PLANNER_SYSTEM, user_goal, model=PLANNER_MODEL)
    print(raw[:500], "…\n" if len(raw) > 500 else "\n")

    data = _parse_json_response(raw, agent="planner")

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

    DIVERSIFICATION — IMPORTANT:
    The portfolio must be diversified across genuinely independent risk
    factors, not just across many tickers.  LLMs cannot reliably estimate
    pairwise correlations from memory, so DO NOT try.  Instead, use this
    explicit rule:

        From each overlap group below, choose AT MOST ONE ticker.

        US broad equity:           VOO, VTI, SPY, IVV, SPLG, ITOT, SCHB
        US large-cap factor tilts: QUAL, MTUM, VLUE, USMV, SPHQ, SPLV
        US dividend tilts:         SCHD, DGRO, VYM, HDV, NOBL, DVY
        US small-cap:              IWM, VB, IJR, SCHA, VTWO
        Int'l developed equity:    VEA, IEFA, VXUS, SCHF, IDEV
        Emerging-market equity:    VWO, IEMG, EEM, SCHE, SPEM
        Intermediate Treasuries:   IEF, GOVT, VGIT, SCHR
        Long Treasuries:           TLT, EDV, VGLT, SPTL
        Short Treasuries / cash:   SHV, SHY, BIL, SGOV, GBIL
        Investment-grade credit:   LQD, VCIT, VCSH, IGIB, IGSB
        High-yield credit:         HYG, JNK, USHY, SHYG
        US aggregate bonds:        AGG, BND, SCHZ, IUSB
        TIPS / inflation-linked:   TIP, SCHP, VTIP, STIP, LTPZ
        Municipal bonds:           MUB, VTEB, TFI, SUB
        Gold:                      GLD, IAU, GLDM, SGOL, BAR
        Broad commodities:         DBC, PDBC, GSG, BCI, COMT
        US REITs:                  VNQ, IYR, SCHH, XLRE, RWR
        Managed futures:           DBMF, KMLM, CTA, WTMF

    Picking VOO + QUAL + SCHD is NOT diversification — all three are
    ~0.85-0.95 correlated US large-cap equity.  Pick one.  Same for
    IEF + GOVT, TLT + EDV, LQD + VCIT, GLD + IAU, etc.

    Across groups, also be deliberate: do not combine instruments whose
    main risk factor is the same in different wrappers (e.g., HYG +
    high-equity-beta credit is mostly equity risk; LTPZ + EDV is mostly
    long-duration rate risk).  Spread across genuinely independent
    factors — equity, duration, credit, inflation-linked, gold,
    commodities, managed futures.

    If you must pick a ticker not on these lists, do so — but state
    explicitly in the rationale why it does not overlap with anything
    already in your allocation.


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

    data = _parse_json_response(raw, agent="generator")

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

    data = _parse_json_response(raw, agent="evaluator")

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

    raw = call_claude(REFINER_SYSTEM, user_msg, max_tokens=REFINER_MAX_TOKENS)
    print(raw[:600], "…\n" if len(raw) > 600 else "\n")

    data = _parse_json_response(raw, agent="refiner")

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

    raw = call_claude(ADVISOR_SYSTEM, user_msg, model=ADVISOR_MODEL)
    print(raw[:500], "…\n" if len(raw) > 500 else "\n")

    data = _parse_json_response(raw, agent="advisor")

    return AdvisorOutput(
        suggestions=data.get("suggestions", []) or [],
        correlation_pairs=data.get("correlation_pairs", []) or [],
        notes=data.get("notes", "") or "",
        raw_text=raw,
    )


# ---------------------------------------------------------------------------
# ORCHESTRATOR — the harness loop
# ---------------------------------------------------------------------------
def _format_advisor_feedback(advisor_output: AdvisorOutput | None) -> str:
    """
    Format the Advisor's correlation findings as a concrete, actionable
    block for the next Generator iteration's prompt.  Only pairs whose
    absolute correlation is ≥ ``ADVISOR_FEEDBACK_RHO_THRESHOLD`` (default
    0.7) are surfaced — below that we don't want to clutter the prompt
    with marginal overlaps.

    Returns "" when the Advisor is missing, found nothing actionable,
    or wasn't run.
    """
    if advisor_output is None:
        return ""
    pairs = []
    for p in (advisor_output.correlation_pairs or []):
        try:
            rho = float(p.get("rho", 0) or 0)
        except (TypeError, ValueError):
            continue
        if abs(rho) >= ADVISOR_FEEDBACK_RHO_THRESHOLD:
            pairs.append((p.get("a", ""), p.get("b", ""), rho))
    suggestions = advisor_output.suggestions or []
    if not pairs and not suggestions:
        return ""

    lines: list[str] = [
        "ADVISOR FINDINGS — OVERLAPPING HOLDINGS IN YOUR PREVIOUS PORTFOLIO:",
        "",
        (
            f"The previous portfolio contains highly correlated holdings "
            f"(|ρ| ≥ {ADVISOR_FEEDBACK_RHO_THRESHOLD:.2f}). Each pair "
            f"represents redundant exposure — collapse each pair into "
            f"ONE ticker in your next iteration."
        ),
        "",
    ]
    if pairs:
        lines.append("Correlated pairs to consolidate:")
        for a, b, rho in sorted(pairs, key=lambda x: -abs(x[2])):
            lines.append(f"  • {a} ↔ {b}  (ρ ≈ {rho:+.2f})")
        lines.append("")
    if suggestions:
        lines.append("Specific consolidation suggestions:")
        for s in suggestions:
            merge_from = " + ".join(s.get("merge_from") or []) or "(unspecified)"
            merge_into = s.get("merge_into") or "(unspecified)"
            tradeoff = s.get("tradeoff") or ""
            line = f"  • Replace {merge_from} → {merge_into}"
            if tradeoff:
                line += f"  (tradeoff: {tradeoff})"
            lines.append(line)
        lines.append("")
    return "\n".join(lines)


def _build_feedback(
    evaluation: EvaluationResult,
    proposal: PortfolioProposal,
    advisor_output: AdvisorOutput | None = None,
) -> str:
    """
    Produce the next round's feedback string based on the current evaluation.

    Three regimes (selects the BASE feedback text):
      • Failed QA          → pass the critique through unchanged (today's behaviour).
      • Passed but over 5% → tell the generator to bring drawdown down to ~5%
                              without sacrificing scores.
      • Passed but well
        under 5%           → tell the generator the risk budget is being wasted
                              and to push drawdown closer to (but under) 5%.
      • Passed and near 5% → still ask for a refinement attempt — the selector
                              will keep the best across iterations.

    If ``advisor_output`` is provided, its concrete correlation-pair
    findings (≥ ``ADVISOR_FEEDBACK_RHO_THRESHOLD``) are prepended to the
    base feedback.  This converts the Advisor from a one-shot report
    decoration into a real signal in the generator ↔ evaluator loop —
    the Generator gets actual overlapping pairs to fix in the next
    iteration, instead of a vague "avoid correlation" rule it cannot
    apply (LLMs can't reliably estimate ρ from memory).
    """
    if not evaluation.passed:
        base = evaluation.critique
    else:
        dd = proposal.expected_max_drawdown
        if dd > TARGET_MAX_LOSS:
            overshoot_pct = (dd - TARGET_MAX_LOSS) * 100
            base = (
                f"QA PASSED with average score {evaluation.average_score}, "
                f"BUT expected_max_drawdown is {dd:.2%}, which exceeds the "
                f"{TARGET_MAX_LOSS:.0%} loss target by {overshoot_pct:.1f} "
                f"percentage points. Your top priority this round is to "
                f"REDUCE expected_max_drawdown as close to {TARGET_MAX_LOSS:.0%} "
                f"as possible WITHOUT crossing it, while keeping every QA "
                f"score ≥ {PASS_THRESHOLD}. Accept lower expected return if "
                f"necessary. Prior critique for reference:\n{evaluation.critique}"
            )
        elif dd < UNDER_UTILISATION_BAND:
            base = (
                f"QA PASSED with average score {evaluation.average_score} and "
                f"expected_max_drawdown of {dd:.2%}, which is well UNDER the "
                f"{TARGET_MAX_LOSS:.0%} loss budget. You are leaving return on "
                f"the table. This round, deploy more risk-bearing exposure to "
                f"raise expected_max_drawdown closer to (but still under) "
                f"{TARGET_MAX_LOSS:.0%}, while keeping every QA score "
                f"≥ {PASS_THRESHOLD}. Prior critique for reference:\n"
                f"{evaluation.critique}"
            )
        else:
            base = (
                f"QA PASSED with average score {evaluation.average_score} and "
                f"expected_max_drawdown of {dd:.2%}, which is close to the "
                f"{TARGET_MAX_LOSS:.0%} target. Attempt one more refinement: try "
                f"to either raise expected_annual_return without exceeding "
                f"{TARGET_MAX_LOSS:.0%} drawdown, or improve the QA scores while "
                f"holding drawdown near {TARGET_MAX_LOSS:.0%}. Prior critique:\n"
                f"{evaluation.critique}"
            )

    advisor_section = _format_advisor_feedback(advisor_output)
    if advisor_section:
        return advisor_section + "\n" + base
    return base


def _select_best_iteration(history: list[dict]) -> int | None:
    """
    Return the 1-based iteration index of the best passing iteration, or None
    if no iteration passed.  The orchestrator's no-pass fallback is to keep
    the FIRST iteration (see ``run_harness``): the critique-driven feedback
    loop tends to push the generator toward increasingly conservative
    portfolios (lower returns at similar drawdown), so when nothing passes,
    the unbiased first attempt is usually the most balanced result.

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

        # --- Step 3a: Intra-iteration Advisor (feedback signal) ---
        # Run the Advisor on this iteration's portfolio so the next
        # round's Generator prompt gets CONCRETE correlation pairs to
        # collapse, rather than a vague "avoid overlap" rule that the
        # LLM cannot apply.  Skip on the last iteration (no next round),
        # when advise is disabled, or when the proposal produced no
        # allocations.  The final Advisor pass (Step 6) still runs for
        # the report and may see a different portfolio.
        # None ⇒ didn't run; int (including 0) ⇒ ran and fed N pairs forward
        intra_advisor: AdvisorOutput | None = None
        intra_pairs_count: int | None = None
        if (
            advise
            and i < MAX_ITERATIONS
            and proposal.allocations
        ):
            intra_advisor = run_advisor(proposal)
            intra_pairs_count = sum(
                1 for p in (intra_advisor.correlation_pairs or [])
                if abs(float(p.get("rho", 0) or 0))
                   >= ADVISOR_FEEDBACK_RHO_THRESHOLD
            )

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
            "intra_advisor_pairs_count": intra_pairs_count,
            "selected": False,
        })

        print(f"\n--- Iteration {i} result ---")
        print(f"  Scores              : {evaluation.scores}")
        print(f"  Average             : {evaluation.average_score}")
        print(f"  Passed              : {evaluation.passed}")
        print(f"  Expected max loss   : {proposal.expected_max_drawdown:.2%}")
        print(f"  Target max loss     : {TARGET_MAX_LOSS:.0%}")
        if intra_advisor is not None:
            print(
                f"  Advisor (pre-feedback) flagged {intra_pairs_count} "
                f"pair(s) at |ρ| ≥ {ADVISOR_FEEDBACK_RHO_THRESHOLD:.2f} "
                f"— feeding into iteration {i + 1}"
            )

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

        feedback = _build_feedback(
            evaluation, proposal, advisor_output=intra_advisor,
        )

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
        # Fall back to the FIRST iteration when nothing passed.  The
        # critique-driven feedback loop tends to push later iterations
        # toward increasingly conservative portfolios (lower returns at
        # similar drawdown).  When no iteration passes QA there is no
        # "objectively better" one — so we keep the unbiased first
        # attempt, which is usually the most balanced result.
        history[0]["selected"] = True
        selected_proposal = proposals[0]
        selected_evaluation = evaluations[0]
        print(
            f"\n⚠️  Reached max iterations ({MAX_ITERATIONS}) without any "
            f"passing portfolio. Returning iteration 1 (first attempt — "
            f"least biased by feedback-driven over-correction).\n"
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
        pricing_result = run_pricing(final_proposal.allocations, capital)
        pricing_block = {
            "performed": True,
            "skipped_reason": None,
            **asdict(pricing_result),
        }

    return {
        "model": MODEL,
        "max_iterations": MAX_ITERATIONS,
        "pass_threshold": PASS_THRESHOLD,
        "target_max_loss": TARGET_MAX_LOSS,
        "spec": asdict(spec),
        "final_proposal": asdict(final_proposal),
        "final_evaluation": asdict(final_evaluation),
        "selected_iteration": selected_idx,
        "selected_proposal": asdict(selected_proposal),
        "selected_evaluation": asdict(selected_evaluation),
        "iteration_history": history,
        "refinement": refinement_block,
        "advisor": advisor_block,
        "pricing": pricing_block,
    }


# ---------------------------------------------------------------------------
# Human-readable Markdown report writer — moved to report.py
# ---------------------------------------------------------------------------
# The writer lives in `report.py` and is imported at the top of this file.
# It reads everything it needs from the result dict (including model,
# max_iterations, pass_threshold, target_max_loss) so it has zero
# dependency on this module's mutable globals.



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
        # --test forces ALL agents to haiku (and disables everything else).
        MODEL = _MODEL_ALIASES["haiku"]
        PLANNER_MODEL = _MODEL_ALIASES["haiku"]
        ADVISOR_MODEL = _MODEL_ALIASES["haiku"]
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
            # --model X overrides ALL agents to X (escape hatch — runs
            # the entire pipeline on one tier, useful for cost / quality
            # comparison or when one tier is overloaded).
            resolved = _MODEL_ALIASES.get(args.model, args.model)
            MODEL = resolved
            PLANNER_MODEL = resolved
            ADVISOR_MODEL = resolved
            print(f"[model override — all agents] {MODEL}")
        else:
            # No override — show the per-agent assignments so the user
            # knows the pipeline isn't uniform.
            print(
                f"[per-agent models] generator/evaluator/refiner={MODEL}  "
                f"planner={PLANNER_MODEL}  advisor={ADVISOR_MODEL}"
            )
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
