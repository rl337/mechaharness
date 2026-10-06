"""Composable evaluators over deterministic checks and optional judges.

Anthropic's eval guidance prefers deterministic graders where possible and
calibrated model graders otherwise
(https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents).
The Verification Horizon paper warns that evaluators can become proxy targets
and need versioning / held-out protection
(https://arxiv.org/abs/2606.26300).

MechaHarness exposes a versioned ``Evaluator`` that emits claims::

    >>> from mechaharness.eval_evidence import Claim
    >>> from mechaharness.evaluator import Evaluator, evaluate_claims
    >>> class FileExistsEvaluator(Evaluator):
    ...     evaluator_id = "demo:file_exists"
    ...     version = "1"
    ...     held_out = True
    ...     def evaluate(self, subject):
    ...         ok = bool(subject.get("exists"))
    ...         return [Claim(id="exists", statement="file exists",
    ...                       status="pass" if ok else "fail")]
    >>> result = evaluate_claims(FileExistsEvaluator(), {"exists": True})
    >>> result.passed
    True
    >>> result.evaluator_id
    'demo:file_exists'
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mechaharness.eval_evidence import Claim, all_passed, compose_claims


class Evaluator(ABC):
    """Versioned, optionally held-out producer of typed claims."""

    evaluator_id: str = "evaluator"
    version: str = "1"
    held_out: bool = False

    @abstractmethod
    def evaluate(self, subject: Mapping[str, Any]) -> list[Claim]:
        """Return independently resolvable claims about ``subject``."""


class EvaluatorResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    evaluator_id: str
    version: str
    held_out: bool = False
    claims: list[Claim] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    passed: bool = False
    harness_fingerprint: str | None = None
    objective_policy_id: str | None = None
    objective_policy_version: str | None = None
    objective_scalar: float | None = None


def evaluate_claims(evaluator: Evaluator, subject: Mapping[str, Any]) -> EvaluatorResult:
    claims = list(evaluator.evaluate(subject))
    return EvaluatorResult(
        evaluator_id=evaluator.evaluator_id,
        version=evaluator.version,
        held_out=evaluator.held_out,
        claims=claims,
        counts=compose_claims(claims),
        passed=all_passed(claims),
    )


class CallableEvaluator(Evaluator):
    """Adapter turning a claim-producing callable into an Evaluator."""

    def __init__(
        self,
        fn: Callable[[Mapping[str, Any]], list[Claim]],
        *,
        evaluator_id: str = "callable",
        version: str = "1",
        held_out: bool = False,
    ) -> None:
        self._fn = fn
        self.evaluator_id = evaluator_id
        self.version = version
        self.held_out = held_out

    def evaluate(self, subject: Mapping[str, Any]) -> list[Claim]:
        return list(self._fn(subject))
