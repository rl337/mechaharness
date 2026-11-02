#!/usr/bin/env python3
"""Record a gastronomic comparison trial from a suite run directory.

Writes under ``.mechaharness/comparison_trials/<trial_id>/`` (gitignored via
``.mechaharness/``). Does not invent live results: arm B stays ``not_run``
until gastronomic can drive Completer coding comparable to ``guided_coding``.

Example::

    python scripts/record_gastronomic_comparison_trial.py \\
      --suite-run .mechaharness/suite_runs/calc_cli-<id> \\
      --trial-id calc-a-1 --arm A --recipe guided_coding \\
      --model-id "$MECHA_MODEL"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from mechaharness.gastronomic_comparison import (  # noqa: E402
    ARM_B_LIVE_BLOCKER,
    live_comparison_status,
    trial_from_suite_run,
    validate_gastronomic_trial,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite-run", type=Path, required=True)
    parser.add_argument("--trial-id", required=True)
    parser.add_argument("--arm", required=True, choices=["A", "B", "C", "D"])
    parser.add_argument(
        "--recipe",
        required=True,
        choices=["guided_coding", "gastronomic_guided_development"],
    )
    parser.add_argument("--model-id", default=os.environ.get("MECHA_MODEL"))
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / ".mechaharness" / "comparison_trials",
    )
    parser.add_argument("--stages-total", type=int, default=6)
    parser.add_argument(
        "--notes",
        default=None,
        help="Optional host note stored on the trial record",
    )
    args = parser.parse_args(argv)

    model = {"id": args.model_id} if args.model_id else None
    trial = trial_from_suite_run(
        args.suite_run,
        trial_id=args.trial_id,
        arm=args.arm,
        recipe_id=args.recipe,
        model=model,
        stages_total=args.stages_total,
        notes=args.notes,
    )
    check = validate_gastronomic_trial(trial)
    if not check["ok"]:
        print("invalid trial:", check["errors"], file=sys.stderr)
        return 2

    dest = args.out_dir / args.trial_id
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "trial.json").write_text(
        json.dumps(trial, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    endpoint = bool(os.environ.get("MECHA_BASE_URL"))
    arm_a = trial if args.arm == "A" else None
    arm_b = trial if args.arm == "B" else None
    status = live_comparison_status(
        arm_a=arm_a,
        arm_b=arm_b,
        endpoint_configured=endpoint,
        arm_b_blocker=ARM_B_LIVE_BLOCKER,
    )
    (dest / "live_status.json").write_text(
        json.dumps(status, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"trial_path": str(dest / "trial.json"), "status": status}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
