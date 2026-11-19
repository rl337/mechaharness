"""Cross-process locks for file-backed run state."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    # SQLite releases the lock on close or process death on Unix and Windows.
    with closing(sqlite3.connect(path, timeout=3600)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        yield
