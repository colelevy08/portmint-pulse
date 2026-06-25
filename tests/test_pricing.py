"""Tests for the cost engine — model normalization and per-token pricing."""

from portmint_pulse import pricing


def test_normalize_strips_bracket_and_date():
    assert pricing.normalize_model("claude-opus-4-8[1m]") == "claude-opus-4-8"
    assert pricing.normalize_model("claude-haiku-4-5-20251001") == "claude-haiku-4-5"
    assert pricing.normalize_model("claude-sonnet-4-6") == "claude-sonnet-4-6"


def test_normalize_unknown_returns_none():
    assert pricing.normalize_model("<synthetic>") is None
    assert pricing.normalize_model(None) is None
    assert pricing.normalize_model("some-future-model") is None


def test_price_input_and_output():
    # 1,000,000 Haiku input tokens = $1.00; output = $5.00.
    assert pricing.price("claude-haiku-4-5", input_tokens=1_000_000) == 1.0
    assert pricing.price("claude-haiku-4-5", output_tokens=1_000_000) == 5.0


def test_price_cache_multipliers():
    # cache read = 0.10x input; 5m write = 1.25x; 1h write = 2.0x.
    assert round(pricing.price("claude-haiku-4-5", cache_read=1_000_000), 4) == 0.1
    assert round(pricing.price("claude-haiku-4-5", cache_write_5m=1_000_000), 4) == 1.25
    assert round(pricing.price("claude-haiku-4-5", cache_write_1h=1_000_000), 4) == 2.0


def test_unknown_model_is_free():
    assert pricing.price("<synthetic>", input_tokens=1_000_000) == 0.0
    assert pricing.price(None, output_tokens=999) == 0.0


def test_opus_1m_variant_prices_same_as_base():
    base = pricing.price("claude-opus-4-8", input_tokens=1_000_000)
    variant = pricing.price("claude-opus-4-8[1m]", input_tokens=1_000_000)
    assert base == variant == 5.0
