"""Interim domain harnesses: former kind strings become ``request.op`` values.

All former domain op-dispatch families have migrated to ``kind: cli``. This
module remains as an empty merge point for hosts/tests that still import
``DOMAIN_HARNESSES`` / ``KIND_TO_HARNESS_OP``.
"""

from __future__ import annotations

DOMAIN_HARNESSES: tuple[object, ...] = ()

# Former story kind → (harness family, op) for fixture migration.
KIND_TO_HARNESS_OP: dict[str, tuple[str, str]] = {}
