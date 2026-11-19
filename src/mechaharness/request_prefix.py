"""Compare selected request fields without storing their prompt text.

The report labels tool-order and policy changes for offline experiments.
It neither observes the serialized provider request nor measures cache misses.
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
    """Hash caller-supplied tool, policy, and dynamic blocks.

    Tool fingerprints include only ``name`` and ``parameters`` (missing or empty
    parameters normalize to an empty dict). Descriptions and provider-specific
    fields are omitted. Policy text and dynamic text are hashed; policy_version
    is retained verbatim and must be a nonsensitive identifier. These hashes
    are diagnostics, not a secrecy guarantee or full wire-request fingerprints.

    Example:
        >>> snap = prefix_snapshot(tools=[{"name": "read"}], policy="Be concise",
        ...                        policy_version="1", dynamic="Read a file")
        >>> sorted(snap)
        ['dynamic', 'policy', 'policy_version', 'tools_canonical', 'tools_order']
        >>> snap["policy_version"]
        '1'
    """
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
    """Label a change between two :func:`prefix_snapshot` reports.

    ``provider_metrics`` is caller-supplied availability, not measured telemetry.
    Identical snapshots yield ``unknown`` without it. ``volatile_system`` means
    policy text changed without a version bump; the helper cannot tell a clock
    from a legitimate edit. Labels are heuristic experiment categories, not
    observed cache-miss causes. Policy-version changes take precedence over
    tool-order changes. Changed tool names or schemas take priority and yield
    ``unknown``: their legitimacy cannot be determined by comparing hashes alone.

    Example:
        >>> snap = prefix_snapshot(tools=[], policy="policy", policy_version="1",
        ...                        dynamic="task")
        >>> classify_prefix_change(snap, snap, provider_metrics=False)["cause"]
        'unknown'
        >>> classify_prefix_change(snap, snap, provider_metrics=True)["cause"]
        'match'
    """
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
    elif before["tools_canonical"] != after["tools_canonical"]:
        cause = "unknown"
        block = "tools"
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
