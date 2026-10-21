"""Test harness Config: production CLI verbs + clocks + ``probe`` verb delta."""

from __future__ import annotations

from pyiv.injector import Injector
from pyiv.time import DateTimeService

from mechaharness.cli_instrumentor import CliInstrumentor
from mechaharness.cli_recipe_adapter import CliRecipeAdapter
from mechaharness.cli_verb import CliProbe, CliVerb
from mechaharness.core.completer import Completer
from mechaharness.di import MechaHarnessConfig, _expose_ctor_type_hints
from mechaharness.harness.base import AbstractHarness
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.judge import JudgeProvider
from mechaharness.inference.mock import MockInferenceStrategy
from mechaharness.rag import RagRetriever
from tests.stories.cli_probes.catalog import story_cli_probe_classes
from tests.stories.cli_probes.clock_verbs import clock_cli_verb_classes
from tests.stories.cli_probes.probe_verb import ProbeVerb


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
    ) -> None:
        self._completer = completer
        self._datetime_service = datetime_service
        self._model = model
        self._agent_id = agent_id
        self._judge_provider = judge_provider
        self._rag_retriever = rag_retriever
        self._lifecycle_extensions = dict(lifecycle_extensions or {})
        self._harness_family = harness_family
        super().__init__()

    def get_rag_retriever(self) -> type[RagRetriever] | RagRetriever:
        if self._rag_retriever is not None:
            return self._rag_retriever
        return super().get_rag_retriever()

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
            )

        self.register(CliInstrumentor, make_cli)


# Back-compat alias during migration.
StoryCliConfig = TestHarnessCliConfig

__all__ = ["StoryCliConfig", "TestHarnessCliConfig"]
