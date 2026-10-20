"""CLI assertion kinds and token totals from inference events."""

from __future__ import annotations

import pytest

from mechaharness.cli_assertion import (
    GteAssertion,
    LteAssertion,
    default_cli_assertion_classes,
)
from mechaharness.cli_instrumentor import CliStepResult, _token_totals
from mechaharness.core.types import Usage


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
    step = CliStepResult(
        verb="infer",
        events=[
            {
                "type": "core:inference",
                "payload": {"usage": Usage(prompt_tokens=4, completion_tokens=1, total_tokens=5).model_dump()},
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
