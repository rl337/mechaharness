"""``includes_if`` gates write-ledger expects on changes_expected."""

from __future__ import annotations

import pytest

from mechaharness.cli_assertion import (
    CliAssertionSpec,
    check_assertions,
    default_cli_assertion_classes,
)


def _checkers():
    return {k: cls() for k, cls in default_cli_assertion_classes().items()}


def test_includes_if_skips_when_gate_false() -> None:
    check_assertions(
        {"written_files": [], "changes_expected": False},
        [
            CliAssertionSpec.model_validate(
                {
                    "kind": "includes_if",
                    "if_key": "changes_expected",
                    "if_equals": True,
                    "key": "written_files",
                    "value": ["calc.py"],
                }
            )
        ],
        _checkers(),
        label="t",
    )


def test_includes_if_requires_items_when_gate_true() -> None:
    with pytest.raises(AssertionError, match="missing"):
        check_assertions(
            {"written_files": [], "changes_expected": True},
            [
                CliAssertionSpec.model_validate(
                    {
                        "kind": "includes_if",
                        "if_key": "changes_expected",
                        "if_equals": True,
                        "key": "written_files",
                        "value": ["calc.py"],
                    }
                )
            ],
            _checkers(),
            label="t",
        )
