"""Attribute request-prefix changes without storing the prompt text.

Tool order and a clock in the stable policy block are avoidable misses.
A real policy revision is a legitimate new prefix. When the provider does not
report cache counters, the miss cause stays ``unknown``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"name": str(tool["name"]), "parameters": tool.get("parameters") or {}}
        for tool in tools
    ]


def prefix_snapshot(
    *,
    tools: list[dict[str, Any]],
    policy: str,
    policy_version: str,
    dynamic: str,
) -> dict[str, Any]:
    """Hash the stable blocks. The raw policy and tool schemas are not kept."""
    ordered = _tools(tools)
    canonical = sorted(ordered, key=lambda tool: tool["name"])
    return {
        "tools_order": _digest(ordered),
        "tools_canonical": _digest(canonical),
        "policy": _digest({"text": policy, "version": policy_version}),
        "dynamic": _digest(dynamic),
        "policy_version": policy_version,
    }


def classify_prefix_change(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    provider_metrics: bool,
) -> dict[str, Any]:
    """Name the first changed block, or ``unknown`` without provider evidence."""
    same_shape = (
        before["tools_order"] == after["tools_order"]
        and before["policy"] == after["policy"]
        and before["dynamic"] == after["dynamic"]
        and before["policy_version"] == after["policy_version"]
    )
    if same_shape and not provider_metrics:
        cause = "unknown"
        block = None
        legitimate = None
    elif before["policy_version"] != after["policy_version"]:
        cause = "policy_change"
        block = "policy"
        legitimate = True
    elif (
        before["tools_canonical"] == after["tools_canonical"]
        and before["tools_order"] != after["tools_order"]
    ):
        cause = "tool_reserialize"
        block = "tools"
        legitimate = False
    elif before["policy"] != after["policy"]:
        cause = "volatile_system"
        block = "policy"
        legitimate = False
    elif before["dynamic"] != after["dynamic"]:
        cause = "dynamic_tail"
        block = "dynamic"
        legitimate = True
    else:
        cause = "match"
        block = None
        legitimate = True
    return {
        "cause": cause,
        "first_changed_block": block,
        "legitimate": legitimate,
        "canonical_tools_match": before["tools_canonical"] == after["tools_canonical"],
        "raw_prompt_stored": False,
    }
