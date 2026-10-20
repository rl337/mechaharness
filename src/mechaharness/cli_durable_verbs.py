"""Durable generator IoC verbs on the CLI instrumentor (product surface)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from mechaharness.cli_verb import CliVerb
from mechaharness.durable_generator_script import (
    AnswerBody,
    InspectBody,
    ListRecipesBody,
    RebuildBody,
    StartBody,
)


class StartVerb(CliVerb):
    name = "start"
    params_model = StartBody

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        return runtime.run_durable_start(params).as_expect_dict()


class AnswerVerb(CliVerb):
    name = "answer"
    params_model = AnswerBody

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        return runtime.run_durable_answer(params).as_expect_dict()


class InspectVerb(CliVerb):
    name = "inspect"
    params_model = InspectBody

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        return runtime.run_durable_inspect(params).as_expect_dict()


class RebuildVerb(CliVerb):
    name = "rebuild"
    params_model = RebuildBody

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        return runtime.run_durable_rebuild(params).as_expect_dict()


class ListRecipesVerb(CliVerb):
    name = "list_recipes"
    params_model = ListRecipesBody

    async def run(self, params: BaseModel, runtime: Any) -> dict[str, Any]:
        return runtime.run_durable_list_recipes(params).as_expect_dict()


class DurableSessionParams(BaseModel):
    """Scenario-level durable session knobs (not a verb)."""

    model_config = ConfigDict(extra="forbid")

    graph: str
    controller: str = "story"
    store: str = "memory"


def durable_cli_verb_classes() -> dict[str, type[CliVerb]]:
    return {
        StartVerb.name: StartVerb,
        AnswerVerb.name: AnswerVerb,
        InspectVerb.name: InspectVerb,
        RebuildVerb.name: RebuildVerb,
        ListRecipesVerb.name: ListRecipesVerb,
    }


__all__ = [
    "AnswerVerb",
    "DurableSessionParams",
    "InspectVerb",
    "ListRecipesVerb",
    "RebuildVerb",
    "StartVerb",
    "durable_cli_verb_classes",
]
