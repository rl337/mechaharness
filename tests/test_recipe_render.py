"""Tests for recipe flowchart render (nodes + node components)."""

from __future__ import annotations

from mechaharness.recipe_render import format_render_document, render_recipe


def test_render_harness_run_has_svg_and_explanations() -> None:
    result = render_recipe("harness_run", soft_bindings={"prompt": "hi"})
    assert result.recipe == "harness_run"
    assert result.svg.startswith("<?xml")
    assert "<svg" in result.svg
    assert "prepare" in result.svg
    assert "harness_loop" in result.svg
    assert "Graph nodes" in result.explanations_markdown
    doc = format_render_document(result, svg_path="harness_run.svg")
    assert doc.index("harness_run.svg") < doc.index("## Graph nodes")
    assert "max_turns" in result.svg
    assert "name" in result.svg and "type" in result.svg and "value" in result.svg
    assert "soft_point:prompt" not in result.svg


def test_render_fan_out_shows_edges() -> None:
    result = render_recipe("fan_out_aggregate")
    assert "branch_0" in result.svg
    assert 'marker-end="url(#arrow)"' in result.svg
    assert result.nodes


def test_render_fan_out_coalesces_parallel_into_stack() -> None:
    from mechaharness.graph_templates.base import GraphTemplateParams

    result = render_recipe(
        "fan_out_aggregate",
        params=GraphTemplateParams(
            goal="survey",
            branch_payloads=[{"index": i} for i in range(6)],
            acceptance=["ok"],
        ),
    )
    svg = result.svg
    # One stack band titled from the shared fan-out label.
    assert "fan_out ×6" in svg
    assert "branch_0" in svg and "branch_5" in svg
    # Single outer arrows — not N overlapping fan_out labels through siblings.
    assert svg.count(">fan_out<") == 1
    assert svg.count(">fan_in<") == 1


def test_render_unknown_recipe_raises() -> None:
    try:
        render_recipe("not_a_real_recipe")
    except KeyError as exc:
        assert "not_a_real_recipe" in str(exc)
    else:
        raise AssertionError("expected KeyError")


def test_render_harness_loop_is_titled_container_with_rows() -> None:
    result = render_recipe(
        "harness_run",
        soft_bindings={"prompt": "hi"},
        tool_names=["lookup"],
    )
    svg = result.svg
    # Node name is the outer box title.
    assert "harness_loop · harness_loop" in svg
    # Start/end circles and sequential then labels.
    assert ">start<" in svg
    assert ">end<" in svg
    assert ">then<" in svg
    assert "tool_call:lookup" in svg
    assert "rx=\"14\"" in svg  # round container
    # Serpentine row wrap uses a C-shaped path (not a diagonal line).
    assert '<path d="M ' in svg


def test_render_fields_by_node_payload() -> None:
    result = render_recipe(
        "harness_run",
        soft_bindings={"prompt": "hi", "max_turns": 3},
    )
    prepare_fields = {f["name"]: f["value"] for f in result.fields_by_node.get("prepare", [])}
    assert prepare_fields.get("prompt") == "hi"
    assert prepare_fields.get("max_turns") == 3
