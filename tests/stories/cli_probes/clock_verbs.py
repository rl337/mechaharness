"""Test-only clock verbs (MockDateTimeService). Production catalog omits these."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from mechaharness.cli_commands import AdvanceClockCommand, SetClockCommand
from mechaharness.cli_verb import CliVerb


class SetClockVerb(CliVerb):
    name = "set_clock"
    params_model = SetClockCommand

    async def run(self, params: BaseModel, runtime: Any) -> Any:
        return await runtime.run_set_clock(params)


class AdvanceClockVerb(CliVerb):
    name = "advance_clock"
    params_model = AdvanceClockCommand

    async def run(self, params: BaseModel, runtime: Any) -> Any:
        return await runtime.run_advance_clock(params)


def clock_cli_verb_classes() -> dict[str, type[CliVerb]]:
    return {
        SetClockVerb.name: SetClockVerb,
        AdvanceClockVerb.name: AdvanceClockVerb,
    }


__all__ = ["AdvanceClockVerb", "SetClockVerb", "clock_cli_verb_classes"]
