"""Controlled demo target for DDC PR Proof."""
from __future__ import annotations

RETRY_COUNT = 3
TIMEOUT_SECONDS = 5


def call_with_retry(operation):
    last_error = None
    for _ in range(RETRY_COUNT):
        try:
            return operation(timeout=TIMEOUT_SECONDS)
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise RuntimeError("operation did not execute")


def rollback(state):
    state.restore()
