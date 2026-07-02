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


def test_subscription_plan_lookup():
    assert pricing.plan_price("pro") == 20.0
    assert pricing.plan_price("max5") == 100.0
    assert pricing.plan_price("max20") == 200.0
    assert pricing.plan_price("MAX20") == 200.0  # case-insensitive
    assert pricing.plan_price("bogus") is None
    assert pricing.plan_price(None) is None
    assert pricing.plan_label("max5") == "Claude Max 5×"
    assert pricing.plan_label("nope") is None


def test_normalize_strips_provider_prefixes():
    # Bedrock-style ids: region prefix + "-vN:0" build suffix.
    assert pricing.normalize_model("anthropic.claude-opus-4-8") == "claude-opus-4-8"
    assert pricing.normalize_model("us.anthropic.claude-opus-4-8-v1:0") == "claude-opus-4-8"
    assert pricing.normalize_model("eu.anthropic.claude-3-5-sonnet-20241022-v2:0") == "claude-3-5-sonnet"
    # Vertex-style "@date" version separator.
    assert pricing.normalize_model("claude-opus-4-5@20251101") == "claude-opus-4-5"
    # "-latest" alias.
    assert pricing.normalize_model("claude-3-5-haiku-latest") == "claude-3-5-haiku"


def test_legacy_models_are_priced():
    # Old transcripts must not silently cost $0.
    assert pricing.price("claude-opus-4-1", input_tokens=1_000_000) == 15.0
    assert pricing.price("claude-opus-4-1-20250805", output_tokens=1_000_000) == 75.0
    assert pricing.price("claude-sonnet-4-5-20250929", input_tokens=1_000_000) == 3.0
    assert pricing.price("claude-3-7-sonnet-20250219", output_tokens=1_000_000) == 15.0
    assert pricing.price("claude-3-5-haiku-20241022", input_tokens=1_000_000) == 0.8
    assert pricing.price("claude-3-haiku-20240307", input_tokens=1_000_000) == 0.25
    assert pricing.price("claude-3-opus-20240229", output_tokens=1_000_000) == 75.0
    assert pricing.price("claude-sonnet-5", input_tokens=1_000_000) == 3.0
