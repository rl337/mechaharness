"""Gastronomic vs guided_coding comparison trial records (post-M6).

Hosts record comparable trial arms without declaring a winner from a single
stochastic run. DevelopmentOutcome is host evidence; model text is not.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

TRIAL_VERSION = "1"

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
    "RECIPE_IDS",
    "TRIAL_VERSION",
    "assemble_gastronomic_trial",
    "summarize_gastronomic_comparison",
    "validate_gastronomic_trial",
]
