"""Story Config: host CLI verbs plus acceptance probe catalog."""

from __future__ import annotations

from mechaharness.cli_verb import CliVerb
from mechaharness.di import MechaHarnessConfig
from mechaharness.harness.base import AbstractHarness
from mechaharness.harness.pass_through import PassThroughHarness
from mechaharness.inference.base import InferenceStrategy
from mechaharness.inference.mock import MockInferenceStrategy
from tests.stories.cli_probes.catalog import story_cli_verb_classes


class StoryCliConfig(MechaHarnessConfig):
    """Merge product CLI verbs with story-only probes via map multibind."""

    def get_inference_class(self) -> type[InferenceStrategy]:
        return MockInferenceStrategy

    def get_harness_class(self) -> type[AbstractHarness]:
        return PassThroughHarness

    def cli_verb_classes(self) -> dict[str, type[CliVerb]]:
        verbs = dict(super().cli_verb_classes())
        verbs.update(story_cli_verb_classes())
        return verbs
