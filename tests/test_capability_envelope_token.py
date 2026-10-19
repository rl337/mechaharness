"""CapabilityEnvelope execution-token fields and attenuation (MH-DOTS-01)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from mechaharness.capability_envelope import CapabilityEnvelope

_PARENT = CapabilityEnvelope(
    grants=["core:graph.execute", "core:fs.read"],
    tool_names=["Read"],
    principal="user:fangore",
    expires_at="2026-10-18T12:00:00Z",
    trust_origin="host:console",
    authorization_epoch=3,
)

_NARROW_OK = [
    ("inherit_all", {}, {"principal": "user:fangore", "authorization_epoch": 3}),
    ("same_principal", {"principal": "user:fangore"}, {"principal": "user:fangore"}),
    ("lower_epoch", {"authorization_epoch": 2}, {"authorization_epoch": 2}),
    (
        "earlier_expiry",
        {"expires_at": "2026-10-18T11:00:00Z"},
        {"expires_at": "2026-10-18T11:00:00Z"},
    ),
    (
        "same_expiry_other_offset",
        {"expires_at": "2026-10-18T05:00:00-07:00"},
        {"expires_at": "2026-10-18T05:00:00-07:00"},
    ),
    ("same_origin", {"trust_origin": "host:console"}, {"trust_origin": "host:console"}),
]

_NARROW_REFUSED = [
    ("higher_epoch", {"authorization_epoch": 4}, "widens authorization_epoch"),
    ("other_principal", {"principal": "user:other"}, "changes principal"),
    ("other_origin", {"trust_origin": "host:webhook"}, "changes trust_origin"),
    ("later_expiry", {"expires_at": "2026-10-18T13:00:00Z"}, "widens expires_at"),
    ("opaque_expiry", {"expires_at": "never"}, "widens expires_at"),
]


@pytest.mark.parametrize(
    ("case_id", "kwargs", "expected"), _NARROW_OK, ids=[c[0] for c in _NARROW_OK]
)
def test_narrow_allows_attenuation(case_id: str, kwargs: dict, expected: dict) -> None:
    del case_id
    child = _PARENT.narrow(**kwargs)
    for field, value in expected.items():
        assert getattr(child, field) == value


@pytest.mark.parametrize(
    ("case_id", "kwargs", "message"), _NARROW_REFUSED, ids=[c[0] for c in _NARROW_REFUSED]
)
def test_narrow_refuses_widening(case_id: str, kwargs: dict, message: str) -> None:
    del case_id
    with pytest.raises(ValueError, match=message):
        _PARENT.narrow(**kwargs)


def test_unset_parent_token_fields_allow_child_to_set_them() -> None:
    parent = CapabilityEnvelope(grants=["core:graph.execute"])
    child = parent.narrow(principal="user:a", trust_origin="x", expires_at="2026-01-01")
    assert (child.principal, child.trust_origin, child.expires_at) == ("user:a", "x", "2026-01-01")


def test_opaque_expiry_must_match_exactly() -> None:
    parent = CapabilityEnvelope(expires_at="tok:abc")
    assert parent.narrow(expires_at="tok:abc").expires_at == "tok:abc"
    with pytest.raises(ValueError, match="widens expires_at"):
        parent.narrow(expires_at="tok:def")


def test_defaults_are_backward_compatible() -> None:
    env = CapabilityEnvelope()
    assert (env.principal, env.expires_at, env.trust_origin, env.authorization_epoch) == (
        None,
        None,
        None,
        0,
    )
    assert env.narrow().authorization_epoch == 0


@pytest.mark.parametrize(
    ("hour", "expired"),
    [(11, False), (12, True), (13, True)],
)
def test_is_expired(hour: int, expired: bool) -> None:
    now = datetime(2026, 10, 18, hour, tzinfo=timezone.utc)
    assert _PARENT.is_expired(now=now) is expired


def test_opaque_expiry_is_not_reported_expired() -> None:
    assert CapabilityEnvelope(expires_at="tok:abc").is_expired() is False
