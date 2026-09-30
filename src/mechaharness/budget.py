"""Execution budgets with soft and hard limits.

A :class:`BudgetPolicy` declares thresholds. A :class:`Budget` is the mutable
spend ledger for one graph run (shared with nested subgraphs so cost
aggregates). Soft breach asks the executor to wind down gracefully; hard
breach fails the run with prejudice. ``hard_limit=None`` means unlimited.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator


class BudgetLevel(str, Enum):
    """Where spent sits relative to the policy."""

    OK = "ok"
    SOFT = "soft"
    HARD = "hard"


class BudgetPolicy(BaseModel):
    """Soft / hard spend ceilings for a graph execution.

    Limits are in abstract cost units (aligned with ability-style units unless
    a host maps them otherwise). ``hard_limit=None`` is unlimited. Soft is
    optional; when set it must be ``<=`` hard when hard is finite.
    """

    model_config = ConfigDict(extra="allow")

    soft_limit: float | None = None
    hard_limit: float | None = None
    unit: Literal["units", "usd", "tokens"] = "units"

    @model_validator(mode="after")
    def _ordered_limits(self) -> BudgetPolicy:
        if self.soft_limit is not None and self.soft_limit < 0:
            raise ValueError("soft_limit must be >= 0")
        if self.hard_limit is not None and self.hard_limit < 0:
            raise ValueError("hard_limit must be >= 0")
        if (
            self.soft_limit is not None
            and self.hard_limit is not None
            and self.soft_limit > self.hard_limit
        ):
            raise ValueError("soft_limit must be <= hard_limit")
        return self

    @classmethod
    def unlimited(cls, **kwargs: Any) -> BudgetPolicy:
        """No soft ceiling; hard limit is unlimited."""
        return cls(soft_limit=None, hard_limit=None, **kwargs)

    def level_for(self, spent: float) -> BudgetLevel:
        if self.hard_limit is not None and spent >= self.hard_limit:
            return BudgetLevel.HARD
        if self.soft_limit is not None and spent >= self.soft_limit:
            return BudgetLevel.SOFT
        return BudgetLevel.OK


class Budget:
    """Mutable spend ledger bound to a :class:`BudgetPolicy`.

    Nested subgraphs should share the same instance (or a :meth:`child` view
    that charges the parent) so spend aggregates across the execution tree.
    """

    def __init__(
        self,
        policy: BudgetPolicy,
        *,
        parent: Budget | None = None,
        spent: float = 0.0,
    ) -> None:
        self.policy = policy
        self.spent = float(spent)
        self.charges: list[dict[str, Any]] = []
        self._parent = parent

    def status(self) -> BudgetLevel:
        return self.policy.level_for(self.spent)

    def remaining_hard(self) -> float | None:
        """Units left before hard failure, or ``None`` when unlimited."""
        if self.policy.hard_limit is None:
            return None
        return max(0.0, self.policy.hard_limit - self.spent)

    def remaining_soft(self) -> float | None:
        if self.policy.soft_limit is None:
            return None
        return max(0.0, self.policy.soft_limit - self.spent)

    def charge(
        self,
        amount: float,
        *,
        node_id: str | None = None,
        kind: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> BudgetLevel:
        """Add spend and return the post-charge level."""
        if amount < 0:
            raise ValueError("charge amount must be >= 0")
        if amount:
            self.spent += amount
            self.charges.append(
                {
                    "amount": amount,
                    "spent": self.spent,
                    "node_id": node_id,
                    "kind": kind,
                    **(detail or {}),
                }
            )
            if self._parent is not None:
                self._parent.charge(
                    amount,
                    node_id=node_id,
                    kind=kind,
                    detail=detail,
                )
        return self.status()

    def child(
        self,
        *,
        soft_limit: float | None = None,
        hard_limit: float | None = None,
        share: float = 1.0,
    ) -> Budget:
        """Nested budget that still rolls charges into this parent.

        When ``hard_limit`` is omitted, the child inherits a share of the
        parent's remaining hard headroom (or stays unlimited).
        """
        if share <= 0 or share > 1:
            raise ValueError("share must be in (0, 1]")
        parent_hard = self.remaining_hard()
        if hard_limit is None and parent_hard is not None:
            hard_limit = parent_hard * share
        if soft_limit is None and self.policy.soft_limit is not None:
            rem = self.remaining_soft()
            soft_limit = None if rem is None else rem * share
        return Budget(
            BudgetPolicy(
                soft_limit=soft_limit,
                hard_limit=hard_limit,
                unit=self.policy.unit,
            ),
            parent=self,
        )
