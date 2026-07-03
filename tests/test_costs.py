"""Tests for the shared cost-tracking module."""

import pytest

from pitcher_narratives.costs import PRICING, UsageTracker, model_label


def test_model_label_strips_provider_prefix():
    """Provider-qualified model ids reduce to bare model names."""
    assert model_label("anthropic:claude-sonnet-4-6") == "claude-sonnet-4-6"
    assert model_label("google-gla:gemini-3.1-pro-preview") == "gemini-3.1-pro-preview"
    assert model_label("claude-haiku-4-5") == "claude-haiku-4-5"


def test_pricing_covers_the_four_run_models():
    """Both providers' full and mini tiers are priced."""
    for model in (
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
        "gemini-3.5-flash",
        "gemini-flash-latest",
    ):
        assert "input" in PRICING[model] and "output" in PRICING[model]


def test_haiku_4_5_pricing_is_correct():
    """Haiku 4.5 pricing is $1.00/$5.00 per MTok, not Haiku 3.5's old $0.80/$4.00."""
    assert PRICING["claude-haiku-4-5"] == {"input": 1.00, "output": 5.00}


def test_tracker_records_and_totals():
    """Records accumulate per model and stage; totals are exact."""
    t = UsageTracker()
    t.record("anthropic:claude-sonnet-4-6", 1_000_000, 500_000, stage="selector")
    t.record("anthropic:claude-sonnet-4-6", 1_000_000, 500_000, stage="writer:Smith")
    # sonnet: $3/M in, $15/M out -> 2M in = $6, 1M out = $15
    assert t.total_cost() == 21.0
    assert t.total_input() == 2_000_000
    assert t.total_output() == 1_000_000
    assert [r.stage for r in t.records] == ["selector", "writer:Smith"]


def test_tracker_unknown_model_costs_none():
    """Unknown models keep token counts but report no dollar cost."""
    t = UsageTracker()
    t.record("openrouter:deepseek/deepseek-v4-pro", 1000, 1000, stage="selector")
    assert t.total_input() == 1000
    assert t.total_cost() is None or t.total_cost() == 0.0
    block = t.render_cost_block(wall_s=10.0)
    assert "n/a" in block
    assert t.to_json()[0]["cost"] is None


def test_render_cost_block_contents():
    """The digest footer block names stages, models, and the total."""
    t = UsageTracker()
    t.record("google-gla:gemini-3.1-pro-preview", 12_400, 1_100, stage="selector")
    t.record("google-gla:gemini-3.1-pro-preview", 3_000, 500, stage="writer:Smith")
    t.record("google-gla:gemini-3.1-pro-preview", 3_000, 500, stage="writer:Jones")
    block = t.render_cost_block(wall_s=94.0)
    assert "selector" in block
    assert "writers" in block          # writer:* stages are grouped
    assert "gemini-3.1-pro-preview" in block
    assert "94s" in block
    assert "$" in block


def test_to_json_records():
    """Raw per-call records serialize for usage.json."""
    t = UsageTracker()
    t.record("anthropic:claude-sonnet-4-6", 100, 50, stage="selector")
    [rec] = t.to_json()
    assert rec["stage"] == "selector"
    assert rec["model"] == "claude-sonnet-4-6"
    assert rec["input_tokens"] == 100
    assert rec["output_tokens"] == 50
    assert rec["cost"] == pytest.approx(0.00105)


def test_format_table_still_renders_markdown():
    """compare.py's markdown table survives the move."""
    t = UsageTracker()
    t.record("anthropic:claude-haiku-4-5", 1_000_000, 0, stage="x")
    table = t.format_table()
    assert table.startswith("| Model |")
    assert "claude-haiku-4-5" in table
