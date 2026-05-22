# Portfolio Optimization Harness

A multi-agent implementation inspired by Anthropic's [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps), applied to financial portfolio optimisation.

The harness started as the original three-agent pattern (Planner → Generator → Evaluator). It has since grown to five agents with explicit selection, refinement, and advisory steps to address the gap between "passes QA" and "ready to actually use."

## Architecture

```
                            ┌──────────┐
                            │ PLANNER  │
                            └─────┬────┘
                                  │ Investment Spec
                                  ▼
        ┌─────────────────────────────────────────────┐
        │  for i in 1..MAX_ITERATIONS (default 3)     │
        │                                             │
        │  ┌───────────┐                              │
        │  │ GENERATOR │ ◀──── critique-driven        │
        │  └─────┬─────┘       feedback               │
        │        │ Portfolio                          │
        │        ▼                                    │
        │  ┌───────────┐                              │
        │  │ EVALUATOR │ ── scores + passed flag      │
        │  └─────┬─────┘                              │
        │        │                                    │
        │        ▼                                    │
        │  history[i] = {alloc, scores, passed, …}    │
        └─────────────────────────────────────────────┘
                                  │
                                  ▼
                          ┌──────────────┐
                          │   SELECTOR   │   pick passing iteration whose
                          │ (no LLM call)│   |drawdown − 5%| is smallest
                          └──────┬───────┘
                                 │ selected_proposal
                                 ▼
                          ┌──────────────┐
                          │   REFINER    │   surgically address every
                          └──────┬───────┘   critique point
                                 │ refined_proposal
                                 ▼
                          ┌──────────────┐
                          │  EVALUATOR   │   re-score the refined version
                          │   (re-run)   │
                          └──────┬───────┘
                                 │
                                 ▼
                       passes QA AND
                       drawdown ≤ 5%?
                       ┌─────┴──────┐
                      yes           no
                       │             │
              promote refined   keep selected
                       └──────┬──────┘
                              │ final_proposal
                              ▼
                       ┌──────────────┐
                       │   ADVISOR    │   surface correlated holdings +
                       │ (read-only)  │   structured merge suggestions
                       └──────┬───────┘
                              │
                              ▼
                       harness_output.{json,md}
```

### Agent roles

| Agent | Role |
|---|---|
| **Planner** | Expands a brief user goal ("maximize return, ≤5% annual loss") into a detailed investment specification: asset universe, constraints, risk budget, evaluation criteria, tail-risk scenarios. |
| **Generator** | Constructs a concrete portfolio allocation that satisfies the spec. Now returns plain-English `descriptions` for each ticker alongside `allocations`. On later iterations, addresses every point from the evaluator's critique. |
| **Evaluator** | Independently stress-tests the portfolio against five 1–10 criteria (constraint compliance, return potential, diversification, implementability, methodology rigour) and writes a detailed critique. **Passes only if** `avg ≥ 7` AND `no single score ≤ 4` AND the evaluator's own `passed: true/false` judgement agrees — all three must hold. |
| **Selector** (no LLM call) | After all `MAX_ITERATIONS` rounds finish, picks the passing iteration whose `expected_max_drawdown` is closest to the 5% loss target. Tiebreak: smaller drawdown, then higher score. Falls back to the last iteration if nothing passed. |
| **Refiner** | Takes the selected portfolio + the evaluator's critique and produces a surgical revision that addresses every flagged issue while preserving what worked. Re-evaluated; **promoted to final only if it passes QA and stays within the 5% drawdown target**, otherwise the selected version is kept. |
| **Advisor** (read-only) | Inspects the final portfolio and emits a pairwise correlation snapshot plus structured `{merge_from, merge_into, rationale, tradeoff}` consolidation suggestions. **Never modifies the portfolio** — every suggestion has an explicit tradeoff so the human reader can decide whether to apply it. |

### Key design decisions

1. **Separation of generation and evaluation.** The blog post's central insight: a generator asked to self-evaluate will "confidently praise its own work." The Evaluator is prompted to be tough and is explicitly told to return `passed: false` whenever it finds a binding-constraint violation (FX hedging, ticker cap, leverage, etc.), even if the numeric scores are high.

2. **Always run all iterations, then select.** The original harness exited the loop as soon as one iteration passed. That gave away later iterations that could have landed closer to the 5% risk-budget target. Now the loop always runs `MAX_ITERATIONS` rounds; after the loop, the Selector picks the best passing iteration by closeness to the target.

3. **Iteration feedback is regime-aware.** When an iteration passes but its drawdown is over 5% the Generator is told to push it down; when drawdown is well under 5% (≤ `UNDER_UTILISATION_BAND`) the Generator is told the risk budget is being wasted and to deploy more risk-bearing exposure. Failures pass the critique through unchanged.

4. **Refinement applies; advice does not.** The Refiner is allowed to replace the selected portfolio if its output passes QA. The Advisor never modifies anything — it produces structured suggestions for the human reader. This split keeps "automated improvement" and "human judgement" cleanly separated.

5. **Resilience to transient API failures.** Each `call_claude` is wrapped in exponential-backoff retry on 429/5xx/529/connection/timeout errors (5 SDK retries + 6 outer attempts with 2/4/8/16/32s jitter, ≈62s max wall-clock). Auth/validation errors fast-fail.

## Running

