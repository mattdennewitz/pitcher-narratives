"""Deterministic cross-surface release gate for analysis-integrity contracts."""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from pitcher_narratives.model_explainer import (
    ProducerModelSemantics,
    render_model_explanation,
)
from pitcher_narratives.models import AuditResult, SpecialistOutputs
from pitcher_narratives.pipeline import (
    AnalysisCapabilities,
    PipelineResult,
    check_hallucinated_metrics,
    is_unverified,
    residual_banner,
)

_SURFACES = json.loads(
    (Path(__file__).parent / "fixtures" / "analysis_integrity" / "surfaces.json").read_text()
)
_SUPPORTED_SEMANTICS = ProducerModelSemantics(
    schema_version="1.0.0",
    feature_schema_sha256="a" * 64,
    model_bundle_sha256="b" * 64,
    artifact_grains=frozenset({"all_pitches"}),
)


@pytest.mark.parametrize("case", _SURFACES, ids=lambda case: case["surface"])
def test_surface_matrix_shares_explanation_and_failure_policy(case):
    explanation = (
        render_model_explanation(
            case["mode"],
            producer_semantics=_SUPPORTED_SEMANTICS,
        )
        if case["mode"] is not None
        else None
    )
    assert (explanation is not None) is case["explains_model"]

    failed = PipelineResult(
        narrative="Generated capsule.",
        specialists=SpecialistOutputs(),
        reader_claim_warnings=["unsupported claim"],
    )
    assert is_unverified(failed) is True
    banner = residual_banner(failed, label=case["surface"].upper())
    assert banner is not None
    assert "UNVERIFIED" in banner


def test_function_model_drives_structured_audit_verdict():
    """The acceptance gate uses a deterministic model, not a provider bypass."""

    def clean_auditor(_messages, info: AgentInfo) -> ModelResponse:
        output_tool = info.output_tools[0]
        return ModelResponse(parts=[ToolCallPart(tool_name=output_tool.name, args={"flags": []})])

    agent = Agent(FunctionModel(clean_auditor), output_type=AuditResult)
    verdict = agent.run_sync("Audit the manifest-backed claim.").output

    assert verdict.is_clean is True


def test_reader_guard_blocks_hallucinated_metric_and_unavailable_capability():
    report = check_hallucinated_metrics(
        "xMagic rose, proving the pitcher intended to change his command.",
        capabilities=AnalysisCapabilities(),
        cited_fact_ids=(),
    )

    assert "xMagic" in report.unknown_metrics
    assert report.unsupported_claim_warnings
    assert report.is_clean is False


def test_public_data_load_opens_only_manifest_bundle(monkeypatch, tmp_path):
    """Raw-file presence cannot influence the public report data path."""
    from pitcher_narratives import data as data_module

    raw_dir = tmp_path / "raw-statcast"
    raw_dir.mkdir()
    pl.DataFrame({"pitcher": [592155], "game_pk": [-1]}).write_parquet(raw_dir / "2026.parquet")
    monkeypatch.setenv("STATCAST_PATH", str(raw_dir))

    opened: list[Path] = []
    read_csv = pl.read_csv
    read_parquet = pl.read_parquet

    def tracked_csv(path, *args, **kwargs):
        opened.append(Path(path).resolve())
        return read_csv(path, *args, **kwargs)

    def tracked_parquet(path, *args, **kwargs):
        opened.append(Path(path).resolve())
        return read_parquet(path, *args, **kwargs)

    monkeypatch.setattr(pl, "read_csv", tracked_csv)
    monkeypatch.setattr(pl, "read_parquet", tracked_parquet)

    bundle_root = tmp_path / "bundle"
    bundle_root.mkdir()
    monkeypatch.setattr(data_module, "AGGS_DIR", bundle_root)

    with pytest.raises(
        data_module.IncompatiblePitchingPlusExport,
        match="semantic manifest is missing",
    ):
        data_module.load_pitcher_data(592155, recent_appearances=2)

    assert opened == []
