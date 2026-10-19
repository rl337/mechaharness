"""Story harness: YAML tests drive the product durable generator instrumentor."""

from __future__ import annotations

from tests.stories.backend import StoryBackend
from tests.stories.catalog import StoryCase
from tests.stories.scenarios.durable_generator_scenario import load_durable_scenario


class DurableGeneratorHarness:
    """Intention-blind: load scenario.yaml, run instrumentor, hard-assert expects."""

    name = "durable_generator"

    def known_ops(self) -> frozenset[str]:
        return frozenset()

    async def run(self, case: StoryCase, backend: StoryBackend) -> None:
        del backend
        path = case.path("scenario.yaml")
        if not path.is_file():
            raise AssertionError(f"{case.label}: missing scenario.yaml")
        scenario = load_durable_scenario(path)
        observations = scenario.run()
        scenario.assert_expects(observations, label=case.label)
