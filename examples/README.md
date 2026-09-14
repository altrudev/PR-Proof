# Retry Demo Target

This directory exists only as a controlled validation fixture for DDC PR Proof.

Declared guarantees:

- retry count is 5
- timeout is 10 seconds
- rollback is enabled after terminal failure
- callers must not assume idempotency

The fixture is intentionally small so PR-Proof demonstrations can show how a seemingly narrow pull request can materially change behavior, failure handling, assumptions, and declared guarantees.
