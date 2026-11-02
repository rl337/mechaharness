"""Gastronomic vs guided_coding comparison trial records (post-M6).

Hosts record comparable trial arms without declaring a winner from a single
stochastic run. DevelopmentOutcome is host evidence; model text is not.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

TRIAL_VERSION = "1"
LIVE_STATUS_VERSION = "1"

# Arm B needs Completer-driven edits inside gastronomic execute; calc_cli stages
# still bind guided_coding + project_coding. Until that bridge lands, hosts must
# mark B as not_run rather than fabricating a gastronomic coding trial.
ARM_B_LIVE_BLOCKER = (
    "gastronomic_guided_development execute applies host file_revisions; "
    "calc_cli live coding still requires guided_coding + project_coding"
)

ARMS: frozenset[str] = frozenset({"A", "B", "C", "D"})
RECIPE_IDS: frozenset[str] = frozenset(
    {
        "guided_coding",
        "gastronomic_guided_development",
    }
)


def assemble_gastronomic_trial(
    *,
    trial_id: str,
    arm: str,
    recipe_id: str,
    development_outcome: Mapping[str, Any] | None = None,
    metrics: Mapping[str, Any] | None = None,
    model: Mapping[str, Any] | None = None,
    budget: Mapping[str, Any] | None = None,
    suite_id: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Build one comparable trial record from host outcome + metrics."""
    outcome = development_outcome if isinstance(development_outcome, Mapping) else {}
    mets = dict(metrics) if isinstance(metrics, Mapping) else {}
    model_info = dict(model) if isinstance(model, Mapping) else {}
    budget_info = dict(budget) if isinstance(budget, Mapping) else {}

    outcome_label = str(outcome.get("outcome") or mets.get("outcome") or "")
    success = outcome_label == "completed"
    if outcome_label == "" and "success" in mets:
        success = bool(mets.get("success"))

    def _num(key: str, default: float | int | None = None) -> float | int | None:
        if key not in mets:
            return default
        raw = mets.get(key)
        if raw is None:
            return default
        try:
            if isinstance(raw, bool):
                return int(raw)
            if isinstance(raw, int):
                return raw
            return float(raw)
        except (TypeError, ValueError):
            return default

    return {
        "version": TRIAL_VERSION,
        "trial_id": str(trial_id),
        "arm": str(arm),
        "recipe_id": str(recipe_id),
        "suite_id": suite_id,
        "success": success,
        "outcome": outcome_label or ("completed" if success else "unknown"),
        "development_outcome": dict(outcome) if outcome else None,
        "metrics": {
            "stages_passed": _num("stages_passed"),
            "stages_total": _num("stages_total"),
            "prior_regressions": _num("prior_regressions", 0),
            "first_failure_class": mets.get("first_failure_class"),
            "model_calls": _num("model_calls"),
            "prompt_tokens": _num("prompt_tokens"),
            "completion_tokens": _num("completion_tokens"),
            "tool_calls": _num("tool_calls"),
            "wall_ms": _num("wall_ms"),
            "repair_loops": _num("repair_loops", 0),
            "guidance_yields": _num("guidance_yields", 0),
            "repeat_failure_loops": _num("repeat_failure_loops", 0),
            "verified_edits": _num("verified_edits"),
        },
        "model": model_info or None,
        "budget": budget_info or None,
        "notes": notes,
        "provenance": {
            "outcome_status": outcome.get("status"),
            "outcome_reason": outcome.get("reason"),
            "gates_passed": (
                (outcome.get("provenance") or {}).get("gates_passed")
                if isinstance(outcome.get("provenance"), Mapping)
                else None
            ),
        },
    }


def validate_gastronomic_trial(report: Mapping[str, Any]) -> dict[str, Any]:
    """Schema report for a gastronomic trial record (non-raising)."""
    errors: list[dict[str, str]] = []
    if str(report.get("version") or "") != TRIAL_VERSION:
        errors.append({"path": "version", "message": f"expected {TRIAL_VERSION}"})
    if not str(report.get("trial_id") or "").strip():
        errors.append({"path": "trial_id", "message": "nonempty required"})
    arm = str(report.get("arm") or "")
    if arm not in ARMS:
        errors.append({"path": "arm", "message": "A|B|C|D required"})
    recipe = str(report.get("recipe_id") or "")
    if recipe not in RECIPE_IDS:
        errors.append(
            {
                "path": "recipe_id",
                "message": "guided_coding|gastronomic_guided_development required",
            }
        )
    if "success" not in report or not isinstance(report.get("success"), bool):
        errors.append({"path": "success", "message": "bool required"})
    if not str(report.get("outcome") or "").strip():
        errors.append({"path": "outcome", "message": "nonempty required"})
    if not isinstance(report.get("metrics"), Mapping):
        errors.append({"path": "metrics", "message": "object required"})
    # Fairness: arm A/C must be guided_coding; B/D gastronomic.
    if arm in {"A", "C"} and recipe != "guided_coding":
        errors.append(
            {
                "path": "recipe_id",
                "message": "arms A/C require guided_coding",
            }
        )
    if arm in {"B", "D"} and recipe != "gastronomic_guided_development":
        errors.append(
            {
                "path": "recipe_id",
                "message": "arms B/D require gastronomic_guided_development",
            }
        )
    return {"ok": not errors, "errors": errors}


