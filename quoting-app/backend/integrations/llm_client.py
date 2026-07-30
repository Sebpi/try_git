"""Thin Anthropic wrapper, optional.

Every LLM-backed agent (composer prose polish, response classifier on
ambiguous replies) must work correctly with NO api key configured, falling
back to its own deterministic heuristic -- that's the primary code path this
app is tested against. When ANTHROPIC_API_KEY is set, agents may call
`complete()` for a higher-quality pass, but must never depend on it for
correctness (see SPEC.md guardrails: never invent a price/product).
"""
from __future__ import annotations

import os


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def complete(system: str, user: str, max_tokens: int = 700) -> str:
    if not available():
        raise RuntimeError("ANTHROPIC_API_KEY not configured")
    from anthropic import Anthropic  # imported lazily -- optional dependency

    client = Anthropic()
    model = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(block.text for block in resp.content if getattr(block, "type", None) == "text")
