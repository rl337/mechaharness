"""Recipe lifecycle plan documents for soft evolution / ports / compose."""

from __future__ import annotations

from pathlib import Path

import pytest

from mechaharness.recipe_plan import RecipePlanCommand, load_recipe_plan


def test_unknown_plan_kind_rejected() -> None:
    with pytest.raises(ValueError, match="unknown recipe plan"):
        load_recipe_plan({"plan": "not_a_plan"})


def test_soft_evolution_plan_from_path(tmp_path: Path) -> None:
    path = tmp_path / "soft.yaml"
    path.write_text(
        "\n".join(
            [
                "plan: soft_evolution",
                "summary: smoke",
                "recipes: [verify_repair]",
                "attempts:",
                "- id: swap",
                "  recipe: verify_repair",
                "  changed: [repair_kind]",
                "",
            ]
        ),
        encoding="utf-8",
    )
    out = RecipePlanCommand(path=str(path)).resolve_and_run(base_dir=tmp_path)
    assert out["outcomes"] == {"swap": "refused"}
    assert out["evolvable"]["verify_repair"] == []
