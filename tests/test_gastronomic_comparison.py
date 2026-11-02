"""Static tests for gastronomic comparison trial records."""

from __future__ import annotations

import pytest

from mechaharness.gastronomic_comparison import (
    ARM_B_LIVE_BLOCKER,
    assemble_gastronomic_trial,
    live_comparison_status,
    metrics_from_suite_timing,
    summarize_gastronomic_comparison,
    trial_from_suite_run,
    validate_gastronomic_trial,
)
from mechaharness.graph_templates import (
    GastronomicComparisonTemplate,
    GraphTemplateParams,
    default_graph_templates,
)
from mechaharness.node_component import node_components_for


def test_gastronomic_comparison_in_default_catalog() -> None:
    assert "gastronomic_comparison" in default_graph_templates().names()


def test_gastronomic_comparison_topology() -> None:
    template = GastronomicComparisonTemplate()
    graph = template.instantiate(
        GraphTemplateParams(
            goal="Record trial",
            inputs={"goal": "Record trial"},
            soft_bindings={
                "compare_payload": {
                    "trial_id": "t1",
                    "arm": "B",
                    "recipe_id": "gastronomic_guided_development",
                }
            },
        )
    )
    assert graph.template_name == "gastronomic_comparison"
    assert sorted(graph.nodes) == ["assemble", "seed", "validate"]
    comps = node_components_for(graph, template=template)
    soft = {c.soft_point_name for c in comps if c.kind == "soft_point"}
    assert "compare_payload" in soft


def test_assemble_trial_from_completed_outcome() -> None:
    trial = assemble_gastronomic_trial(
        trial_id="t1",
        arm="B",
        recipe_id="gastronomic_guided_development",
        suite_id="calc_cli",
        development_outcome={
            "version": "1",
            "status": "ok",
            "outcome": "completed",
            "reason": "host gates passed",
            "provenance": {"gates_passed": True},
        },
        metrics={
            "stages_passed": 6,
            "stages_total": 6,
            "model_calls": 12,
            "wall_ms": 44000,
            "repair_loops": 1,
        },
        model={"id": "qwen3-30b-thinking"},
        budget={"max_tokens": 8192},
    )
    assert trial["success"] is True
    assert trial["outcome"] == "completed"
    assert trial["metrics"]["model_calls"] == 12
    assert validate_gastronomic_trial(trial)["ok"] is True


def test_arm_recipe_pairing_validated() -> None:
    bad = assemble_gastronomic_trial(
        trial_id="t2",
        arm="A",
        recipe_id="gastronomic_guided_development",
        metrics={"success": True},
    )
    report = validate_gastronomic_trial(bad)
    assert report["ok"] is False
    assert any(e["path"] == "recipe_id" for e in report["errors"])


def test_summarize_does_not_declare_winner() -> None:
    trials = [
        assemble_gastronomic_trial(
            trial_id="a1",
            arm="A",
            recipe_id="guided_coding",
            metrics={
                "success": False,
                "model_calls": 20,
                "wall_ms": 50000,
                "repair_loops": 3,
                "outcome": "failed",
            },
        ),
        assemble_gastronomic_trial(
            trial_id="b1",
            arm="B",
            recipe_id="gastronomic_guided_development",
            development_outcome={"outcome": "completed", "status": "ok", "reason": "ok"},
            metrics={"model_calls": 14, "wall_ms": 42000, "repair_loops": 1},
        ),
        assemble_gastronomic_trial(
            trial_id="b2",
            arm="B",
            recipe_id="gastronomic_guided_development",
            development_outcome={
                "outcome": "needs_guidance",
                "status": "ok",
                "reason": "open",
            },
            metrics={"model_calls": 16, "wall_ms": 48000, "repair_loops": 2},
        ),
    ]
    summary = summarize_gastronomic_comparison(trials)
    assert summary["comparable_ab"] is True
    assert summary["winner"] is None
    assert summary["arms"]["A"]["n"] == 1
    assert summary["arms"]["B"]["n"] == 2
    assert summary["arms"]["B"]["success_rate"] == 0.5
    assert "single stochastic run" in summary["caveats"][0]


