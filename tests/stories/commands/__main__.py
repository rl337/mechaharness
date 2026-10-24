"""``python -m tests.stories.commands <subcommand>``."""

from __future__ import annotations

from pyiv.command import CommandRunner


def main(argv: list[str] | None = None) -> int:
    runner = CommandRunner()
    return runner.run(
        "tests.stories.commands",
        prog="python -m tests.stories.commands",
        description="MechaHarness user-story suite fixture tools (YAML SSOT).",
        args=argv,
    )


if __name__ == "__main__":
    raise SystemExit(main())
