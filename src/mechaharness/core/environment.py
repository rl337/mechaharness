"""Optional host probe for the active inference environment.

Hosts (for example junespark) implement this to refuse runs that need
capabilities the loaded profile does not provide. The library default is a
no-op so CLI/mock paths stay unchanged.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from mechaharness.core.access import CapabilityProfile, grant_key
from mechaharness.core.exceptions import MechaHarnessError


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

    def active_grants(self) -> list[str]:
        """Grants the environment is willing to honor (default: none)."""
        return []

    def assert_compatible(
        self,
        *,
        required_grants: Sequence[object] | None = None,
        require_media: bool = False,
    ) -> None:
        """Raise if the active environment cannot satisfy the request."""
        held = set(self.active_grants())
        needed = {grant_key(item) for item in (required_grants or [])}
        missing = sorted(needed - held)
        profile = self.active_profile() or "unknown"
        if missing:
            raise InferenceEnvironmentError(
                f"active profile {profile!r} lacks grants: {', '.join(missing)}"
            )
        if require_media and not any(key.startswith("core:media.") for key in held):
            raise InferenceEnvironmentError(
                f"active profile {profile!r} does not provide media capabilities"
            )


class NoOpInferenceEnvironment(InferenceEnvironment):
    """Always compatible; used when no host probe is configured."""

    def active_profile(self) -> str | None:
        return None

    def active_capabilities(self) -> CapabilityProfile:
        return CapabilityProfile()

    def assert_compatible(
        self,
        *,
        required_grants: Sequence[object] | None = None,
        require_media: bool = False,
    ) -> None:
        del required_grants, require_media
