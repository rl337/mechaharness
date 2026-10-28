"""Pytest configuration."""

# Coding-suite source snapshots under fixtures are workspace seeds for guided
# coding arcs — not root-collected tests (they import bare modules like widget).
# Patterns are relative to this conftest's directory (``tests/``).
collect_ignore_glob = [
    "fixtures/models/**/suites/*/sources/**",
]
