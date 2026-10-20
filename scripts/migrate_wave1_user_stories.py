#!/usr/bin/env python3
"""Migrate Wave 1 (product CLI, no probe) stories to kind: user_story."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
STORIES = ROOT / "tests/fixtures/models/static/fixture/v1/stories"
FIXTURES = ROOT / "tests/fixtures/models"

WAVE1 = [
    # A durable
    "fangore_insp_driver_session_resume",
    "fangore_insp_durable_graph_generator",
    "fangore_insp_graph_guidance_yield",
    "fangore_insp_guidance_controller_auth",
    "fangore_insp_guidance_survive_restart",
    "nubble_insp_guidance_cost_budget",
    "taloneth_insp_scripted_driver_replay",
    # B recipe shape
    "fangore_bounded_retry_recipe",
    "fangore_environment_repair_recipe",
    "fangore_graph_template_soft_points",
    "fangore_insp_independent_review",
    "fangore_insp_initialize_preflight",
    "fangore_insp_produce_critique_refine",
    "fangore_insp_template_incubation",
    "fangore_node_components",
    "fangore_recipe_namespace_tile",
    "fangore_verify_repair_recipe",
    "taloneth_insp_safety_eval_recipes",
    # C recipe plan
    "fangore_insp_evolution_ownership_split",
    "fangore_insp_recipe_lineage_promote",
    "fangore_insp_recipe_port_search",
    "fangore_insp_recipe_version_pointer",
    "fangore_insp_registry_only_compose",
    "fangore_insp_soft_evolution_allowlist",
    "fangore_recipe_as_tool",
    "fangore_traversal_contract",
    "taloneth_insp_recipe_evolution_loop",
    "taloneth_insp_recipe_final_test_gate",
    # D execute
    "fangore_backend_describe_recipe",
    "fangore_conversational_tool_loop",
    "fangore_harness_family_react",
    "fangore_harness_run_recipe",
    "fangore_harness_tool_loop_graph",
    # E diagnostics
    "fangore_refund_verdict",
    "nubble_insp_model_input_replay",
    "nubble_insp_model_routing",
    "nubble_model_affinity",
    "taloneth_insp_run_parity",
    "taloneth_shadow_decision_backends",
    # F infer
    "fangore_host_kit_event_tap",
]


class _NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True


def _dump(data: dict[str, Any]) -> str:
    return yaml.dump(
        data,
        Dumper=_NoAliasDumper,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )


def _parse_commands(raw_commands: list[Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for item in raw_commands:
        if not isinstance(item, dict):
            raise ValueError(f"bad command item {item!r}")
        data = dict(item)
        expect = data.pop("expect", None)
        expect_error = data.pop("expect_error", None)
        if len(data) != 1:
            raise ValueError(f"command needs one verb; got {sorted(data)}")
        verb, params = next(iter(data.items()))
        if params is None:
            params = {}
        if verb in {"probe", "set_clock", "advance_clock"}:
            raise ValueError(f"wave1 must not use {verb}")
        step: dict[str, Any] = {"do": {verb: dict(params) if isinstance(params, dict) else params}}
        if expect is not None:
            step["expect"] = expect
        if expect_error is not None:
            step["expect_error"] = expect_error
        steps.append(step)
    return steps


def _recipe_from_bind(story_dir: Path, path: str | None) -> str | None:
    if not path:
        return None
    bind_path = story_dir / path
    if not bind_path.is_file():
        return None
    raw = yaml.safe_load(bind_path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and raw.get("name"):
        return str(raw["name"])
    return None


def convert_scenario(story_dir: Path, scen_path: Path, story: dict[str, Any]) -> dict[str, Any]:
    raw = yaml.safe_load(scen_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("kind") != "cli":
        raise ValueError(f"{scen_path}: expected kind: cli")
    host = raw.get("host") or {}
    durable = raw.get("durable")
    commands = raw.get("commands") or []
    script_expect = raw.get("expect")
    steps = _parse_commands(commands)

    family = str(host.get("family") or "pass_through")
    backend = str(host.get("backend") or "mock")
    environment: dict[str, Any] = {"family": family, "backend": backend}
    if host.get("clock"):
        environment["clock"] = host["clock"]

    graph: dict[str, Any] | None = None
    if isinstance(durable, dict):
        graph = {
            "recipe": durable["graph"],
            "durable": {
                "controller": durable.get("controller", "story"),
                "store": durable.get("store", "memory"),
            },
        }
    else:
        # Document recipe id when instantiate/tile/run_recipe names one.
        recipe = None
        bind = None
        for step in steps:
            do = step["do"]
            verb, params = next(iter(do.items()))
            if not isinstance(params, dict):
                continue
            if verb == "instantiate_recipe" and params.get("path"):
                bind = str(params["path"])
                recipe = _recipe_from_bind(story_dir, bind) or recipe
            if verb == "tile_recipe" and params.get("path"):
                bind = str(params["path"])
            if verb == "run_recipe" and params.get("name"):
                recipe = str(params["name"])
            if verb == "tool_loop" and params.get("family"):
                environment["family"] = str(params.get("family") or family)
        if recipe or bind:
            graph = {}
            if recipe:
                graph["recipe"] = recipe
            # Do not set graph.bind — that would re-run instantiate before steps.

    import copy

    last = steps[-1]
    if script_expect:
        complete_expect = copy.deepcopy(script_expect)
    elif last.get("expect_error") is not None:
        # Terminal refuse / error is the story completion claim.
        complete_expect = [
            {
                "kind": "equals",
                "key": "error",
                "value": last["expect_error"],
            }
        ]
    elif last.get("expect"):
        complete_expect = copy.deepcopy(last["expect"])
    else:
        complete_expect = None
        for step in reversed(steps[:-1]):
            if step.get("expect"):
                complete_expect = copy.deepcopy(step["expect"])
                break
        if complete_expect is None:
            raise ValueError(f"{scen_path}: no script or step expect for complete")

    out: dict[str, Any] = {
        "kind": "user_story",
        "environment": environment,
        "graph": graph,
        "steps": steps,
        "complete": {"expect": complete_expect},
        "cleanup": [],
    }
    return out


def _pronoun(persona: str) -> tuple[str, str]:
    # (subject, Subject)
    name = {"nubble": "Nubble", "fangore": "Fangore", "taloneth": "Taloneth"}[persona]
    return name, name


def rewrite_narrative(story: dict[str, Any], scen: dict[str, Any]) -> str:
    name, _ = _pronoun(story["persona"])
    env = scen["environment"]
    family = env["family"]
    backend = env["backend"]
    old = story["narrative"]
    # Preserve footnote markers and story backticks from the old prose.
    footnotes = re.findall(r"\[\^[^\]]+\]", old)
    cites = re.findall(r"`[a-z0-9_]+`", old)

    graph = scen.get("graph") or {}
    recipe = graph.get("recipe")
    durable = graph.get("durable")
    verbs = [next(iter(s["do"])) for s in scen["steps"]]

    open_line = (
        f"{name} starts the CLI host with family `{family}` and backend `{backend}`"
    )
    if durable and recipe:
        open_line += (
            f", loads the `{recipe}` durable graph "
            f"(controller `{durable.get('controller')}`, store `{durable.get('store')}`)"
        )
    elif recipe:
        open_line += f", and works with the `{recipe}` recipe"
    open_line += "."

    # Task body: keep the most informative sentence(s) from the old narrative,
    # stripped of leading capability blurbs when we already opened with CLI walk.
    body = old
    for marker in footnotes:
        body = body.replace(marker, "")
    body = re.sub(r"\s+", " ", body).strip()
    # Prefer middle content — keep up to ~2 sentences after first.
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", body) if s.strip()]
    if len(sentences) >= 2:
        task = " ".join(sentences[:3])
    else:
        task = body

    step_bits = ", ".join(verbs)
    verify = (
        f"He walks product steps ({step_bits}) and verifies completion from the "
        f"structured observation expects on this scenario."
    )
    if name == "Taloneth":
        verify = verify.replace("He walks", "They walk").replace("and verifies", "and verify")
    elif name == "Nubble":
        pass

    parts = [open_line, task, verify]
    # Re-attach unique footnote markers at end if present.
    if footnotes:
        parts.append("".join(dict.fromkeys(footnotes)))
    # Ensure important sibling cites remain if stripped oddly
    for c in cites[:4]:
        if c not in " ".join(parts):
            parts.append(f"Related: {c}.")
            break
    return " ".join(parts)


def header_comment(story_id: str, narrative: str) -> str:
    # First ~2 sentences as YAML comments
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", narrative) if s.strip()]
    lines = [f"# user story: {story_id}"]
    for s in sentences[:3]:
        # wrap long lines lightly
        while len(s) > 88:
            cut = s.rfind(" ", 0, 88)
            if cut < 40:
                cut = 88
            lines.append(f"# {s[:cut].strip()}")
            s = s[cut:].strip()
        if s:
            lines.append(f"# {s}")
    return "\n".join(lines) + "\n"


def convert_story(story_id: str) -> None:
    story_dir = STORIES / story_id
    story_path = story_dir / "story.json"
    story = json.loads(story_path.read_text(encoding="utf-8"))
    scen_dir = story_dir / "scenarios"
    yaml_files = sorted(scen_dir.glob("*.yaml"))
    if not yaml_files:
        raise SystemExit(f"{story_id}: no scenarios")

    scen_names = []
    first_scen: dict[str, Any] | None = None
    for yp in yaml_files:
        converted = convert_scenario(story_dir, yp, story)
        if first_scen is None:
            first_scen = converted
        narr_preview = rewrite_narrative(story, converted)
        text = header_comment(story_id, narr_preview) + _dump(converted)
        yp.write_text(text, encoding="utf-8")
        scen_names.append(yp.name)

    assert first_scen is not None
    new_narr = rewrite_narrative(story, first_scen)
    story["kind"] = "user_story"
    story["narrative"] = new_narr
    story["validation"] = (
        f"Harness `user_story` scenario{'s' if len(scen_names) > 1 else ''} "
        + ", ".join(f"`{n}`" for n in scen_names)
        + ": environment + graph + steps + complete expects."
    )
    # Soften implementation host references that said CliScenario.host
    impl = story.get("implementation") or ""
    impl = impl.replace("CliScenario.host", "UserStoryScenario.environment")
    impl = impl.replace("`host.family`", "`environment.family`")
    impl = impl.replace("`host.backend`", "`environment.backend`")
    story["implementation"] = impl
    story_path.write_text(
        json.dumps(story, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"converted {story_id} ({len(yaml_files)} scenario(s))")

    # Sync twin story.json + scenarios when present
    for twin_root in FIXTURES.glob(f"*/*/v*/stories/{story_id}"):
        if twin_root.resolve() == story_dir.resolve():
            continue
        twin_story = twin_root / "story.json"
        if twin_story.is_file():
            # Twin parity: copy narrative fields from static
            twin_story.write_text(story_path.read_text(encoding="utf-8"), encoding="utf-8")
        twin_scen = twin_root / "scenarios"
        if twin_scen.is_dir():
            for yp in sorted(twin_scen.glob("*.yaml")):
                # Re-convert from twin's own cli if still cli, else skip if already migrated
                raw = yp.read_text(encoding="utf-8")
                if "kind: user_story" in raw[:80]:
                    continue
                if "kind: cli" not in raw[:40] and not raw.lstrip().startswith("kind: cli"):
                    # might still be cli with comment header
                    pass
                data = yaml.safe_load(raw)
                if isinstance(data, dict) and data.get("kind") == "cli":
                    converted = convert_scenario(twin_root, yp, story)
                    # Keep twin token expects — convert_scenario uses twin yaml expects
                    # Force openai_compat backend for openai_compat family twins
                    family = twin_root.parts[
                        twin_root.parts.index("models") + 1
                    ]
                    if family == "openai_compat":
                        converted["environment"]["backend"] = "openai_compat"
                    elif family == "systemone":
                        # judge twins may need systemone — leave mock unless scenario had adapter cues
                        pass
                    text = header_comment(story_id, new_narr) + _dump(converted)
                    yp.write_text(text, encoding="utf-8")
                    print(f"  twin scenario {twin_root.relative_to(FIXTURES)}/{yp.name}")


def main() -> None:
    for sid in WAVE1:
        convert_story(sid)


if __name__ == "__main__":
    main()
