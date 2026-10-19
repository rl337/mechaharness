"""Story YAML tests over the product CLI instrumentor."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mechaharness.cli_instrumentor import CliInstrumentor, CliRunResult
from mechaharness.cli_verb import CliParsedCommand, parse_cli_commands, script_from_mapping


class CliScenario(BaseModel):
    """CLI story script: verb commands + open hard expect mapping."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["cli"]
    commands: list[CliParsedCommand] = Field(min_length=1)
    expect: dict[str, Any]

    @model_validator(mode="before")
    @classmethod
    def _parse_commands(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        raw = data.get("commands")
        if isinstance(raw, list) and raw and isinstance(raw[0], dict):
            # YAML shape ``- infer: {…}`` → CliParsedCommand list
            if "verb" not in raw[0]:
                data = {**data, "commands": parse_cli_commands(raw)}
        return data

    @model_validator(mode="after")
    def _expect_nonempty(self) -> CliScenario:
        if not self.expect:
            raise ValueError("expect must declare at least one key")
        return self

    def to_script(self):
        return script_from_mapping(
            {"commands": [{c.verb: c.params} for c in self.commands]}
        )

    def assert_expect(self, result: CliRunResult, *, label: str) -> None:
        got = result.as_expect_dict()
        for key, wanted in self.expect.items():
            if key not in got:
                raise AssertionError(
                    f"{label}: missing actual key {key!r}; got {sorted(got)}"
                )
            assert got[key] == wanted, f"{label}: {key}: {got[key]!r} != {wanted!r}"


def load_cli_scenario(path: Path) -> CliScenario:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: scenario root must be a mapping")
    try:
        return CliScenario.model_validate(data)
    except Exception as exc:
        raise ValueError(f"{path}: invalid cli scenario: {exc}") from exc


async def run_cli_scenario(
    scenario: CliScenario,
    instrumentor: CliInstrumentor,
) -> CliRunResult:
    return await instrumentor.run(scenario.to_script())
