"""Harness experiment dimension vectors (MH-MHRL-02).

FineEnvs identifies action format, context structure, and control flow as major
harness-overfitting axes; experiments should declare fixed vs varying dimensions
(https://fineenvs-multi-harness-rl.hf.space/?__theme=system#why-models-overfit-to-a-single-harness)::

    >>> from mechaharness.experiment_dimensions import ExperimentDimensions
    >>> dims = ExperimentDimensions(
    ...     fixed={"model_revision": "m@1", "task_family": "math"},
    ...     varying={"tool_surface": ["Read", "Edit"], "retry_policy": "once"},
    ... )
    >>> dims.fingerprint_parts()["varying"]["tool_surface"]
    ['Edit', 'Read']
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.model_input_manifest import content_digest


class ExperimentDimensions(BaseModel):
    """Fixed vs varying configuration axes for a harness experiment."""

    model_config = ConfigDict(extra="allow")

    fixed: dict[str, Any] = Field(default_factory=dict)
    varying: dict[str, Any] = Field(default_factory=dict)
    detail: dict[str, Any] = Field(default_factory=dict)

    def fingerprint_parts(self) -> dict[str, Any]:
        def _norm(values: Mapping[str, Any]) -> dict[str, Any]:
            out: dict[str, Any] = {}
            for key in sorted(values):
                value = values[key]
                if isinstance(value, list):
                    out[key] = sorted(value, key=str)
                else:
                    out[key] = value
            return out

        return {"fixed": _norm(self.fixed), "varying": _norm(self.varying)}

    def digest(self) -> str:
        return content_digest(self.fingerprint_parts())


def require_dimension_trace_fields(
    trace_fields: Mapping[str, Any],
    *,
    dimensions: ExperimentDimensions,
) -> dict[str, Any]:
    """Ensure experiment assignment traces carry dimension digests."""
    out = dict(trace_fields)
    out["experiment_dimensions_digest"] = dimensions.digest()
    out["experiment_dimensions"] = dimensions.fingerprint_parts()
    return out
