"""
Anthropic API client + small helpers shared by ``agents.py`` and the
orchestrator in ``harness.py``.

What lives here:

* The singleton ``anthropic.Anthropic`` client.
* ``call_claude`` — the Messages API wrapper with exponential-backoff
  retry on transient errors and an explicit truncation warning when
  the response hits ``stop_reason == "max_tokens"``.
* ``_parse_json_response`` — fail-soft JSON parser used by every
  agent.  Returns ``{}`` on unparseable output so the pipeline degrades
  through dataclass defaults rather than crashing.
* Model / token / retry constants.  These are deliberately
  module-level mutables so the harness CLI can patch them (e.g.,
  ``api.MODEL = ...`` from ``--model X`` or ``--test``).
  ``call_claude`` resolves them at call time, so patches take effect
  immediately without having to re-import anything.

Has no dependency on ``models``, ``agents``, ``harness``, ``pricing``,
or ``report`` — strictly a leaf module on the project's dependency graph.
"""

from __future__ import annotations

import json
import os
import random
import re
import sys
import time
from typing import Any

import anthropic


# ---------------------------------------------------------------------------
# Model selection (per-agent; patched by the CLI in harness.py)
# ---------------------------------------------------------------------------
MODEL = "claude-opus-4-7"
# Per-agent overrides.  The Planner is mostly recall + JSON structuring
# and the Advisor is pattern-matching against training memory — neither
# needs Opus.  Generator / Evaluator / Refiner do the real reasoning
# work and stay on MODEL (Opus by default).
PLANNER_MODEL = "claude-sonnet-4-6"
ADVISOR_MODEL = "claude-haiku-4-5-20251001"

# ---------------------------------------------------------------------------
# Token budgets
# ---------------------------------------------------------------------------
MAX_TOKENS = 4096
# The Refiner emits a full portfolio (allocations + descriptions + numbers)
# AND a point-by-point response to every critique item — by far the most
# output-heavy agent.  4096 tokens regularly truncates mid-string, which
# previously crashed the JSON parser.  Give it more headroom.
REFINER_MAX_TOKENS = 8192


# ---------------------------------------------------------------------------
# Retry / backoff config for transient Anthropic API errors
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Client construction (fires at import time — fails fast on missing key)
# ---------------------------------------------------------------------------
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
# Internal: classify which exceptions should trigger a retry
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


# ---------------------------------------------------------------------------
# Public: Messages API wrapper
# ---------------------------------------------------------------------------
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
# Public: best-effort JSON parse for model responses
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
