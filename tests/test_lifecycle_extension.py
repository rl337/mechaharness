"""Data-driven coverage for lifecycle interception (req 20)."""

from __future__ import annotations

import pytest

from tests.support.lifecycle_extension_cases import assert_expect, iter_cases, run_case

_CASES = list(iter_cases())
_IDS = [c["id"] for c in _CASES]


def test_lifecycle_extension_fixture_matrix_nonempty() -> None:
    assert len(_CASES) >= 4
    assert len(set(_IDS)) == len(_IDS)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _CASES, ids=_IDS)
async def test_lifecycle_extension_case(case: dict) -> None:
    actual = await run_case(case)
    assert_expect(actual, case["expect"])
