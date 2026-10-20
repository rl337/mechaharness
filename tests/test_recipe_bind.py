"""Human-readable RecipeBind documents for catalog instantiate."""

from __future__ import annotations

from pathlib import Path

import pytest

from mechaharness.recipe_bind import InstantiateRecipeCommand, RecipeBind


def test_unknown_soft_points_rejected() -> None:
    bind = RecipeBind(
        name="initialize_preflight",
        goal="preflight",
        soft_bindings={
            "linkage_kind": "preflight_linkage",
            "extra_slot": "nope",
        },
    )
    with pytest.raises(ValueError, match="unknown soft points"):
        bind.resolve_template()


def test_omitted_soft_points_take_template_defaults() -> None:
    bind = RecipeBind(
        name="initialize_preflight",
        summary="Smoke expand",
        goal="preflight",
        soft_bindings={"linkage_kind": "preflight_linkage"},
    )
    template, materialized = bind.resolve_template()
    assert template.name == "initialize_preflight"
    assert materialized.soft_bindings["capability_kind"] == "preflight_capability"
    assert "ready" in bind.instantiate().nodes


def test_story_decisions_override_defaults() -> None:
    bind = RecipeBind(
        name="bounded_retry",
        goal="dispatch",
        soft_bindings={"max_attempts": 5},
    )
    graph = bind.instantiate()
    stop = graph.nodes["attempt"].stop_contract
    assert stop["max_iterations"] == 5


def test_instantiate_command_loads_path_relative_to_base(tmp_path: Path) -> None:
    bind_dir = tmp_path / "binds"
    bind_dir.mkdir()
    path = bind_dir / "preflight.yaml"
    path.write_text(
        "\n".join(
            [
                "name: initialize_preflight",
                "summary: From disk",
                "goal: from-disk",
                "soft_bindings:",
                "  linkage_kind: preflight_linkage",
                "",
            ]
        ),
        encoding="utf-8",
    )
    bind = InstantiateRecipeCommand(path="binds/preflight.yaml").resolve_bind(
        base_dir=tmp_path
    )
    assert bind.summary == "From disk"
    assert bind.goal == "from-disk"
    assert "ready" in bind.instantiate().nodes
