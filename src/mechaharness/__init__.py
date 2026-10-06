"""MechaHarness: agentic harness with pluggable inference and harness families.

Package overview
================

MechaHarness separates **inference** (provider I/O) from **harness policy**
(agent loops, graphs, grants, verification). Hosts extend via
:class:`~mechaharness.di.MechaHarnessConfig` rather than patching closed enums.

Many primitives below were motivated by ideas in the Claude and Cursor
developer blogs (see ``docs/inspiration/``). The doctests cite those sources
and show how MechaHarness expresses the suggestion — not product
compatibility claims.

Inspiration tour (doctests)
===========================

Retire scaffolding that no longer helps
---------------------------------------
In *Agent Harness Design: 3 Patterns for Harnessing Claude's Intelligence*,
the Claude developer blog suggests asking what scaffolding you can stop doing
as models improve
(https://claude.com/blog/harnessing-claudes-intelligence).
In *Continually improving our agent harness*, the Cursor developer blog
suggests treating harness changes as evaluable hypotheses
(https://cursor.com/blog/continually-improving-agent-harness).
MechaHarness makes with/without comparison explicit::

    >>> from mechaharness.harness_experiment import (
    ...     HarnessExperiment, HarnessExperimentRunner,
    ... )
    >>> runner = HarnessExperimentRunner()
    >>> exp = runner.propose(HarnessExperiment(
    ...     hypothesis="context resets are dead weight after the model upgrade",
    ...     intervention="remove_context_anxiety_resets",
    ...     failure_mode="premature_wrap_up",
    ...     evidence="claude.com/blog/harnessing-claudes-intelligence",
    ... ))
    >>> runner.evaluate(
    ...     exp,
    ...     with_intervention=lambda: {"task_success_rate": 0.91, "tokens": 12_000},
    ...     without_intervention=lambda: {"task_success_rate": 0.90, "tokens": 11_500},
    ... ).status
    'retained'
    >>> # When treatment underperforms control, the intervention is retired:
    >>> dead = runner.propose(HarnessExperiment(
    ...     hypothesis="hand-crafted tool-result piping still helps",
    ...     intervention="force_all_tool_results_into_context",
    ...     failure_mode="token_bloat",
    ... ))
    >>> runner.evaluate(
    ...     dead,
    ...     with_intervention=lambda: {"task_success_rate": 0.70},
    ...     without_intervention=lambda: {"task_success_rate": 0.88},
    ... ).status
    'retired'

Bounded verify-then-repair (loops + verification skills)
--------------------------------------------------------
In *Loop engineering: Getting started with loops*, the Claude developer blog
suggests goal-based loops with explicit stop criteria and turn caps
(https://claude.com/blog/getting-started-with-loops).
In *Building verification loops in Claude Code with skills*, it suggests
encoding checks so completion depends on verification, not generation alone
(https://claude.com/blog/building-verification-loops-in-claude-code-with-skills).
A reusable template plus :class:`~mechaharness.stop_contract.StopContract`
encodes that::

    >>> from mechaharness.graph_templates import (
    ...     GraphTemplateParams, VerifyRepairTemplate,
    ... )
    >>> from mechaharness.stop_contract import StopContract
    >>> graph = VerifyRepairTemplate().instantiate(GraphTemplateParams(
    ...     goal="get homepage Lighthouse score >= 90",
    ...     acceptance=["lighthouse_score>=90"],
    ...     stop_contract=StopContract(
    ...         trigger="verify_failed",
    ...         success_condition="acceptance_met",
    ...         abort_condition="max_iterations",
    ...         max_iterations=5,
    ...     ),
    ...     soft_bindings={"produce_kind": "edit_page", "verify_kind": "lighthouse"},
    ... ))
    >>> sorted(graph.nodes)
    ['complete', 'produce', 'repair', 'verify']
    >>> graph.nodes["repair"].repeating
    True
    >>> graph.nodes["repair"].stop_contract["max_iterations"]
    5
    >>> graph.template_name
    'verify_repair'

Preflight linkage before expensive work
---------------------------------------
In *Introducing dynamic workflows in Claude Code*, the Claude developer blog
suggests runtime-composed multi-agent graphs that stay resumable and checked
before fold-in
(https://claude.com/blog/introducing-dynamic-workflows-in-claude-code).
In *What we've learned building cloud agents*, the Cursor developer blog
suggests treating environment readiness as part of the execution contract
(https://cursor.com/blog/cloud-agent-lessons).
Linkage is the pre-execution check — distinct from DI construction::

    >>> from mechaharness.core.access import (
    ...     AccessPolicy, GraphExecute, InMemoryAccessControl,
    ... )
    >>> from mechaharness.core.environment import NoOpInferenceEnvironment
    >>> from mechaharness.core.events import InMemoryEventLog
    >>> from mechaharness.graph import ExecutionGraph, GraphNode
    >>> from mechaharness.graph_executor import GraphNodeRunnerRegistry
    >>> from mechaharness.linkage_resolver import DefaultLinkageResolver
    >>> runners = GraphNodeRunnerRegistry()  # empty → kinds fail linkage
    >>> access = InMemoryAccessControl(
    ...     InMemoryEventLog(), AccessPolicy(grants=[GraphExecute]),
    ... )
    >>> resolver = DefaultLinkageResolver(
    ...     runners, access, NoOpInferenceEnvironment(),
    ... )
    >>> g = ExecutionGraph(goal="ship")
    >>> _ = g.add_node(GraphNode(id="work", kind="migrate"))
    >>> report = resolver.resolve(g)
    >>> report.ok
    False
    >>> report.edges[0].code
    'no_runner'
    >>> report.edges[0].candidate_provider.startswith("GraphNodeRunnerRegistry")
    True
    >>> # Repeating work without a stop contract also fails before run:
    >>> loop = ExecutionGraph(goal="until green")
    >>> _ = loop.add_node(GraphNode(id="fix", kind="loop", repeating=True))
    >>> codes = {e.code for e in resolver.resolve(loop).edges}
    >>> "missing_stop_contract" in codes
    True

Subagents need narrow envelopes; advisors stay non-binding
----------------------------------------------------------
In *How and when to use subagents in Claude Code*, the Claude developer blog
suggests isolated child contexts with restricted tools that return synthesis,
not full history
(https://claude.com/blog/subagents-in-claude-code).
In *Escalate hard decisions with the advisor tool*, the Claude Code docs
suggest sparse, non-binding counsel from a stronger model while the executor
keeps ownership
(https://code.claude.com/docs/en/advisor).
MechaHarness separates those as envelopes versus advisor policy::

    >>> from mechaharness.capability_envelope import CapabilityEnvelope
    >>> from mechaharness.delegation_policy import (
    ...     DefaultDelegationPolicy, DelegationRequest,
    ... )
    >>> parent = CapabilityEnvelope(
    ...     grants=["core:graph.execute", "core:fs.read", "core:fs.write"],
    ...     tool_names=["Read", "Edit", "Bash"],
    ...     model_class="reason-fast",
    ... )
    >>> decision = DefaultDelegationPolicy().decide(DelegationRequest(
    ...     independence_required=True,
    ...     context_pollution_risk=0.8,
    ...     parent_envelope=parent,
    ...     metadata={"parent_state_version": "plan-v3"},
    ... ))
    >>> decision.choice
    'child'
    >>> child = decision.child_envelope.narrow(tool_names=["Read"])
    >>> child.tool_names
    ['Read']
    >>> child.parent_state_version
    'plan-v3'
    >>> # Widening tools is rejected structurally (hard boundary, not a prompt):
    >>> parent.narrow(tool_names=["Read", "Deploy"])
    Traceback (most recent call last):
        ...
    ValueError: child envelope widens tools: Deploy
    >>> import asyncio
    >>> from mechaharness.advisor import (
    ...     AdvisorContextContract, AdvisorRequest, DefaultAdvisorPolicy,
    ...     RejectAdvisor, consult_advisor,
    ... )
    >>> policy = DefaultAdvisorPolicy(max_consultations=1)
    >>> obs = []
    >>> guidance = asyncio.run(consult_advisor(
    ...     RejectAdvisor(),
    ...     policy,
    ...     AdvisorRequest(
    ...         trigger="consequential_planning",
    ...         context=AdvisorContextContract(
    ...             summary="two migration strategies disagree",
    ...             evidence_refs=["diff:auth"],
    ...         ),
    ...     ),
    ...     observations=obs,
    ... ))
    >>> guidance.proposed_next_actions
    ['continue_without_advisor']
    >>> # Sparse budget: second consult is skipped; ownership never transferred.
    >>> asyncio.run(consult_advisor(
    ...     RejectAdvisor(), policy, AdvisorRequest(trigger="user_initiated"),
    ... )) is None
    True

Independent review + risk-scaled autonomy
-----------------------------------------
In *A harness for every task: dynamic workflows in Claude Code*, the Claude
developer blog suggests adversarial / independent verification so producers
do not grade their own work in the same accumulated state
(https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code).
In *Governing agent autonomy with Auto-review*, the Cursor developer blog
suggests scaling scrutiny by consequence rather than a global autonomy switch
(https://cursor.com/blog/agent-autonomy-auto-review).
MechaHarness expresses both as templates and consequence policy::

    >>> from mechaharness.graph_templates import (
    ...     GraphTemplateParams, IndependentReviewTemplate,
    ... )
    >>> review = IndependentReviewTemplate().instantiate(GraphTemplateParams(
    ...     goal="adversarial review of migration plan",
    ...     acceptance=["no_silent_behavior_change"],
    ...     inputs={"reviewer_count": 2},
    ... ))
    >>> review.nodes["review_0"].payload["omit_producer_reasoning"]
    True
    >>> review.nodes["aggregate_reviews"].payload["retain_disagreement"]
    True
    >>> from mechaharness.consequence import ActionConsequence, ConsequencePolicy
    >>> risk = ConsequencePolicy(actions=[
    ...     ActionConsequence(action="fs.read", consequence="low"),
    ...     ActionConsequence(
    ...         action="prod.deploy", consequence="critical", requires_approval=True,
    ...     ),
    ... ])
    >>> risk.requires_stronger_controls("fs.read")
    False
    >>> risk.requires_stronger_controls("prod.deploy")
    True

Discover context on demand; soft skills vs hard grants
------------------------------------------------------
In *Dynamic context discovery*, the Cursor developer blog suggests short
discoverable indices and just-in-time loading instead of static dump
(https://cursor.com/blog/dynamic-context-discovery).
In *Lessons from building Claude Code: How we use skills*, the Claude
developer blog suggests scarce, progressive skill content with measurable
trigger behavior
(https://claude.com/blog/lessons-from-building-claude-code-how-we-use-skills).
Soft instruction never replaces structural grants::

    >>> from mechaharness.context_provider import (
    ...     ContextProviderRegistry, StaticContextProvider,
    ... )
    >>> kg = StaticContextProvider(
    ...     "host.docs",
    ...     {"skill:verify-ui": "Never mark UI done without browser check..."},
    ...     summaries={"skill:verify-ui": "UI verification skill (short index)"},
    ... )
    >>> registry = ContextProviderRegistry([kg])
    >>> index = registry.get("host.docs").index(query="verify")
    >>> index[0].summary
    'UI verification skill (short index)'
    >>> chunks = kg.load([index[0].ref])
    >>> chunks[0].content.startswith("Never mark UI done")
    True
    >>> from mechaharness.instruction_component import InstructionCatalog
    >>> catalog = InstructionCatalog()
    >>> gotcha = catalog.append_gotcha(
    ...     "log hygiene",
    ...     "error logs must include request id; never log request bodies",
    ...     provenance={"source": "claude.com/blog/building-verification-loops"},
    ... )
    >>> gotcha.record_trigger(used=True, appropriate=True)
    >>> catalog.promote(gotcha.id).status
    'active'
    >>> # Soft gotcha exists alongside hard envelopes/grants — different layers.
    >>> CapabilityEnvelope(grants=["core:fs.read"]).allows_grant("core:fs.write")
    False

Lifecycle mods with ordered interception
----------------------------------------
In *Customize Claude Code with mods*, the Claude developer blog suggests
typed lifecycle hooks that can observe, rewrite, block, or replace default
behavior, with deterministic ordering and authority that cannot silently
widen
(https://claude.com/blog/claude-code-mods).
MechaHarness exposes the same shape as ordered lifecycle extensions::

    >>> from mechaharness.lifecycle_extension import (
    ...     BeforeTool, Block, ExtensionEffect, LifecycleExtension,
    ...     LifecycleExtensionContext, LifecycleExtensionRegistry,
    ...     ObserveBefore, Rewrite,
    ... )
    >>> class Audit(LifecycleExtension):
    ...     extension_id = "acme:audit"
    ...     boundary = BeforeTool
    ...     modes = frozenset({ObserveBefore})
    ...     def handle(self, context):
    ...         return ExtensionEffect(mode=ObserveBefore.key(),
    ...                                notes={"seen": context.tool_name})
    >>> class SandboxPath(LifecycleExtension):
    ...     extension_id = "acme:sandbox"
    ...     boundary = BeforeTool
    ...     modes = frozenset({Rewrite})
    ...     def handle(self, context):
    ...         path = context.arguments.get("path", "")
    ...         return ExtensionEffect(
    ...             mode=Rewrite.key(),
    ...             rewrite_arguments={"path": f"/sandbox/{path}"},
    ...         )
    >>> class DenyProd(LifecycleExtension):
    ...     extension_id = "acme:deny_prod"
    ...     boundary = BeforeTool
    ...     modes = frozenset({Block})
    ...     def handle(self, context):
    ...         if str(context.arguments.get("path", "")).startswith("/prod"):
    ...             return ExtensionEffect(
    ...                 mode=Block.key(), block=True,
    ...                 block_message="production path blocked",
    ...             )
    ...         return ExtensionEffect(mode=Block.key())
    >>> # DenyProd runs before rewrite so production paths are judged on the
    >>> # original arguments (early security extensions win on order).
    >>> reg = LifecycleExtensionRegistry([Audit(), DenyProd(), SandboxPath()])
    >>> ctx = LifecycleExtensionContext(
    ...     boundary=BeforeTool.key(), run_id="r1", agent_id="a1",
    ...     tool_name="Write", arguments={"path": "config.json"},
    ... )
    >>> effect = reg.dispatch(BeforeTool, ctx)
    >>> effect.rewrite_arguments["path"]
    '/sandbox/config.json'
    >>> effect.block
    False
    >>> blocked = reg.dispatch(
    ...     BeforeTool,
    ...     ctx.model_copy(update={"arguments": {"path": "/prod/secrets"}}),
    ... )
    >>> blocked.block, blocked.block_message
    (True, 'production path blocked')
"""

