"""Resolve host authorization and budget policies for recipe / graph runs.

Hosts pass these on ``run_recipe`` / Config / story ``environment``. Omit →
host-kit defaults (permissive grants + unlimited budget). See
``docs/reference/access.md`` and ``docs/reference/budget.md``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from mechaharness.budget import BudgetPolicy
from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.core.access import AccessPolicy, CompoundPolicy, GrantPolicyLike


def access_policy_from_mapping(data: Any) -> GrantPolicyLike:
    """Build ``AccessPolicy`` or ``CompoundPolicy`` from YAML/dict.

    Accepted shapes::

        {"grants": ["core:fs.read", ...]}
        {"layers": [["core:fs.read"], ["core:fs.write"]]}
        [["core:fs.read"], ["core:fs.write"]]   # layered compound
        ["core:fs.read", "core:fs.write"]       # flat grants
    """
    if isinstance(data, (AccessPolicy, CompoundPolicy)):
        return data
    if isinstance(data, list):
        if data and isinstance(data[0], list):
            return CompoundPolicy.of(
                *[AccessPolicy(grants=list(layer)) for layer in data]
            )
        return AccessPolicy(grants=list(data))
    if not isinstance(data, Mapping):
        raise TypeError(f"access_policy must be mapping or list, got {type(data)!r}")
    if "layers" in data:
        layers = data["layers"]
        if not isinstance(layers, list):
            raise TypeError("access_policy.layers must be a list")
        return CompoundPolicy.of(
            *[AccessPolicy(grants=list(layer)) for layer in layers]
        )
    if "policies" in data:
        return CompoundPolicy.model_validate(data)
    if "grants" in data:
        return AccessPolicy.model_validate(data)
    raise ValueError(
        "access_policy mapping needs grants, layers, or policies"
    )


def grants_list(
    policy: GrantPolicyLike | None,
    grants: Sequence[object] | None,
) -> list[object] | None:
    """Flatten policy/grants for ``host_graph_executor(grants=)``.

    Returns ``None`` when both omitted (caller keeps host-kit defaults).
    """
    if policy is not None:
        return list(policy.grants)
    if grants is not None:
        return list(grants)
    return None


def budget_policy_from_mapping(data: Any | None) -> BudgetPolicy | None:
    """Parse optional budget YAML/dict; ``None`` when omitted."""
    if data is None:
        return None
    if isinstance(data, BudgetPolicy):
        return data
    return BudgetPolicy.model_validate(data)


def capability_envelope_from_mapping(
    data: Any | None,
    *,
    grants: Sequence[object] | None = None,
    authorization_epoch: int | None = None,
) -> CapabilityEnvelope | None:
    """Parse optional envelope YAML; stamp epoch when provided."""
    if data is None and grants is None and authorization_epoch is None:
        return None
    if data is None:
        envelope = CapabilityEnvelope.from_grants(grants or [])
    elif isinstance(data, CapabilityEnvelope):
        envelope = data
    else:
        envelope = CapabilityEnvelope.model_validate(data)
    if authorization_epoch is not None:
        envelope = envelope.model_copy(
            update={"authorization_epoch": authorization_epoch}
        )
    return envelope


def resolve_run_budget(
    *,
    explicit: BudgetPolicy | None = None,
    runtime_default: BudgetPolicy | None = None,
    body_budget: Mapping[str, Any] | None = None,
) -> BudgetPolicy:
    """Prefer explicit / body override, else runtime default, else unlimited."""
    if explicit is not None:
        return explicit
    if body_budget is not None:
        return BudgetPolicy.model_validate(body_budget)
    if runtime_default is not None:
        return runtime_default
    return BudgetPolicy.unlimited()


__all__ = [
    "access_policy_from_mapping",
    "budget_policy_from_mapping",
    "capability_envelope_from_mapping",
    "grants_list",
    "resolve_run_budget",
]
