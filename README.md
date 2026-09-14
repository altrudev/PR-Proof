# DDC PR Proof

**Know what your pull request really changes.**

PRs tell you what changed. **DDC PR Proof tells you what changed that matters.**

DDC PR Proof is a local-first semantic proof-of-change layer for GitHub pull requests. It is intentionally not another generic AI code reviewer. Its job is to identify changes in behavior, boundaries, authority, failure semantics, assumptions, dependencies, configuration, tests, and declared guarantees, then compare those consequences with the PR's stated intent.

## What a PR gets

Example result:

    DDC PR PROOF

    Overall impact: MODERATE
    Merge posture: REVIEW

    DDC Surprise Score: 73/100
    Intent Alignment: 62%

    Behavior changes
    ✓ implementation changed

    Authority changes
    ⚠ permission semantics may have changed

    Failure-mode changes
    ⚠ retry / rollback behavior changed

    Test coverage
    ⚠ implementation changed without a test-file change

    DDC verdict:
    REVIEW BEFORE MERGE

Every run also writes a machine-readable proof to .ddc/pr-proof.json with a proof hash.

## v0.1 checks

The deterministic local engine currently checks:

1. Intent versus observed diff alignment
2. Dependency changes
3. Configuration and permission / authority changes
4. Test-behavior changes
5. Failure, retry, recovery, and rollback changes
6. Documentation / declared-guarantee contradictions

It also reports three public metrics:

- **DDC Surprise Score** — how much material semantic impact exceeds the stated PR intent.
- **Intent Alignment** — how closely the declared purpose matches detected change categories.
- **Merge Posture** — PASS, REVIEW, or BLOCK.

The scores are evidence-backed heuristics, not probabilistic truth claims. Findings expose the evidence that contributed to them.

## GitHub Action

For the current development branch, pin to main. A versioned v1 tag should be published only after the first external validation pass.

Create .github/workflows/ddc-pr-proof.yml:

    name: DDC PR Proof

    on:
      pull_request:
        types: [opened, synchronize, reopened, edited]

    permissions:
      contents: read
      pull-requests: write
      issues: write

    jobs:
      proof:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
            with:
              fetch-depth: 0
              ref: ${{ github.event.pull_request.head.sha }}

          - uses: altrudev/PR-Proof@main
            with:
              github-token: ${{ secrets.GITHUB_TOKEN }}

The source diff stays inside the GitHub runner. v0.1 does not call an external model or external DDC service.

## Local CLI

No external Python dependencies are required.

    git clone https://github.com/altrudev/PR-Proof.git
    cd PR-Proof
    python3 pr_proof.py analyze --base origin/main --head HEAD \
      --title "Clean up retry handling" \
      --body "Refactor only"

Or install the CLI package:

    python3 -m pip install .
    ddc-pr-proof analyze --base origin/main

## Trust boundary

LOCAL mode is the default and currently the only implemented mode.

- no external LLM
- no source-code upload
- no telemetry
- no remote code execution
- GitHub token is used only for updating the PR proof comment
- deterministic JSON proof emitted on every run

An optional ENHANCED mode may later accept a user-selected model, but it must remain separable from the deterministic proof and clearly identify model-derived claims.

## What PR Proof is not

It is not a replacement for CodeQL, secret scanning, dependency scanning, tests, or human review.

Those tools ask questions such as whether a vulnerability, secret, or failing test exists.

PR Proof asks a different question:

> **Did this pull request change the system's guarantees, authority, behavior, assumptions, or failure semantics in ways the stated intent does not make obvious?**

## Roadmap

Near-term work is deliberately narrow:

- per-finding confidence and provenance
- stronger language-aware semantic diff adapters
- config / permission adapters for common ecosystems
- test-to-behavior linkage
- contradiction graph across docs, config, and code
- proof receipts tied to commit SHA and DDC version
- optional signed attestations
- stable v1 action tag after external validation

## Status

v0.1 is an early deterministic proof engine. The repository dogfoods PR Proof on its own pull requests.

Copyright © 2026 Valentyn Rukhaylo / Altru.dev. All rights reserved.
