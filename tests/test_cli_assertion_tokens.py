"""CLI assertion kinds and token totals from inference events."""

from __future__ import annotations

import pytest

from mechaharness.cli_assertion import (
    CliAssertionSpec,
    EqualsAssertion,
    GteAssertion,
    LteAssertion,
    NonemptyAssertion,
    check_assertions,
    default_cli_assertion_classes,
    is_cassette_exact_assertion,
    resolve_observation_path,
)
from mechaharness.cli_instrumentor import CliStepResult, _token_totals
from mechaharness.core.types import Usage


def test_resolve_observation_path_nested() -> None:
    obs = {
        "plan": {
            "mode": "list",
            "items": [
                {"instruction": "add helper"},
                {"instruction": "add test"},
            ],
        }
    }
    assert resolve_observation_path(obs, "plan.mode") == "list"
    assert (
        resolve_observation_path(obs, "plan.items[0].instruction") == "add helper"
    )
    assert resolve_observation_path(obs, "plan.items[1].instruction") == "add test"
    with pytest.raises(KeyError):
        resolve_observation_path(obs, "plan.items[9].instruction")


def test_equals_assertion_nested_path() -> None:
    obs = {"plan": {"mode": "oneshot", "items": [{"instruction": "do thing"}]}}
    EqualsAssertion().check(
        obs,
        EqualsAssertion.params_model(
            key="plan.items[0].instruction", value="do thing"
        ),
    )
    with pytest.raises(AssertionError, match="missing observation key"):
        EqualsAssertion().check(
            obs,
            EqualsAssertion.params_model(key="plan.items[2].instruction", value="x"),
        )


def test_lte_and_gte_assertions() -> None:
    classes = default_cli_assertion_classes()
    assert "lte" in classes
    obs = {"total_tokens": 5}
    LteAssertion().check(
        obs, LteAssertion.params_model(key="total_tokens", value=5)
    )
    GteAssertion().check(
        obs, GteAssertion.params_model(key="total_tokens", value=5)
    )
    with pytest.raises(AssertionError, match=">"):
        LteAssertion().check(
            obs, LteAssertion.params_model(key="total_tokens", value=4)
        )


def test_token_totals_sum_inference_usage() -> None:
    events = [
        {
            "type": "core:cost",
            "payload": {"units": 1, "total_tokens": 99},
        },
        {
            "type": "core:inference",
            "payload": {
                "usage": {"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5}
            },
        },
        {
            "type": "core:inference",
            "payload": {
                "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}
            },
        },
    ]
    assert _token_totals(events) == (6, 4, 10)


def test_cli_step_observation_exposes_tokens() -> None:
    usage = Usage(prompt_tokens=4, completion_tokens=1, total_tokens=5)
    step = CliStepResult(
        verb="infer",
        events=[
            {
                "type": "core:inference",
                "payload": {"usage": usage.model_dump()},
            }
        ],
        event_types=["core:inference"],
    )
    obs = step.observation()
    assert obs["prompt_tokens"] == 4
    assert obs["completion_tokens"] == 1
    assert obs["total_tokens"] == 5


def test_usage_for_event_defaults_zeros() -> None:
    assert Usage.for_event(None) == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }


def test_cassette_exact_token_asserts_relax_in_live() -> None:
    assert is_cassette_exact_assertion(
        CliAssertionSpec(kind="equals", key="prompt_tokens", value=8)
    )
    assert not is_cassette_exact_assertion(
        CliAssertionSpec(kind="nonempty", key="text")
    )
    assertions = {
        "equals": EqualsAssertion(),
        "nonempty": NonemptyAssertion(),
    }
    obs = {"prompt_tokens": 13, "text": "hello"}
    specs = [
        CliAssertionSpec(kind="equals", key="prompt_tokens", value=8),
        CliAssertionSpec(kind="nonempty", key="text"),
    ]
    check_assertions(
        obs, specs, assertions, label="live", relax_cassette_exact=True
    )
    with pytest.raises(AssertionError, match="prompt_tokens"):
        check_assertions(
            obs, specs, assertions, label="static", relax_cassette_exact=False
        )
