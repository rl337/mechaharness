"""InferenceEnvironment refusal hooks."""

from __future__ import annotations

import pytest

from mechaharness.core.access import CapabilityProfile, MediaImage
from mechaharness.core.environment import (
    LANE_DECIDE,
    LANE_MEDIA,
    LANE_REASON,
    InferenceEnvironment,
    InferenceEnvironmentError,
    NoOpInferenceEnvironment,
)


class ReasonOnlyEnv(InferenceEnvironment):
    def active_profile(self) -> str | None:
        return "reason-fast"

    def active_capabilities(self) -> CapabilityProfile:
        return CapabilityProfile()

    def active_lane(self) -> str | None:
        return LANE_REASON

    def active_grants(self) -> list[str]:
        return []


class DecideEnv(InferenceEnvironment):
    def active_profile(self) -> str | None:
        return "decide-fast"

    def active_capabilities(self) -> CapabilityProfile:
        return CapabilityProfile()

    def active_lane(self) -> str | None:
        return LANE_DECIDE

    def active_grants(self) -> list[str]:
        return []


def test_noop_environment_never_raises() -> None:
    NoOpInferenceEnvironment().assert_compatible(
        required_grants=[MediaImage],
        require_media=True,
        require_lane=LANE_DECIDE,
    )


def test_reason_profile_rejects_media() -> None:
    env = ReasonOnlyEnv()
    with pytest.raises(InferenceEnvironmentError, match="media"):
        env.assert_compatible(require_media=True)
    with pytest.raises(InferenceEnvironmentError, match="lacks grants"):
        env.assert_compatible(required_grants=[MediaImage])


def test_reason_profile_rejects_decide_lane() -> None:
    env = ReasonOnlyEnv()
    with pytest.raises(InferenceEnvironmentError, match="decide-fast"):
        env.assert_compatible(require_lane=LANE_DECIDE)


def test_decide_lane_accepts_decide() -> None:
    DecideEnv().assert_compatible(require_lane=LANE_DECIDE)


def test_require_lane_media_hint() -> None:
    env = ReasonOnlyEnv()
    with pytest.raises(InferenceEnvironmentError, match="infer load media"):
        env.assert_compatible(require_lane=LANE_MEDIA)
