"""Test harness Config: production CLI verbs + clocks + ``probe`` verb delta."""

from __future__ import annotations

from pyiv.injector import Injector
from pyiv.time import DateTimeService

from mechaharness.budget import BudgetPolicy
from mechaharness.capability_envelope import CapabilityEnvelope
from mechaharness.cli_instrumentor import CliInstrumentor
from mechaharness.cli_recipe_adapter import CliRecipeAdapter
from mechaharness.cli_verb import CliProbe, CliVerb
from mechaharness.core.access import AccessControl, GrantPolicyLike
from mechaharness.core.completer import Completer
from mechaharness.di import MechaHarnessConfig, _expose_ctor_type_hints
from mechaharness.harness.base import AbstractHarness
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.judge import JudgeProvider
from mechaharness.inference.mock import MockInferenceStrategy
from mechaharness.job_lane_broker import JobLaneBroker
from mechaharness.rag import RagRetriever
from tests.stories.cli_probes.catalog import story_cli_probe_classes
from tests.stories.cli_probes.clock_verbs import clock_cli_verb_classes
from tests.stories.cli_probes.probe_verb import ProbeVerb


def _probe_as_verb(probe_cls: type[CliProbe]) -> type[CliVerb]:
    """Expose a story probe as a first-class verb for ``user_story`` walks."""

    class _V(CliVerb):
        async def run(self, params, runtime):  # type: ignore[no-untyped-def]
            return await probe_cls().run(params, runtime)

    _V.name = probe_cls.name
    _V.params_model = probe_cls.params_model
    _V.__name__ = f"{probe_cls.name}_verb"
    _V.__qualname__ = _V.__name__
    return _V


class _CliMaps:
    def __init__(
        self,
        verbs: dict[str, CliVerb],
        adapters: dict[str, CliRecipeAdapter],
    ) -> None:
        self.verbs = verbs
        self.adapters = adapters


class TestHarnessCliConfig(MechaHarnessConfig):
    """Merge production CLI with test clocks/probes; bind ``CliInstrumentor``."""

    def __init__(
        self,
        completer: Completer,
        datetime_service: DateTimeService,
        *,
        model: str = "cli-default",
        agent_id: str = "cli",
        judge_provider: JudgeProvider | None = None,
        rag_retriever: RagRetriever | None = None,
        lifecycle_extensions: dict[str, object] | None = None,
        harness_family: str = "pass_through",
        grants: list[object] | None = None,
        access_policy: GrantPolicyLike | None = None,
        capability_envelope: CapabilityEnvelope | None = None,
        budget_policy: BudgetPolicy | None = None,
        job_lane_broker: JobLaneBroker | None = None,
    ) -> None:
        self._completer = completer
        self._datetime_service = datetime_service
        self._model = model
        self._agent_id = agent_id
        self._judge_provider = judge_provider
        self._rag_retriever = rag_retriever
        self._lifecycle_extensions = dict(lifecycle_extensions or {})
        self._harness_family = harness_family
        self._grants = grants
        self._access_policy = access_policy
        self._capability_envelope = capability_envelope
        self._budget_policy = budget_policy
        self._job_lane_broker = job_lane_broker
        super().__init__()

    def get_rag_retriever(self) -> type[RagRetriever] | RagRetriever:
        if self._rag_retriever is not None:
            return self._rag_retriever
        return super().get_rag_retriever()

    def get_grants(self) -> list[object]:
        if self._grants is not None:
            return list(self._grants)
        if self._access_policy is not None:
            return list(self._access_policy.grants)
        return super().get_grants()

    def get_access_policy(self) -> GrantPolicyLike:
        if self._access_policy is not None:
            return self._access_policy
        return super().get_access_policy()

    def get_capability_envelope(self) -> CapabilityEnvelope:
        if self._capability_envelope is not None:
            return self._capability_envelope
        return super().get_capability_envelope()

    def get_job_lane_broker(self) -> JobLaneBroker | type[JobLaneBroker] | None:
        if self._job_lane_broker is not None:
            return self._job_lane_broker
        return super().get_job_lane_broker()

    def get_inference_class(self) -> type[InferenceStrategy]:
        if isinstance(self._completer, InferenceStrategy):
            return type(self._completer)
        return MockInferenceStrategy

    def get_harness_class(self) -> type[AbstractHarness]:
        name = self._harness_family.lower()
        classes = self.harness_classes()
        try:
            return classes[name]
        except KeyError as exc:
            known = ", ".join(sorted(classes)) or "(none)"
            raise KeyError(
                f"Unknown harness family {name!r}. Known: {known}"
            ) from exc

    def cli_verb_classes(self) -> dict[str, type[CliVerb]]:
        verbs = dict(super().cli_verb_classes())
        verbs.update(clock_cli_verb_classes())
        verbs[ProbeVerb.name] = ProbeVerb
        # Promote remaining probes so migrated user_story YAML can call them
        # without the ``probe:`` wrapper (G2/G5/G7). Prefer src product verbs
        # when both exist.
        for name, probe_cls in self.cli_probe_classes().items():
            if name not in verbs:
                verbs[name] = _probe_as_verb(probe_cls)
        return verbs

    def cli_probe_classes(self) -> dict[str, type[CliProbe]]:
        probes = dict(super().cli_probe_classes())
        probes.update(story_cli_probe_classes())
        return probes

    def configure(self) -> None:
        super().configure()
        self.register_instance(Completer, self._completer)
        self.register_instance(DateTimeService, self._datetime_service)
        if isinstance(self._completer, InferenceStrategy):
            self.register_instance(InferenceStrategy, self._completer)
        if self._judge_provider is not None:
            self.register_instance(JudgeProvider, self._judge_provider)
        if self._rag_retriever is not None:
            self.register_instance(RagRetriever, self._rag_retriever)

        model = self._model
        agent_id = self._agent_id
        judge = self._judge_provider
        rag = self._rag_retriever
        life = self._lifecycle_extensions
        budget = self._budget_policy
        grants = self.get_grants() if (
            self._grants is not None or self._access_policy is not None
        ) else None
        access_policy = self._access_policy
        _expose_ctor_type_hints(_CliMaps)

        def make_cli(injector: Injector) -> CliInstrumentor:
            maps = injector.inject(_CliMaps)
            return CliInstrumentor(
                completer=injector.inject(Completer),
                verbs=maps.verbs,
                recipe_adapters=maps.adapters,
                datetime_service=injector.inject(DateTimeService),
                model=model,
                agent_id=agent_id,
                judge_provider=judge,
                rag_retriever=rag,
                lifecycle_extensions=life,
                access_control=injector.inject(AccessControl),
                capability_envelope=injector.inject(CapabilityEnvelope),
                budget_policy=budget,
                grants=grants,
                access_policy=access_policy,
                job_lane_broker=injector.inject(JobLaneBroker),
            )

        self.register(CliInstrumentor, make_cli)


# Back-compat alias during migration.
StoryCliConfig = TestHarnessCliConfig

__all__ = ["StoryCliConfig", "TestHarnessCliConfig"]
