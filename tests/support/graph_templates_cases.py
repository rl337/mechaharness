"""Load and interpret declarative graph-template fixture cases."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mechaharness.graph_templates import GraphTemplateParams
from mechaharness.stop_contract import StopContract

CASES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "graph_templates"


@dataclass(frozen=True)
class GraphTemplateCase:
    path: Path
    data: dict[str, Any]

    @property
    def id(self) -> str:
        return str(self.data.get("id") or self.path.stem)


def iter_cases() -> list[GraphTemplateCase]:
    if not CASES_DIR.is_dir():
        return []
    cases: list[GraphTemplateCase] = []
    for path in sorted(CASES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise TypeError(f"{path}: case root must be an object")
        cases.append(GraphTemplateCase(path=path, data=data))
    return cases


def build_params(raw: Mapping[str, Any] | None) -> GraphTemplateParams:
    data = dict(raw or {})
    stop = data.pop("stop_contract", None)
    params = GraphTemplateParams.model_validate(data)
    if stop is not None:
        params = params.model_copy(
            update={"stop_contract": StopContract.model_validate(stop)}
        )
    return params


def assert_expect(*, graph: Any, expect: Mapping[str, Any], case_id: str) -> None:
    prefix = f"case {case_id}"
    if "template_name" in expect:
        assert graph.template_name == expect["template_name"], f"{prefix}: template_name"
    if "template_version" in expect:
        assert graph.template_version == expect["template_version"], (
            f"{prefix}: template_version"
        )
    if "template_status" in expect:
        assert graph.template_status == expect["template_status"], (
            f"{prefix}: template_status"
        )
    if "node_ids" in expect:
        assert sorted(graph.nodes) == sorted(expect["node_ids"]), f"{prefix}: node_ids"
    if "node_count" in expect:
        assert len(graph.nodes) == int(expect["node_count"]), f"{prefix}: node_count"
    if "goal" in expect:
        assert graph.goal == expect["goal"], f"{prefix}: goal"
    if "edge_count" in expect:
        assert len(graph.edges) == int(expect["edge_count"]), f"{prefix}: edge_count"
    for node_id, node_exp in (expect.get("nodes") or {}).items():
        node = graph.nodes[node_id]
        if "kind" in node_exp:
            assert node.kind == node_exp["kind"], f"{prefix}: {node_id}.kind"
        if "repeating" in node_exp:
            assert node.repeating is bool(node_exp["repeating"]), (
                f"{prefix}: {node_id}.repeating"
            )
        if "has_stop_contract" in node_exp:
            has = node.stop_contract is not None
            assert has is bool(node_exp["has_stop_contract"]), (
                f"{prefix}: {node_id}.stop"
            )
        if "depends_on" in node_exp:
            assert list(node.depends_on) == list(node_exp["depends_on"]), (
                f"{prefix}: {node_id}.depends_on"
            )
        if "acceptance" in node_exp:
            assert list(node.acceptance) == list(node_exp["acceptance"]), (
                f"{prefix}: {node_id}.acceptance"
            )
        for key, value in (node_exp.get("payload") or {}).items():
            assert node.payload.get(key) == value, (
                f"{prefix}: {node_id}.payload.{key}"
            )
