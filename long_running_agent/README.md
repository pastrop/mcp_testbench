# Portfolio Optimization Harness

A bare-bones implementation of the **three-agent architecture** described in
Anthropic's [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps),
applied to financial portfolio optimisation.

## Architecture

```
┌──────────┐     Investment Spec     ┌───────────┐
│  PLANNER │ ──────────────────────▶ │ GENERATOR │
└──────────┘                         └─────┬─────┘
  "Expand a                                │
   1-sentence                         Portfolio
   goal into                          Proposal
   a full spec"                            │
                                     ┌─────▼─────┐
                              ┌─────▶│ EVALUATOR │
                              │      └─────┬─────┘
                              │            │
                         feedback     pass / fail
                         (if fail)         │
                              │      ┌─────▼─────┐
                              └──────┤  PASSED?   │──▶ yes ──▶ DONE
                                     └───────────┘
                                          │
                                       no (loop up to N times)
```

### Agent Roles

| Agent       | Blog-post analogue | Role in this harness |
|-------------|-------------------|----------------------|
| **Planner** | Planner           | Expands a brief user goal ("maximize return, ≤5% loss") into a detailed investment specification: asset universe, constraints, risk budget, evaluation criteria, tail-risk scenarios. |
| **Generator** | Generator / Builder | Constructs a concrete portfolio allocation that satisfies the spec. On subsequent iterations, addresses every point from the evaluator's critique. |
| **Evaluator** | Evaluator / QA   | Independently stress-tests the portfolio against 5 hard criteria (constraint compliance, return potential, diversification, implementability, methodology). Grades each 1-10 and writes a detailed critique. Portfolio passes only if avg ≥ 7 and no single score ≤ 4. |

### Key Design Decisions (mapped to the blog post)

1. **Separation of generation and evaluation** — The blog post's central insight.
   A generator asked to self-evaluate will "confidently praise its own work."
   Our evaluator is prompted to be *skeptical* and *tough*, penalizing
   hand-waving and checking specific historical crash scenarios.

2. **Structured hand-off artifacts** — The spec, proposal, and evaluation
   are dataclasses serialised to JSON, ensuring each agent has complete
   context without inheriting the previous agent's conversation history
   (analogous to context resets in the blog).

3. **Concrete grading criteria** — Just as the blog post turned "is this
   design good?" into four gradable dimensions, we turn "is this portfolio
   good?" into five dimensions with specific failure conditions.

4. **Iterative feedback loop** — If the evaluator fails the portfolio, its
   full critique is injected into the generator's next prompt.  The generator
   must address every issue (analogous to the sprint-contract renegotiation
   in the blog post).

## Running

This project is set up as a [uv](https://docs.astral.sh/uv/) workspace member of the parent `testbench` project. All dependencies are managed through uv — no manual `pip install` needed.

### First-time setup

From the repository root (`testbench/`):

```bash
# Sync the workspace — creates .venv and installs all deps for every member
uv sync
```

### Run the harness

```bash
# Set your API key (the harness will exit with a clear error if this is missing)
export ANTHROPIC_API_KEY="sk-ant-..."

# From the repository root:
uv run python long_running_agent/harness.py

# …or from inside long_running_agent/:
cd long_running_agent
uv run python harness.py
```

`uv run` automatically uses the workspace's managed virtualenv at `testbench/.venv`, so you don't need to activate it manually.

The harness will print each agent's output and a final summary. A full trace (spec, all iterations, final portfolio) is saved to `harness_output.json` in the directory you ran it from.

## Configuration

Edit the constants at the top of `harness.py`:

| Constant         | Default            | Meaning |
|------------------|--------------------|---------|
| `MODEL`          | `claude-opus-4-7`  | Which Claude model to use |
| `MAX_ITERATIONS` | `3`                | Max generator↔evaluator rounds |
| `PASS_THRESHOLD` | `7`                | Minimum average score to pass |

## Extending This

Some natural next steps if you want to go deeper:

- **Add real data**: plug in `yfinance` or similar to fetch actual historical
  returns, then have the generator use real numbers and the evaluator run
  actual backtests.
- **Tool use**: give the generator and evaluator Claude tool-use capabilities
  so they can call Python functions (backtest, calculate Sharpe, etc.) rather
  than reasoning from memory.
- **Sprint decomposition**: for a more complex version, break the work into
  sprints (asset selection → weight optimisation → tail-risk hedging → final
  review), each with its own generator↔evaluator loop.
- **Persistent context**: use the Agent SDK's compaction or context-reset
  features for longer-running versions.

## Disclaimer

This is a conceptual exploration of an AI engineering pattern.  It is NOT
financial advice.  The portfolio allocations produced are illustrative and
should not be used for actual investment decisions.
