"""Backward-compatible re-export — prefer ``mechaharness.api_connection``."""

from mechaharness.api_connection import *  # noqa: F403
from mechaharness.api_connection import (  # noqa: F401
    DEFAULT_JUDGE_PATH,
    APIConnectionConfig,
    SimpleHttpConnectionConfig,
    connection_as_dict,
)
