"""Backward-compatible re-export — prefer ``mechaharness.decision_log``."""

from mechaharness.decision_log import *  # noqa: F403
from mechaharness.decision_log import (  # noqa: F401
    DecisionLog,
    DecisionRecord,
    DecisionRecorded,
    replay_verdict,
    signals_to_map,
)
