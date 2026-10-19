"""Config hooks and host_kit helpers for the authority surfaces (DI-first)."""

from __future__ import annotations

import pytest

from mechaharness import host_apis
from mechaharness.authority_gate import AuthorityGate
from mechaharness.consequence import ActionConsequence, ConsequencePolicy
from mechaharness.core.access import GraphExecute
from mechaharness.denial_store import (
    DenialStore,
    InMemoryDenialStore,
    equivalent_action_digest,
)
from mechaharness.di import MechaHarnessConfig, get_injector
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.host_kit import host_authority_gate, host_denial_store
from mechaharness.inference.mock import MockInferenceStrategy
from mechaharness.tool_result_freshness import ToolResultFreshnessPolicy


class _Base(MechaHarnessConfig):
    def get_inference_class(self) -> type:
        return MockInferenceStrategy

    def get_harness_class(self) -> type:
        return PassThroughHarness

    def get_grants(self) -> list[object]:
        return [GraphExecute]


def test_default_hooks_are_injectable_and_share_one_denial_store() -> None:
    injector = get_injector(_Base())
    gate = injector.inject(AuthorityGate)
    store = injector.inject(DenialStore)
    assert isinstance(store, InMemoryDenialStore)
    assert gate.denials is store
    assert injector.inject(ToolResultFreshnessPolicy).max_age_seconds is None


def test_host_config_overrides_each_hook() -> None:
    durable = InMemoryDenialStore()
    policy = ToolResultFreshnessPolicy(max_age_seconds=60)

    class _Host(_Base):
        def get_denial_store(self) -> DenialStore:
            return durable

        def get_tool_result_freshness_policy(self) -> ToolResultFreshnessPolicy:
            return policy

    injector = get_injector(_Host())
    assert injector.inject(DenialStore) is durable
    assert injector.inject(AuthorityGate).denials is durable
    assert injector.inject(ToolResultFreshnessPolicy) is policy


def test_gate_from_config_remembers_denials_across_equivalent_actions() -> None:
    gate = get_injector(_Base()).inject(AuthorityGate)
    digest = equivalent_action_digest("email.send", "bob@example.com")
    assert gate.denials is not None
    gate.denials.record(digest, reason="user_denied")
    decision = gate.evaluate(action="email.send", action_digest=digest)
    assert decision.reason_codes == ["prior_denial"]


def test_host_authority_gate_wires_grants_consequence_and_denials() -> None:
    store = InMemoryDenialStore()
    gate = host_authority_gate(
        grants=[GraphExecute],
        consequence=ConsequencePolicy(
            actions=[ActionConsequence(action="email.send", consequence="high")]
        ),
        denial_store=store,
    )
    assert gate.denials is store
    asked = gate.evaluate(action="email.send", required_grants=[GraphExecute])
    assert asked.outcome == "ask_human"
    assert gate.evaluate(action="email.send", approved=True).outcome == "allow"
    no_grants = host_authority_gate().evaluate(action="x", required_grants=[GraphExecute])
    assert no_grants.reason_codes == ["access_denied"]


def test_host_denial_store_defaults_and_binds() -> None:
    assert isinstance(host_denial_store(), InMemoryDenialStore)
    bound = InMemoryDenialStore()
    assert host_denial_store(denial_store=bound) is bound


@pytest.mark.parametrize("name", sorted(host_apis.__all__))
def test_host_apis_catalog_names_resolve(name: str) -> None:
    assert getattr(host_apis, name) is not None