from mechaharness.budget import Budget, BudgetLevel, BudgetPolicy
from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.config import Settings
from mechaharness.core.access import AccessControl, CostAccountant
from mechaharness.core.completer import Completer
from mechaharness.core.contract import RunRequest, RunResponse
from mechaharness.core.environment import InferenceEnvironment
from mechaharness.core.events import Event, EventLog, EventType
from mechaharness.core.types import (
    ChatMessage,
    CompletionRequest,
    CompletionResponse,
    Role,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from mechaharness.di import MechaHarnessConfig, SettingsConfig, list_inference_backends
from mechaharness.factory import run
from mechaharness.graph_executor import GraphExecutor
from mechaharness.harness.base import AbstractHarness, HarnessConfig, HarnessResult
from mechaharness.inference.base import InferenceStrategy
from mechaharness.linkage_resolver import LinkageResolver
from mechaharness.stop_contract import StopContract
from mechaharness.tools.base import Tool, ToolRegistry

__all__ = [
    "AbstractHarness",
    "AccessControl",
    "Budget",
    "BudgetLevel",
    "BudgetPolicy",
    "CapabilityEnvelope",
    "ChatMessage",
    "Completer",
    "CompletionRequest",
    "CompletionResponse",
    "CostAccountant",
    "Event",
    "EventLog",
    "EventType",
    "GraphExecutor",
    "HarnessConfig",
    "HarnessResult",
    "InferenceEnvironment",
    "InferenceStrategy",
    "LinkageResolver",
    "MechaHarnessConfig",
    "Role",
    "RunRequest",
    "RunResponse",
    "Settings",
    "SettingsConfig",
    "StopContract",
    "Tool",
    "ToolCall",
    "ToolDefinition",
    "ToolRegistry",
    "ToolResult",
    "list_inference_backends",
    "run",
]

__version__ = "0.3.0"