def metrics_from_suite_timing(
    events: Sequence[Mapping[str, Any]],
    *,
    stages_total: int | None = None,
) -> dict[str, Any]:
    """Derive comparison metrics from suite ``TIMING.jsonl`` event dicts.

    Counts ``suite_stage`` rows for progress, sums wall time, and tallies
    coding-burst repair/verify hints when present. Missing fields stay absent
    so hosts do not invent token counts.
    """
    stage_rows = [e for e in events if e.get("kind") == "suite_stage"]
    burst_rows = [e for e in events if e.get("kind") == "coding_burst"]
    work_rows = [e for e in events if e.get("kind") == "coding_work_item"]
    stages_passed = sum(1 for e in stage_rows if e.get("status") == "ok")
    failed = next((e for e in stage_rows if e.get("status") != "ok"), None)
    wall_s = 0.0
    for e in stage_rows:
        raw = e.get("elapsed_s")
        if raw is None:
            continue
        try:
            wall_s += float(raw)
        except (TypeError, ValueError):
            continue
    repair_loops = 0
    verify_runs = 0
    for e in burst_rows:
        raw_repair = e.get("max_repair_rounds")
        # Prefer explicit repair count when hosts log it; else leave 0.
        if "repair_rounds" in e:
            try:
                repair_loops += int(e.get("repair_rounds") or 0)
            except (TypeError, ValueError):
                pass
        elif raw_repair is not None:
            # Budget ceiling is not loops used; ignore unless repair_rounds set.
            pass
        if "verify_runs" in e:
            try:
                verify_runs += int(e.get("verify_runs") or 0)
            except (TypeError, ValueError):
                pass
    model_calls = None
    for e in burst_rows + work_rows:
        if "model_calls" in e:
            try:
                model_calls = (model_calls or 0) + int(e.get("model_calls") or 0)
            except (TypeError, ValueError):
                continue
    total = stages_total
    if total is None:
        total = len(stage_rows) if stage_rows else None
    success = failed is None and bool(stage_rows) and (
        total is None or stages_passed >= int(total)
    )
    first_failure_class = None
    if isinstance(failed, Mapping):
        first_failure_class = failed.get("failure_class") or failed.get("status")
    out: dict[str, Any] = {
        "stages_passed": stages_passed,
        "stages_total": total,
        "prior_regressions": 0,
        "first_failure_class": first_failure_class,
        "wall_ms": int(round(wall_s * 1000.0)),
        "repair_loops": repair_loops,
        "guidance_yields": 0,
        "repeat_failure_loops": 0,
        "verified_edits": verify_runs if verify_runs else None,
        "success": success,
        "outcome": "completed" if success else "failed",
    }
    if model_calls is not None:
        out["model_calls"] = model_calls
    return out


def trial_from_suite_run(
    run_dir: str | Path,
    *,
    trial_id: str,
    arm: str,
    recipe_id: str,
    model: Mapping[str, Any] | None = None,
    budget: Mapping[str, Any] | None = None,
    stages_total: int | None = 6,
    notes: str | None = None,
) -> dict[str, Any]:
    """Assemble one trial from a suite run directory (manifest + TIMING.jsonl)."""
    root = Path(run_dir).expanduser().resolve()
    manifest_path = root / "manifest.json"
    timing_path = root / "TIMING.jsonl"
    if not timing_path.is_file():
        raise FileNotFoundError(f"missing TIMING.jsonl under {root}")
    suite_id = None
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(manifest, Mapping):
            suite_id = manifest.get("suite_id")
            completed = manifest.get("completed_stages")
            failed_stage = manifest.get("failed_stage")
            if stages_total is None and isinstance(completed, list):
                stages_total = len(completed) + (1 if failed_stage else 0)
    events: list[Mapping[str, Any]] = []
    for line in timing_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if isinstance(row, Mapping):
            events.append(row)
    metrics = metrics_from_suite_timing(events, stages_total=stages_total)
    return assemble_gastronomic_trial(
        trial_id=trial_id,
        arm=arm,
        recipe_id=recipe_id,
        suite_id=str(suite_id) if suite_id is not None else None,
        metrics=metrics,
        model=model,
        budget=budget,
        notes=notes,
        development_outcome={
            "version": "1",
            "status": "ok" if metrics.get("success") else "failed",
            "outcome": metrics.get("outcome") or "unknown",
            "reason": "derived from suite TIMING.jsonl",
            "provenance": {"source": "suite_timing", "run_dir": str(root)},
        },
    )


