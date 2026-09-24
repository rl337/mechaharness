"""Optional host probe for the active inference environment.

Hosts (for example junespark) implement this to refuse runs that need
capabilities the loaded profile does not provide. The library default is a
no-op so CLI/mock paths stay unchanged.

Lanes are open ``str`` identity (``reason``, ``judge``, ``media``, or a host
namespace). Unknown lanes round-trip; hosts supply load hints.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence

from mechaharness.core.access import CapabilityProfile, grant_key
from mechaharness.core.exceptions import MechaHarnessError

# Well-known lane names (conveniences — hosts may add more).
LANE_REASON = "reason"
LANE_JUDGE = "judge"
LANE_MEDIA = "media"
# Deprecated alias — same string as LANE_JUDGE after rename.
LANE_DECIDE = LANE_JUDGE

DEFAULT_LANE_LOAD_HINTS: Mapping[str, str] = {
    LANE_REASON: "infer load reason-fast",
    # Host profile filenames may still be decide-* until operators rename them.
    LANE_JUDGE: "infer load decide-fast",
    LANE_MEDIA: "infer load media",
}


class InferenceEnvironmentError(MechaHarnessError):
    """Requested work does not match the active inference environment."""


class InferenceEnvironment(ABC):
    """Describe what the current backend / host profile can do."""

    @abstractmethod
    def active_profile(self) -> str | None:
        """Host profile name, or None when unknown."""

    @abstractmethod
    def active_capabilities(self) -> CapabilityProfile:
        """Capability set of the loaded environment."""

    def active_lane(self) -> str | None:
        """Capability lane derived from the active profile, or None if unknown.

        Well-known values: ``reason``, ``judge``, ``media``. Hosts may return
        other namespaced lanes.
        """
        return None

    def active_grants(self) -> list[str]:
        """Grants the environment is willing to honor (default: none)."""
        return []

    def lane_load_hint(self, lane: str) -> str:
        """Operator hint naming how to load a profile for ``lane``."""
        return DEFAULT_LANE_LOAD_HINTS.get(lane, f"infer load <profile-for-{lane}>")

    def assert_compatible(
        self,
        *,
        required_grants: Sequence[object] | None = None,
        require_media: bool = False,
        require_lane: str | None = None,
    ) -> None:
        """Raise if the active environment cannot satisfy the request."""
        held = set(self.active_grants())
        needed = {grant_key(item) for item in (required_grants or [])}
        missing = sorted(needed - held)
        profile = self.active_profile() or "unknown"
        lane = self.active_lane()
        if require_lane is not None and lane != require_lane:
            hint = self.lane_load_hint(require_lane)
            raise InferenceEnvironmentError(
                f"active profile {profile!r} lane={lane!r} cannot satisfy "
                f"require_lane={require_lane!r}; try `{hint}`"
            )
        if missing:
            raise InferenceEnvironmentError(
                f"active profile {profile!r} lacks grants: {', '.join(missing)}"
            )
        if require_media and not any(key.startswith("core:media.") for key in held):
            hint = self.lane_load_hint(LANE_MEDIA)
            raise InferenceEnvironmentError(
                f"active profile {profile!r} does not provide media capabilities; "
                f"try `{hint}`"
            )


class NoOpInferenceEnvironment(InferenceEnvironment):
    """Always compatible; used when no host probe is configured."""

    def active_profile(self) -> str | None:
        return None

    def active_capabilities(self) -> CapabilityProfile:
        return CapabilityProfile()

    def active_lane(self) -> str | None:
        return None

    def assert_compatible(
        self,
        *,
        required_grants: Sequence[object] | None = None,
        require_media: bool = False,
        require_lane: str | None = None,
    ) -> None:
        del required_grants, require_media, require_lane
