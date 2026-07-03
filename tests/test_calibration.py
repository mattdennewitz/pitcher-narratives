import json

from pitcher_narratives.calibration import (
    aggregate,
    format_table,
    load_records,
    main,
)


def _rec(mode, rev, *, anchor_cap, fact_cap, capsule_revised=False):
    return {
        "mode": mode, "pitcher_id": 1, "span": 10,
        "anchor_depth_cap": anchor_cap, "fact_depth_cap": fact_cap,
        "revision_count": rev, "capsule_revised": capsule_revised,
        "n_capsule_audit_flags": 0, "n_anchor_warnings": 0,
        "n_value_parity_warnings": 0, "n_audit_flags": 0,
    }


def test_aggregate_groups_by_mode_and_computes_rates():
    records = [
        _rec("recap", 0, anchor_cap=1, fact_cap=2),
        _rec("recap", 1, anchor_cap=1, fact_cap=2, capsule_revised=True),
        _rec("report", 5, anchor_cap=5, fact_cap=2),
    ]
    stats = aggregate(records)
    assert set(stats) == {"recap", "report"}
    assert stats["recap"].n == 2
    assert stats["recap"].mean_revision_count == 0.5
    assert stats["recap"].capsule_revised_rate == 0.5
    # one of two recap records hit the anchor cap of 1 (revision_count 1 >= 1)
    assert stats["recap"].anchor_hit_cap_rate == 0.5
    assert stats["recap"].fact_hit_cap_rate == 0.5
    assert stats["report"].anchor_hit_cap_rate == 1.0  # 5 >= 5


def test_load_records_from_jsonl_and_validation_json(tmp_path):
    jl = tmp_path / "metrics.jsonl"
    jl.write_text(
        json.dumps(_rec("report", 2, anchor_cap=5, fact_cap=2)) + "\n"
        + json.dumps(_rec("recap", 1, anchor_cap=1, fact_cap=2)) + "\n"
    )
    vj = tmp_path / "validation.json"
    vj.write_text(json.dumps({
        "game_date": "2026-07-03",
        "picks": {"592155": _rec("recap", 0, anchor_cap=1, fact_cap=2)},
    }))
    records = load_records([str(jl), str(vj)])
    assert len(records) == 3
    assert sum(r["mode"] == "recap" for r in records) == 2


def test_load_records_walks_directory(tmp_path):
    (tmp_path / "2026-07-03").mkdir()
    (tmp_path / "2026-07-03" / "validation.json").write_text(json.dumps({
        "game_date": "2026-07-03",
        "picks": {"1": _rec("recap", 1, anchor_cap=1, fact_cap=2)},
    }))
    records = load_records([str(tmp_path)])
    assert len(records) == 1


def test_format_table_lists_each_mode():
    stats = aggregate([_rec("recap", 1, anchor_cap=1, fact_cap=2)])
    table = format_table(stats)
    assert "recap" in table
    assert "anchor_hit_cap" in table


def test_main_prints_table(tmp_path, capsys):
    jl = tmp_path / "m.jsonl"
    jl.write_text(json.dumps(_rec("report", 2, anchor_cap=5, fact_cap=2)) + "\n")
    rc = main([str(jl)])
    assert rc == 0
    assert "report" in capsys.readouterr().out


def test_main_no_records_returns_nonzero(tmp_path, capsys):
    rc = main([str(tmp_path)])
    assert rc == 1
    assert "no records" in capsys.readouterr().err.lower()
