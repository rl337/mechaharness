"""InferenceEnvironment refusal hooks."""

from __future__ import annotations

import pytest

from mechaharness.core.access import CapabilityProfile, MediaImage
from mechaharness.core.environment import (
    InferenceEnvironment,
    InferenceEnvironmentError,
    NoOpInferenceEnvironment,
)


class ReasonOnlyEnv(InferenceEnvironment):
    def active_profile(self) -> str | None:
        return "reason-fast"

    def active_capabilities(self) -> CapabilityProfile:
        return CapabilityProfile()

    def active_grants(self) -> list[str]:
        return []


def test_noop_environment_never_raises() -> None:
    NoOpInferenceEnvironment().assert_compatible(
        required_grants=[MediaImage],
        require_media=True,
    )


def test_reason_profile_rejects_media() -> None:
    env = ReasonOnlyEnv()
    with pytest.raises(InferenceEnvironmentError, match="media"):
        env.assert_compatible(require_media=True)
    with pytest.raises(InferenceEnvironmentError, match="lacks grants"):
        env.assert_compatible(required_grants=[MediaImage])