def test_validate_reports_schema_errors() -> None:
    report = validate_gastronomic_trial(
        {
            "version": "0",
            "trial_id": "",
            "arm": "Z",
            "recipe_id": "nope",
            "outcome": "",
        }
    )
    assert report["ok"] is False
    paths = {e["path"] for e in report["errors"]}
    assert paths >= {"version", "trial_id", "arm", "recipe_id", "success", "outcome", "metrics"}


@pytest.mark.parametrize(
    ("arm", "recipe"),
    [
        ("A", "guided_coding"),
        ("C", "guided_coding"),
        ("B", "gastronomic_guided_development"),
        ("D", "gastronomic_guided_development"),
    ],
)
def test_valid_arm_recipe_pairs(arm: str, recipe: str) -> None:
    trial = assemble_gastronomic_trial(
        trial_id=f"{arm}-1",
        arm=arm,
        recipe_id=recipe,
        metrics={"success": True, "outcome": "completed"},
    )
    assert validate_gastronomic_trial(trial)["ok"] is True


def test_metrics_from_suite_timing_counts_stages(tmp_path) -> None:
    events = [
        {"kind": "suite_start", "suite_id": "calc_cli", "backend": "live"},
        {
            "kind": "suite_stage",
            "stage": "fangore_calc_parse_number/010",
            "status": "ok",
            "elapsed_s": 1.5,
        },
        {
            "kind": "coding_burst",
            "recipe_id": "guided_coding",
            "verify_runs": 2,
            "repair_rounds": 1,
            "model_calls": 4,
            "elapsed_s": 1.2,
        },
        {
            "kind": "suite_stage",
            "stage": "fangore_calc_add_sub/020",
            "status": "failed",
            "elapsed_s": 0.2,
        },
        {
            "kind": "suite_stage",
            "stage": "fangore_calc_add_sub/020",
            "status": "ok",
            "elapsed_s": 2.0,
        },
    ]
    metrics = metrics_from_suite_timing(events, stages_total=6)
    assert metrics["stages_passed"] == 2
    assert metrics["stages_total"] == 6
    assert metrics["wall_ms"] == 3700
    assert metrics["repair_loops"] == 1
    assert metrics["model_calls"] == 4
    assert metrics["success"] is False
    assert metrics["outcome"] == "failed"
    assert metrics["first_failure_class"] is None

    run = tmp_path / "calc_cli-run"
    run.mkdir()
    (run / "manifest.json").write_text(
        '{"run_id":"r1","suite_id":"calc_cli","completed_stages":["a","b"],'
        '"failed_stage":null}\n',
        encoding="utf-8",
    )
    # Six ok stages → completed arm-A trial.
    lines = [
        '{"kind":"suite_start","suite_id":"calc_cli","backend":"live"}',
        *[
            (
                '{"kind":"suite_stage","stage":"s%d","status":"ok","elapsed_s":0.5}'
                % i
            )
            for i in range(6)
        ],
    ]
    (run / "TIMING.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    trial = trial_from_suite_run(
        run,
        trial_id="calc-a-fixture",
        arm="A",
        recipe_id="guided_coding",
        stages_total=6,
        model={"id": "local-qwen"},
    )
    assert trial["success"] is True
    assert trial["suite_id"] == "calc_cli"
    assert trial["metrics"]["stages_passed"] == 6
    assert validate_gastronomic_trial(trial)["ok"] is True


def test_live_comparison_status_marks_arm_b_not_run() -> None:
    arm_a = assemble_gastronomic_trial(
        trial_id="a1",
        arm="A",
        recipe_id="guided_coding",
        metrics={"success": True, "outcome": "completed", "stages_passed": 6},
    )
    status = live_comparison_status(
        arm_a=arm_a,
        arm_b=None,
        endpoint_configured=True,
    )
    assert status["comparable_ab"] is False
    assert status["winner"] is None
    assert status["arms"]["A"]["status"] == "recorded"
    assert status["arms"]["B"]["status"] == "not_run"
    assert ARM_B_LIVE_BLOCKER in str(status["arms"]["B"]["blocker"])
