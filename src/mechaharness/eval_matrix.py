"""Model × harness/config × task-family evaluation matrix (MH-MHRL-17).

FineEnvs evaluates checkpoints under all harnesses and retains the per-harness
matrix so averages cannot hide catastrophic compatibility failures
(https://fineenvs-multi-harness-rl.hf.space/?__theme=system#accuracy).

MechaHarness indexes cells and always retains drill-down::

    >>> from mechaharness.eval_matrix import EvalMatrix, EvalMatrixCell
    >>> from mechaharness.eval_trial import Trial
    >>> matrix = EvalMatrix()
    >>> _ = matrix.add_trial(
    ...     Trial(trial_id="1", success=True),
    ...     model="m1",
    ...     harness_fingerprint="fp:a",
    ...     task_family="math",
    ... )
    >>> cell = matrix.cell("m1", "fp:a", "math")
    >>> cell.trial_count
    1
    >>> matrix.aggregate()["cells"][0]["task_family"]
    'math'
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.eval_trial import Trial, task_trials


class EvalMatrixCell(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    harness_fingerprint: str
    task_family: str
    trials: list[Trial] = Field(default_factory=list)
    detail: dict[str, Any] = Field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.model, self.harness_fingerprint, self.task_family)

    @property
    def trial_count(self) -> int:
        return len(self.trials)

    @property
    def success_rate(self) -> float | None:
        scored = task_trials(self.trials)
        if not scored:
            return None
        return sum(1 for t in scored if t.success) / len(scored)


class EvalMatrix(BaseModel):
    """Sparse matrix of evaluation cells with mandatory drill-down retention."""

    model_config = ConfigDict(extra="allow")

    cells: dict[str, EvalMatrixCell] = Field(default_factory=dict)

    @staticmethod
    def cell_id(model: str, harness_fingerprint: str, task_family: str) -> str:
        return f"{model}|{harness_fingerprint}|{task_family}"

    def cell(self, model: str, harness_fingerprint: str, task_family: str) -> EvalMatrixCell:
        cid = self.cell_id(model, harness_fingerprint, task_family)
        if cid not in self.cells:
            self.cells[cid] = EvalMatrixCell(
                model=model,
                harness_fingerprint=harness_fingerprint,
                task_family=task_family,
            )
        return self.cells[cid]

    def add_trial(
        self,
        trial: Trial,
        *,
        model: str,
        harness_fingerprint: str,
        task_family: str,
    ) -> EvalMatrixCell:
        cell = self.cell(model, harness_fingerprint, task_family)
        if trial.harness_fingerprint is None:
            trial = trial.model_copy(update={"harness_fingerprint": harness_fingerprint})
        cell.trials.append(trial)
        return cell

    def iter_cells(self) -> Iterable[EvalMatrixCell]:
        return self.cells.values()

    def aggregate(self) -> dict[str, Any]:
        """Aggregate while retaining every cell (no average-only collapse)."""
        cell_rows = []
        for cell in self.iter_cells():
            cell_rows.append(
                {
                    "model": cell.model,
                    "harness_fingerprint": cell.harness_fingerprint,
                    "task_family": cell.task_family,
                    "trial_count": cell.trial_count,
                    "success_rate": cell.success_rate,
                    "trial_ids": [t.trial_id for t in cell.trials],
                }
            )
        rates = [r["success_rate"] for r in cell_rows if r["success_rate"] is not None]
        return {
            "cell_count": len(cell_rows),
            "mean_success_rate": (sum(rates) / len(rates)) if rates else None,
            "cells": cell_rows,
        }
