"""Cost engine — turns raw Claude token counts into dollars.

All prices are in US dollars *per million tokens*, taken from Anthropic's
published model pricing (the figures the Claude API skill carries, cached
2026-06-04). We keep every number in exactly one place so a price change is a
one-line edit, never a hunt-and-replace.

How cache pricing works (Anthropic's standard multipliers, relative to a
model's input price):
  - writing to the 5-minute cache costs 1.25x the input price
  - writing to the 1-hour cache  costs 2.00x the input price
  - reading from the cache       costs 0.10x the input price

Claude Code leans heavily on prompt caching, so getting these right is the
difference between a believable cost number and a wildly inflated one.

Note on the "[1m]" long-context variant of Opus 4.8: Anthropic serves Opus 4.8's
full 1-million-token context at standard pricing — there is no long-context
premium — so "claude-opus-4-8[1m]" is priced identically to the base model.
"""

from __future__ import annotations

# Base input/output price per MILLION tokens, in USD.
_BASE_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-opus-4-8":   {"input": 5.0,  "output": 25.0},
    "claude-opus-4-7":   {"input": 5.0,  "output": 25.0},
    "claude-sonnet-4-6": {"input": 3.0,  "output": 15.0},
    "claude-haiku-4-5":  {"input": 1.0,  "output": 5.0},
    "claude-fable-5":    {"input": 10.0, "output": 50.0},
}

# Cache-price multipliers applied to a model's input price (see module docstring).
_CACHE_WRITE_5M_MULT = 1.25
_CACHE_WRITE_1H_MULT = 2.00
_CACHE_READ_MULT = 0.10


def _build_per_token_rates() -> dict[str, dict[str, float]]:
    """Pre-compute the per-SINGLE-token price for every token type, per model.

    Doing the divide-by-a-million once here keeps the hot path (pricing tens of
    thousands of messages) to plain multiplications.
    """
    rates: dict[str, dict[str, float]] = {}
    for model, base in _BASE_PER_MTOK.items():
        inp = base["input"] / 1_000_000
        out = base["output"] / 1_000_000
        rates[model] = {
            "input": inp,
            "output": out,
            "cache_write_5m": inp * _CACHE_WRITE_5M_MULT,
            "cache_write_1h": inp * _CACHE_WRITE_1H_MULT,
            "cache_read": inp * _CACHE_READ_MULT,
        }
    return rates


_RATES = _build_per_token_rates()


def normalize_model(raw: str | None) -> str | None:
    """Map a raw transcript model string onto a known pricing key.

    Transcripts contain things like "claude-opus-4-8[1m]" (the 1M-context
    variant), "claude-haiku-4-5-20251001" (a dated snapshot), or "<synthetic>"
    (locally generated, not a real model call). We strip the bracketed suffix
    and any trailing date, then look the result up. Anything we don't recognise
    (including "<synthetic>") returns None and is treated as zero-cost.
    """
    if not raw:
        return None
    name = raw.strip()
    # Drop a bracketed context-window tag, e.g. "[1m]".
    bracket = name.find("[")
    if bracket != -1:
        name = name[:bracket]
    # Drop a trailing "-YYYYMMDD" dated-snapshot suffix.
    parts = name.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 8:
        name = parts[0]
    return name if name in _RATES else None


def price(
    model: str | None,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read: int = 0,
    cache_write_5m: int = 0,
    cache_write_1h: int = 0,
) -> float:
    """Return the USD cost of one message's token usage.

    Unknown / synthetic models cost nothing (we can't price what we can't
    identify), but their tokens are still counted elsewhere for the totals.
    """
    key = normalize_model(model)
    if key is None:
        return 0.0
    r = _RATES[key]
    return (
        input_tokens * r["input"]
        + output_tokens * r["output"]
        + cache_read * r["cache_read"]
        + cache_write_5m * r["cache_write_5m"]
        + cache_write_1h * r["cache_write_1h"]
    )


def known_models() -> list[str]:
    """The set of model keys we have prices for (handy for diagnostics)."""
    return list(_BASE_PER_MTOK.keys())


# --- Subscription plans (for the "money's worth" comparison) -----------------
# Claude.ai flat monthly prices. Used ONLY to compare your API-equivalent token
# spend against a subscription — never billed, never sent anywhere.
SUBSCRIPTION_PLANS: dict[str, tuple[str, float]] = {
    "pro": ("Claude Pro", 20.0),
    "max5": ("Claude Max 5×", 100.0),
    "max20": ("Claude Max 20×", 200.0),
}


def plan_price(name: str | None) -> float | None:
    """Monthly USD for a plan key (pro/max5/max20), or None if unknown."""
    plan = SUBSCRIPTION_PLANS.get((name or "").strip().lower())
    return plan[1] if plan else None


def plan_label(name: str | None) -> str | None:
    """Display label for a plan key (e.g. 'Claude Max 5×'), or None if unknown."""
    plan = SUBSCRIPTION_PLANS.get((name or "").strip().lower())
    return plan[0] if plan else None
