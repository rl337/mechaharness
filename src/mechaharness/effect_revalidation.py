"""Pre-effect revalidation of authority (MH-DOTS-02).

Authority captured at graph start, approval, or checkpoint time can be stale
when a consequential action actually runs. :func:`revalidate_before_effect`
rechecks the envelope expiry, the live authorization epoch, and the grants
immediately before an ``execute``-phase effect::

    >>> from mechaharness.capability_envelope import CapabilityEnvelope
    >>> from mechaharness.effect_revalidation import revalidate_before_effect
    >>> env = CapabilityEnvelope(
    ...     grants=["core:graph.execute"], authorization_epoch=2,
    ... )
    >>> revalidate_before_effect(envelope=env, live_authorization_epoch=2).ok
    True
    >>> revalidate_before_effect(envelope=env, live_authorization_epoch=3).reason
    'authorization_epoch_advanced:2!=3'
    >>> revalidate_before_effect(
    ...     envelope=env, required_grants=["core:net.http"],
    ... ).reason
    'envelope_grant_missing:core:net.http'
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime

from pydantic import BaseModel

from mechaharness.capability_envelope import CapabilityEnvelope


class EffectRevalidation(BaseModel):
    """Outcome of a pre-effect authority recheck."""

    ok: bool
    reason: str | None = None


def revalidate_before_effect(
    *,
    envelope: CapabilityEnvelope | None = None,
    required_grants: Sequence[object] = (),
    live_authorization_epoch: int | None = None,
    access_allows: Callable[[Sequence[object]], bool] | None = None,
    now: datetime | None = None,
) -> EffectRevalidation:
    """Fail closed if authority lapsed between planning and the effect."""
    if envelope is not None:
        issue = envelope.authority_issue(
            required_grants=required_grants,
            live_authorization_epoch=live_authorization_epoch,
            now=now,
        )
        if issue is not None:
            return EffectRevalidation(ok=False, reason=issue)
    if access_allows is not None and not access_allows(required_grants):
        return EffectRevalidation(ok=False, reason="access_revoked")
    return EffectRevalidation(ok=True)
