"""Graph budget spend folds into CLI cost_units observations."""

from __future__ import annotations

from types import SimpleNamespace

from mechaharness.cli_instrumentor import CliRunResult, CliStepResult
from tests.stories.cli_probes.graph_cost import graph_cost_fields, with_graph_cost


def test_graph_cost_fields_sum_results() -> None:
    a = SimpleNamespace(budget_spent=1.5)
    b = SimpleNamespace(budget_spent=2.5)
    assert graph_cost_fields(a, b) == {"budget_spent": 4.0, "cost_units": 4.0}


def test_with_graph_cost_does_not_overwrite_explicit() -> None:
    out = with_graph_cost(
        {"budget_spent": 9.0, "status": "ok"},
        SimpleNamespace(budget_spent=2.0),
    )
    assert out["budget_spent"] == 9.0
    assert out["cost_units"] == 2.0
    assert out["status"] == "ok"


def test_observation_prefers_budget_spent_over_priced_zero() -> None:
    step = CliStepResult(
        verb="probe",
        cost_units=0.0,
        fields={"budget_spent": 4.0, "status": "ok"},
    )
    assert step.observation()["cost_units"] == 4.0
    run = CliRunResult(
        steps=[step],
        cost_units=0.0,
        fields={"budget_spent": 4.0},
    )
    assert run.observation()["cost_units"] == 4.0