def live_comparison_status(
    *,
    arm_a: Mapping[str, Any] | None = None,
    arm_b: Mapping[str, Any] | None = None,
    endpoint_configured: bool = False,
    arm_b_blocker: str = ARM_B_LIVE_BLOCKER,
) -> dict[str, Any]:
    """Host-facing live A/B status; never invents missing arm results."""

    def _arm(record: Mapping[str, Any] | None, *, blocker: str | None) -> dict[str, Any]:
        if record is None:
            return {
                "status": "not_run",
                "blocker": blocker,
                "trial": None,
            }
        return {"status": "recorded", "blocker": None, "trial": dict(record)}

    return {
        "version": LIVE_STATUS_VERSION,
        "endpoint_configured": bool(endpoint_configured),
        "arms": {
            "A": _arm(arm_a, blocker=None if endpoint_configured else "MECHA_BASE_URL unset"),
            "B": _arm(
                arm_b,
                blocker=None if arm_b is not None else arm_b_blocker,
            ),
        },
        "comparable_ab": bool(arm_a is not None and arm_b is not None),
        "winner": None,
        "caveats": [
            "Do not claim reliability improvement from a single stochastic run",
            "Mark missing arms not_run rather than fabricating results",
        ],
    }


def summarize_gastronomic_comparison(
    trials: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Aggregate trial arms without declaring a single-run winner."""
    by_arm: dict[str, list[Mapping[str, Any]]] = {a: [] for a in sorted(ARMS)}
    valid: list[Mapping[str, Any]] = []
    invalid = 0
    for row in trials:
        if not isinstance(row, Mapping):
            invalid += 1
            continue
        check = validate_gastronomic_trial(row)
        if not check["ok"]:
            invalid += 1
            continue
        valid.append(row)
        by_arm[str(row["arm"])].append(row)

    def _arm_summary(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
        if not rows:
            return {
                "n": 0,
                "success_rate": None,
                "mean_model_calls": None,
                "mean_wall_ms": None,
                "mean_repair_loops": None,
            }
        n = len(rows)
        successes = sum(1 for r in rows if r.get("success"))
        def _mean(key: str) -> float | None:
            vals = []
            for r in rows:
                metrics = r.get("metrics")
                if not isinstance(metrics, Mapping):
                    continue
                raw = metrics.get(key)
                if raw is None:
                    continue
                try:
                    vals.append(float(raw))
                except (TypeError, ValueError):
                    continue
            if not vals:
                return None
            return sum(vals) / len(vals)

        return {
            "n": n,
            "success_rate": successes / n,
            "mean_model_calls": _mean("model_calls"),
            "mean_wall_ms": _mean("wall_ms"),
            "mean_repair_loops": _mean("repair_loops"),
        }

    arms = {arm: _arm_summary(rows) for arm, rows in by_arm.items()}
    comparable = bool(arms["A"]["n"] and arms["B"]["n"])
    # Never auto-declare a winner; hosts interpret under matched budgets.
    return {
        "version": TRIAL_VERSION,
        "trial_count": len(valid),
        "invalid_count": invalid,
        "arms": arms,
        "comparable_ab": comparable,
        "winner": None,
        "caveats": [
            "Do not claim reliability improvement from a single stochastic run",
            "Match model, tools, suite, and inference budget across compared arms",
            "Prefer multiple trials; inspect mean_model_calls before success_rate",
        ],
    }


__all__ = [
    "ARMS",
    "ARM_B_LIVE_BLOCKER",
    "LIVE_STATUS_VERSION",
    "RECIPE_IDS",
    "TRIAL_VERSION",
    "assemble_gastronomic_trial",
    "live_comparison_status",
    "metrics_from_suite_timing",
    "summarize_gastronomic_comparison",
    "trial_from_suite_run",
    "validate_gastronomic_trial",
]
