"""Persona-task YAML: environment → graph → steps → complete → cleanup.

Wraps product :class:`~mechaharness.cli_instrumentor.CliInstrumentor` verbs.
No probe path; Config knobs come only from ``environment`` / ``graph``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mechaharness.cli_assertion import (
    CliAssertion,
    CliAssertionSpec,
    check_assertions,
    parse_expect_list,
)
from mechaharness.cli_instrumentor import CliInstrumentor, CliRunResult
from mechaharness.cli_verb import CliParsedCommand, CliScript, parse_cli_commands
from tests.stories.scenarios.cli_scenario import _require_cost_ceiling


class CodingWriteBlock(BaseModel):
    """Offline stub ``write_file`` target when ``local_work: project_coding``."""

    model_config = ConfigDict(extra="forbid")

    path: str
    content: str


class FilesystemBlock(BaseModel):
    """Workspace + optional breakout seed files for the story harness.

    ``type``:
      - ``suite`` — sequential suite injects a shared arc workspace
      - ``temp`` — fresh scratch directory per stage
      - other string — absolute path, or path relative to the stage YAML
    ``path`` — optional root override (rarely needed when type is suite/temp).
    ``contents`` — path (relative to the stage YAML) to a files.json breakout
    mapping workspace-relative paths to text (or a list of ``{path, content}``).
    """

    model_config = ConfigDict(extra="forbid")

    type: str = "temp"
    path: str | None = None
    contents: str | None = None


class EnvironmentBlock(BaseModel):
    """Host Config surface for this story (family, backend, optional clock)."""

    model_config = ConfigDict(extra="forbid")

    family: str = "pass_through"
    backend: str = "mock"
    # Durable local-work hook: noop / plan_classify / project_coding.
    local_work: Literal["noop", "plan_classify", "project_coding"] = "noop"
    # Workspace + optional files.json seed (replaces workspace / coding_writes).
    filesystem: FilesystemBlock | None = None
    # CodingGit binding for project_coding tools.
    # ``local_mock_pr`` = local ``git`` process + recorded/mock pull requests
    # (no forge network). Omit / ``default`` = LocalProcessCodingGit (git+gh).
    coding_git: Literal["default", "local_mock_pr"] | None = None
    # GitHubClient binding for CI lookup tools (``ci_checks`` / ``ci_job_log``).
    # ``local_mock_ci`` = ``RecordingGitHubClient`` + connection owner/repo
    # (no forge network). Omit = no GitHub client (CI tools unregistered).
    coding_github: Literal["default", "local_mock_ci"] | None = None
    # Seed a tiny git repo in the workspace before the coding burst.
    git_seed: Literal["feature_branch"] | None = None
    # Seed a fake CI failure log + broken module for repair stories.
    ci_seed: Literal["failing_check"] | None = None
    # Seed a local static-check failure (ruff I001 / mypy no-untyped-def).
    static_seed: Literal["ruff_imports", "mypy_untyped"] | None = None
    # Seed a healthy multi-KB module for write-gutting guard stories.
    write_guard_seed: Literal["healthy_module"] | None = None
    # Offline Completer script that issues git/PR/CI tool calls (static CI).
    # Live Completer ignores this and drives tools itself.
    coding_tool_script: (
        Literal[
            "git_inspect",
            "git_open_pr",
            "ci_repair",
            "ci_diagnose",
            "static_ruff_repair",
            "static_mypy_repair",
            "write_gutting_attempt",
        ]
        | None
    ) = None
    # ISO-8601 instant for MockDateTimeService; omit for harness default.
    clock: str | None = None
    # Optional FixtureRagRetriever corpus (YAML path under the story dir).
    rag_corpus: str | None = None
    # Optional story-host lifecycle extension ids (see tests.stories.hosts).
    lifecycle_extensions: list[str] = Field(default_factory=list)
    # Authorization: omit → Config/host-kit defaults. Empty grants → deny-all.
    grants: list[str] | None = None
    # AccessPolicy / CompoundPolicy YAML (see host_run_policies.access_policy_from_mapping).
    access_policy: Any | None = None
    # CapabilityEnvelope mapping (Pydantic); optional authorization_epoch stamps it.
    capability_envelope: dict[str, Any] | None = None
    authorization_epoch: int | None = None
    # BudgetPolicy YAML (soft_limit / hard_limit / unit). Omit → unlimited.
    budget: dict[str, Any] | None = None
    # JobLaneBroker catalog (lane_id → exposure meta/keys). Omit → empty broker.
    job_lanes: dict[str, Any] | None = None
    # Optional standing grants beyond lane exposure ({from_lane, to_lane, keys, meta}).
    lane_grants: list[dict[str, Any]] | None = None


class DurableGraphBlock(BaseModel):
    """Durable IoC session knobs when ``graph.recipe`` is run via start/answer."""

    model_config = ConfigDict(extra="forbid")

    controller: str = "story"
    store: Literal["memory", "shared"] = "memory"


class InlineGraphBlock(BaseModel):
    """Inline ExecutionGraph spec for stepped ``graph_walk`` stories (SG-09)."""

    model_config = ConfigDict(extra="forbid")

    goal: str = ""
    nodes: list[dict[str, Any]] = Field(min_length=1)
    edges: list[dict[str, Any]] = Field(default_factory=list)


class GraphBlock(BaseModel):
    """What plan/session the persona loads before walking steps."""

    model_config = ConfigDict(extra="forbid")

    recipe: str | None = None
    bind: str | None = None
    durable: DurableGraphBlock | None = None
    # Product graph for graph_walk (stepped control); not a recipe expand.
    inline: InlineGraphBlock | None = None

    @model_validator(mode="after")
    def _durable_needs_recipe(self) -> GraphBlock:
        if self.durable is not None and not self.recipe:
            raise ValueError("graph.durable requires graph.recipe")
        return self


class StoryStep(BaseModel):
    """One action (product verb) with optional mid-walk expects."""

    model_config = ConfigDict(extra="forbid")

    do: dict[str, Any]
    expect: list[dict[str, Any]] | None = None
    expect_error: str | None = None
    # Writer/caller JobLane identity for lane_* verbs (JL-10).
    lane: str | None = None
    run_id: str | None = None

    @model_validator(mode="after")
    def _one_verb_no_probe(self) -> StoryStep:
        if "probe" in self.do:
            raise ValueError("user_story steps must not use probe; use product verbs")
        if len(self.do) != 1:
            raise ValueError(
                f"step.do needs exactly one verb key; got {sorted(self.do)}"
            )
        verb = next(iter(self.do))
        if verb == "set_clock" or verb == "advance_clock":
            raise ValueError(
                f"{verb!r} belongs in environment.clock, not steps"
            )
        return self

    def to_command(self) -> CliParsedCommand:
        raw = dict(self.do)
        verb = next(iter(raw))
        params = raw[verb]
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise ValueError(f"step.do.{verb} must be a mapping")
        merged = dict(params)
        if self.lane is not None:
            if "caller_lane" in merged and merged["caller_lane"] != self.lane:
                raise ValueError(
                    "step.lane conflicts with step.do caller_lane"
                )
            merged["caller_lane"] = self.lane
        if self.run_id is not None:
            if "run_id" in merged and merged["run_id"] != self.run_id:
                raise ValueError("step.run_id conflicts with step.do run_id")
            merged["run_id"] = self.run_id
        raw = {verb: merged}
        # Fold expect human_review.inject into the verb params so the product
        # façade can answer ask→ans on the walk bag during the same step.
        if self.expect is not None:
            inject = _human_review_inject(self.expect)
            if inject is not None:
                if "inject" in merged and merged["inject"] != inject:
                    raise ValueError(
                        "step.do inject conflicts with expect human_review.inject"
                    )
                merged = dict(merged)
                merged["inject"] = inject
                raw = {verb: merged}
            raw["expect"] = self.expect
        if self.expect_error is not None:
            raw["expect_error"] = self.expect_error
        return parse_cli_commands([raw])[0]


def _human_review_inject(expect: list[dict[str, Any]]) -> dict[str, Any] | None:
    found: dict[str, Any] | None = None
    for index, item in enumerate(expect):
        if not isinstance(item, dict) or item.get("kind") != "human_review":
            continue
        inject = item.get("inject")
        if inject is None:
            continue
        if not isinstance(inject, dict):
            raise ValueError(
                f"expect[{index}].inject must be a mapping when kind is human_review"
            )
        if found is not None:
            raise ValueError("at most one expect human_review.inject per step")
        found = dict(inject)
    return found


class CompleteBlock(BaseModel):
    """Story-completion claims (what the persona verifies when the job is done)."""

    model_config = ConfigDict(extra="forbid")

    expect: list[CliAssertionSpec] = Field(min_length=1)


class UserStoryScenario(BaseModel):
    """Structured persona task: prose + environment, graph, steps, complete.

    Suite stages carry guide fields (``id``, ``persona``, ``title``, …) in the
    same YAML as the runnable walk. Harness ignores prose; the guide generator
    reads it.
    """

    model_config = ConfigDict(extra="forbid")

    # Guide / catalog prose (required on suite stage YAMLs).
    id: str
    suite: str | None = None
    persona: str
    title: str
    narrative: str
    implementation: str
    validation: str
    footnotes: list[Any] = Field(default_factory=list)
    kind: Literal["user_story"]
    environment: EnvironmentBlock
    graph: GraphBlock | None = None
    steps: list[StoryStep] = Field(min_length=1)
    complete: CompleteBlock
    cleanup: list[Any] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _parse_complete_expect(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        complete = out.get("complete")
        if isinstance(complete, dict) and isinstance(complete.get("expect"), list):
            complete = dict(complete)
            complete["expect"] = parse_expect_list(complete["expect"])
            out["complete"] = complete
        return out

    @model_validator(mode="after")
    def _cleanup_empty(self) -> UserStoryScenario:
        if self.cleanup:
            raise ValueError(
                "cleanup is reserved; leave cleanup: [] until cleanup verbs exist"
            )
        return self

    def to_script(self) -> CliScript:
        return CliScript(commands=[step.to_command() for step in self.steps])

    def assert_expect(
        self,
        result: CliRunResult,
        assertions: dict[str, CliAssertion],
        *,
        label: str,
        relax_cassette_exact: bool = False,
    ) -> None:
        commands = [s.to_command() for s in self.steps]
        if len(result.steps) != len(commands):
            raise AssertionError(
                f"{label}: got {len(result.steps)} steps for "
                f"{len(commands)} story steps"
            )
        for index, (cmd, step) in enumerate(zip(commands, result.steps)):
            step_label = f"{label}:steps[{index}].{cmd.verb}"
            obs = step.observation()
            if cmd.expect_error is not None:
                if obs.get("error") != cmd.expect_error:
                    raise AssertionError(
                        f"{step_label}: expect_error {cmd.expect_error!r} "
                        f"!= {obs.get('error')!r}"
                    )
            elif cmd.expect is not None:
                specs = parse_expect_list(cmd.expect)
                check_assertions(
                    obs,
                    specs,
                    assertions,
                    label=step_label,
                    relax_cassette_exact=relax_cassette_exact,
                )
        complete_label = f"{label}:complete"
        check_assertions(
            result.observation(),
            self.complete.expect,
            assertions,
            label=complete_label,
            relax_cassette_exact=relax_cassette_exact,
        )
        _require_cost_ceiling(
            result.observation(), self.complete.expect, label=complete_label
        )


def load_user_story_scenario(path: Path) -> UserStoryScenario:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: scenario root must be a mapping")
    try:
        return UserStoryScenario.model_validate(data)
    except Exception as exc:
        raise ValueError(f"{path}: invalid user_story scenario: {exc}") from exc


async def run_user_story_scenario(
    scenario: UserStoryScenario,
    instrumentor: CliInstrumentor,
) -> CliRunResult:
    graph = scenario.graph
    if graph is not None and graph.durable is not None:
        assert graph.recipe is not None
        instrumentor.configure_durable_session(
            graph=graph.recipe,
            controller=graph.durable.controller,
            store=graph.durable.store,
        )
    elif graph is not None and graph.bind is not None:
        # Shape-only setup: expand RecipeBind before walking product steps.
        setup = CliScript(
            commands=[
                CliParsedCommand(
                    verb="instantiate_recipe",
                    params={"path": graph.bind},
                )
            ]
        )
        await instrumentor.run(setup)
    if graph is not None and graph.inline is not None:
        instrumentor.inline_graph = {
            "goal": graph.inline.goal,
            "nodes": list(graph.inline.nodes),
            "edges": list(graph.inline.edges),
        }
    return await instrumentor.run(scenario.to_script())


__all__ = [
    "CodingWriteBlock",
    "CompleteBlock",
    "DurableGraphBlock",
    "EnvironmentBlock",
    "FilesystemBlock",
    "GraphBlock",
    "InlineGraphBlock",
    "StoryStep",
    "UserStoryScenario",
    "load_user_story_scenario",
    "run_user_story_scenario",
]
