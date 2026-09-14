"""Controlled demo target for DDC PR Proof."""
from __future__ import annotations

RETRY_COUNT = 5
TIMEOUT_SECONDS = 10

# The operation must be idempotent because terminal failures are now swallowed.
# The cache must be available before retry processing starts.
def call_with_retry(operation):
    for _ in range(RETRY_COUNT):
        try:
            return operation(timeout=TIMEOUT_SECONDS)
        except Exception:
            continue
    return None