This project is a [uv](https://docs.astral.sh/uv/) workspace member of the parent `testbench` project. All dependencies are managed through uv — no manual `pip install`.

### First-time setup

From the repository root (`testbench/`):

```bash
uv sync
```

### Set the API key

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Default run

Opus 4.7, 3 iterations, refinement on, advisor on:

```bash
uv run python long_running_agent/harness.py
```

This makes ~10 API calls per run (1 planner + 3×generator + 3×evaluator + refiner + re-evaluator + advisor) and takes a few minutes against Opus 4.7.

### CLI flags

| Flag | Effect |
|---|---|
| `--test` | Smoke-test mode: Haiku 4.5, 1 iteration, no refinement, no advisor. ~3 API calls, cheapest end-to-end verification of the plumbing. Useful when Opus is overloaded or you just want to see the flow run. |
| `--model {haiku\|sonnet\|opus\|<full-id>}` | Override the model. Aliases resolve to `claude-haiku-4-5-20251001`, `claude-sonnet-4-6`, `claude-opus-4-7`. Any other string is passed through verbatim as a model ID. |
| `--iterations N` | Override `MAX_ITERATIONS` for this run (default 3). |
| `--no-refine` | Skip the post-selection Refiner pass. |
| `--no-advisor` | Skip the post-selection Advisor pass. |

`--test` takes precedence — if combined with `--model` / `--iterations` / `--no-refine` / `--no-advisor`, the test-mode defaults win.

### Examples

```bash
# Full default run
uv run python long_running_agent/harness.py

# Quick smoke test — Haiku, 1 iteration, no refiner, no advisor
uv run python long_running_agent/harness.py --test

# Opus is overloaded? Full 3-iteration run on Sonnet
uv run python long_running_agent/harness.py --model sonnet

# Run with refiner but skip the advisor
uv run python long_running_agent/harness.py --no-advisor

# Smallest meaningful real run — Haiku, 2 iterations, with refinement
uv run python long_running_agent/harness.py --model haiku --iterations 2
```

## Output

Each run produces two files in the directory it was run from:

- **`harness_output.json`** — machine-readable trace: spec, every iteration's allocations and scores, selected proposal, refinement block (before/after), advisor block (suggestions + correlations), and raw model responses.
- **`harness_output.md`** — human-readable Markdown report. Renders cleanly in VS Code's built-in preview (`Cmd+Shift+V`) or any Markdown viewer. Contents:
  - Header summary (model, iterations, selected iteration, refinement / advisor status, target loss, pass rule)
  - **Final Portfolio** table with `Ticker | Weight | Description` columns
  - Iteration Summary table comparing all iterations on score, return, drawdown, and distance to target — selected iteration starred
  - Investment Spec from the Planner
  - Selected Portfolio Methodology + Rationale
  - Selected Portfolio Evaluator Scores + Critique
  - **Post-Selection Refinement** section with Score deltas, Portfolio metric deltas, and Allocation changes tables, plus the Refiner's point-by-point rationale and the re-evaluator's report
  - **Simplification Suggestions** (Advisor) — `{merge_from} → {merge_into}` items with explicit tradeoffs, plus a pairwise correlation table sorted by strongest |ρ|
  - Per-iteration detail
  - Planner / Generator / Evaluator / Refiner / Advisor raw responses in collapsible `<details>` blocks

## Configuration

Edit the constants at the top of `harness.py`:

| Constant | Default | Meaning |
|---|---|---|
| `MODEL` | `claude-opus-4-7` | Default model (override via `--model`) |
| `MAX_TOKENS` | `4096` | Per-call token budget |
| `MAX_ITERATIONS` | `3` | Generator ↔ evaluator rounds (override via `--iterations`) |
| `PASS_THRESHOLD` | `7` | Minimum average score for a portfolio to pass |
| `TARGET_MAX_LOSS` | `0.05` | The 5% loss-budget target the selector aims for |
| `UNDER_UTILISATION_BAND` | `0.04` | Drawdowns below this are flagged as "wasting risk capacity" in feedback |
| `SDK_MAX_RETRIES` | `5` | SDK-level transparent retries on transient errors |
| `RETRY_MAX_ATTEMPTS` | `6` | Outer-wrapper attempts on top of SDK |
| `RETRY_INITIAL_BACKOFF_SECONDS` | `2.0` | First backoff before retry 2 |
| `RETRY_MAX_BACKOFF_SECONDS` | `32.0` | Cap on per-step backoff |
| `RETRYABLE_HTTP_STATUS` | `{429, 500, 502, 503, 504, 529}` | Status codes worth retrying |

## Extending This

Some natural next steps:

- **Structured critique.** Have the Evaluator return critique as a list of `{issue, severity, suggested_fix}` objects instead of one prose paragraph. The Refiner could then address each item explicitly and report which were resolved.
- **Deterministic constraint checker.** Add a Python pre-check that verifies hard rules (ticker count ≤ 15, FX-hedged-only on non-USD, sector caps, leverage) before the LLM evaluator sees the portfolio. Cheap, deterministic, no opinion drift.
- **Real data.** Plug in `yfinance` or similar to fetch actual historical returns, then have the generator use real numbers and the evaluator run actual backtests.
- **Tool use.** Give the generator and evaluator Claude tool-use capabilities so they can call Python functions (mean-variance solver, Sharpe ratio, drawdown calc) rather than reasoning from memory.
- **Sprint decomposition.** For a more complex version, break the work into sprints (asset selection → weight optimisation → tail-risk hedging → final review), each with its own generator ↔ evaluator loop.

## Disclaimer

This is a conceptual exploration of an AI engineering pattern. It is **NOT** financial advice. The portfolio allocations produced are illustrative and must not be used for actual investment decisions.
