#!/usr/bin/env python3
# DDC PR Proof
# Copyright © 2026 Valentyn Rukhaylo. All rights reserved.
# Created by Valentyn Rukhaylo / Altru.dev
# https://www.linkedin.com/in/val-rukhaylo-437a1b3b6/
# See LICENSE and NOTICE for terms and attribution.
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

VERSION = "0.1.0"
MARKER = "<!-- ddc-pr-proof -->"

DEP_FILES = {
    "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
    "pyproject.toml", "poetry.lock", "requirements.txt", "Pipfile", "Pipfile.lock",
    "Cargo.toml", "Cargo.lock", "go.mod", "go.sum", "Gemfile", "Gemfile.lock"
}
SRC = re.compile(r"\.(py|js|jsx|ts|tsx|go|rs|java|kt|rb|php|c|cc|cpp|h|hpp|cs|swift)$", re.I)
TEST = re.compile(r"(^|/)(tests?|specs?)(/|$)|(_test|\.test|\.spec)\.", re.I)
CONFIG = re.compile(r"(^|/)(\.github/workflows|config|configs|infra|deploy|k8s|helm)(/|$)|\.(ya?ml|toml|ini|conf|env)$", re.I)
AUTH = re.compile(r"\b(auth|authori[sz]|permission|role|scope|token|credential|privilege|acl|policy)\b", re.I)
FAIL = re.compile(r"\b(rollback|retry|retries|timeout|except|catch|recover|fallback|failover|circuit.?breaker|compensat|undo)\b", re.I)
INPUT = re.compile(r"\b(input|request|payload|param|argument|schema|validation|sanitize|parse)\b", re.I)
ASSUME = re.compile(r"\b(assum|require|must|available|idempot|cache|database|network|reachable|exists|non.?null|guarantee)\b", re.I)
PERM = re.compile(r"\bpermissions?\s*:|\bcontents\s*:|\bpull-requests\s*:|\bactions\s*:|\bpackages\s*:|\bid-token\s*:", re.I)
DOC = re.compile(r"(^|/)(README|CHANGELOG|docs?)(\.|/|$)", re.I)
FACT = re.compile(r"\b([A-Za-z][\w .-]{1,40})\s*(?:=|:|is|are)\s*(\d+(?:\.\d+)?)\b", re.I)

@dataclass
class Finding:
    category: str
    severity: str
    summary: str
    evidence: list[str] = field(default_factory=list)

@dataclass
class Proof:
    version: str
    base: str
    head: str
    changed_files: int
    findings: list[Finding]
    surprise_score: int
    intent_alignment: int
    overall_impact: str
    verdict: str
    proof_hash: str = ""

def run(*args: str, check: bool = True) -> str:
    p = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and p.returncode:
        raise RuntimeError("command failed: " + " ".join(args) + " :: " + p.stderr.strip())
    return p.stdout

def git(*args: str, check: bool = True) -> str:
    return run("git", *args, check=check)

def resolve_base(explicit: str | None) -> str:
    if explicit:
        return explicit
    if os.getenv("DDC_BASE"):
        return os.environ["DDC_BASE"]
    ref = os.getenv("GITHUB_BASE_REF")
    if ref:
        candidate = "origin/" + ref
        if git("rev-parse", "--verify", candidate, check=False).strip():
            return candidate
        return ref
    for candidate in ("origin/main", "main", "origin/master", "master"):
        if git("rev-parse", "--verify", candidate, check=False).strip():
            return candidate
    raise RuntimeError("base ref unresolved; pass --base or action input base")

def files_changed(base: str, head: str) -> list[str]:
    return [x for x in git("diff", "--name-only", base + "..." + head).splitlines() if x.strip()]

def diff_lines(base: str, head: str) -> tuple[list[str], list[str]]:
    raw = git("diff", "--no-ext-diff", "--unified=1", base + "..." + head)
    added, removed = [], []
    for line in raw.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added.append(line[1:])
        elif line.startswith("-"):
            removed.append(line[1:])
    return added, removed

def hits(lines: list[str], rx: re.Pattern, limit: int = 4) -> list[str]:
    out = []
    for line in lines:
        if rx.search(line):
            clean = line.strip()
            if clean and clean not in out:
                out.append(clean[:220])
            if len(out) >= limit:
                break
    return out

def extract_declarations(path: str, text: str) -> list[tuple[str, str]]:
    """Extract a deliberately small set of comparable declarations."""
    out: list[tuple[str, str]] = []
    lower = text.lower()

    patterns = (
        ("retry_count", re.compile(r"\bretry[_ ]?count\s*(?:=|:|is)\s*(\d+)\b", re.I)),
        ("timeout_seconds", re.compile(r"\btimeout(?:[_ ]seconds)?\s*(?:=|:|is)\s*(\d+)\b", re.I)),
        ("rollback_enabled", re.compile(r"\brollback(?:[_ ]enabled)?\s*(?:=|:|is)?\s*(enabled|disabled|true|false)\b", re.I)),
    )
    for key, rx in patterns:
        for value in rx.findall(text):
            norm = str(value).lower()
            if norm == "enabled":
                norm = "true"
            elif norm == "disabled":
                norm = "false"
            out.append((key, norm))

    # Common code constants.
    for value in re.findall(r"\bRETRY_COUNT\s*=\s*(\d+)\b", text):
        out.append(("retry_count", value))
    for value in re.findall(r"\bTIMEOUT_SECONDS\s*=\s*(\d+)\b", text):
        out.append(("timeout_seconds", value))

    # Nested retry YAML commonly uses short keys.
    if re.search(r"(?m)^\s*retry\s*:\s*$", text):
        for value in re.findall(r"(?m)^\s*count\s*:\s*(\d+)\s*$", text):
            out.append(("retry_count", value))
        for value in re.findall(r"(?m)^\s*timeout_seconds\s*:\s*(\d+)\s*$", text):
            out.append(("timeout_seconds", value))
        for value in re.findall(r"(?m)^\s*rollback_enabled\s*:\s*(true|false)\s*$", lower):
            out.append(("rollback_enabled", value))

    return list(dict.fromkeys(out))


def cross_representation_contradictions(changed: list[str]) -> list[str]:
    """Find surviving declarations that disagree across tracked representations."""
    tracked = [x for x in git("ls-files").splitlines() if x.strip()]
    changed_set = set(changed)
    by_key: dict[str, list[tuple[str, str]]] = {}

    for path in tracked:
        if not (SRC.search(path) or CONFIG.search(path) or DOC.search(path) or path.lower().endswith(".md")):
            continue
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for key, value in extract_declarations(path, text):
            by_key.setdefault(key, []).append((path, value))

    evidence: list[str] = []
    for key, records in sorted(by_key.items()):
        values = {value for _, value in records}
        if len(values) < 2 or not any(path in changed_set for path, _ in records):
            continue
        rendered = " <> ".join(sorted({value + " @ " + path for path, value in records}))
        evidence.append(key + ": " + rendered)
    return evidence[:6]


def analyze_diff(base: str, head: str) -> tuple[list[Finding], dict[str, bool]]:
    files = files_changed(base, head)
    added, removed = diff_lines(base, head)
    findings: list[Finding] = []
    flags = {k: False for k in ("behavior","dependency","config","authority","failure","tests","input","assumption","contradiction")}

    source = [f for f in files if SRC.search(f) and not TEST.search(f)]
    tests = [f for f in files if TEST.search(f)]
    deps = [f for f in files if Path(f).name in DEP_FILES]
    configs = [f for f in files if CONFIG.search(f)]
    docs = [f for f in files if DOC.search(f) or f.lower().endswith(".md")]

    if source:
        flags["behavior"] = True
        findings.append(Finding("behavior", "info", str(len(source)) + " implementation file(s) changed", source[:5]))
    if deps:
        flags["dependency"] = True
        findings.append(Finding("dependencies", "review", "Dependency surface changed", deps[:5]))
    if configs:
        flags["config"] = True
        findings.append(Finding("configuration", "review", "Configuration or workflow surface changed", configs[:5]))

    authority = hits(added + removed, AUTH) + hits(added + removed, PERM)
    if authority:
        flags["authority"] = True
        findings.append(Finding("authority", "review", "Authority or permission semantics may have changed", authority[:6]))

    failure_added = hits(added, FAIL)
    failure_removed = hits(removed, FAIL)
    if failure_added or failure_removed:
        flags["failure"] = True
        severity = "review" if failure_removed else "info"
        evidence = ["removed: " + x for x in failure_removed] + ["added: " + x for x in failure_added]
        findings.append(Finding("failure_modes", severity, "Failure or rollback semantics changed", evidence[:6]))

    input_evidence = hits(added + removed, INPUT)
    if input_evidence:
        flags["input"] = True
        findings.append(Finding("input_boundary", "review", "Input or validation boundary changed", input_evidence))

    assumptions = hits(added, ASSUME)
    if assumptions:
        flags["assumption"] = True
        findings.append(Finding("assumptions", "review", "New or modified operational assumptions detected", assumptions))

    contradictions = cross_representation_contradictions(files)
    if contradictions:
        flags["contradiction"] = True
        findings.append(Finding(
            "contradictions", "review",
            "Surviving repository representations disagree",
            contradictions
        ))

    if tests:
        flags["tests"] = True
        findings.append(Finding("tests", "info", str(len(tests)) + " test file(s) changed", tests[:5]))
    elif source:
        findings.append(Finding("tests", "review", "Implementation changed without a test-file change", source[:5]))

    return findings, flags

def scores(title: str, body: str, flags: dict[str, bool]) -> tuple[int, int]:
    text = (title + "\n" + body).lower()
    terms = {
        "behavior": ("behavior","feature","fix","change","refactor","logic"),
        "dependency": ("dependency","dependencies","package","upgrade","bump"),
        "config": ("config","workflow","ci","deploy","configuration"),
        "authority": ("auth","permission","role","scope","policy"),
        "failure": ("retry","rollback","error","failure","timeout","recover"),
        "tests": ("test","spec","coverage"),
        "input": ("input","validation","request","payload","schema"),
        "assumption": ("assumption","cache","idempot","availability"),
        "contradiction": ("docs","readme","contract","guarantee","document")
    }
    material = [k for k in terms if flags.get(k)]
    mentioned = {k for k, words in terms.items() if any(w in text for w in words)}
    alignment = 100 if not material else round(100 * sum(k in mentioned for k in material) / len(material))
    narrow = bool(re.search(r"\b(refactor only|cleanup only|docs? only|no behavior change|non-functional|formatting only)\b", text))
    if narrow and any(flags.get(k) for k in ("behavior","authority","failure","input","dependency","config")):
        alignment = min(alignment, 25)
    weights = {"behavior":12,"dependency":15,"config":12,"authority":24,"failure":20,"input":16,"assumption":12,"contradiction":14}
    materiality = sum(v for k,v in weights.items() if flags.get(k))
    surprise = min(100, round(materiality * 0.6 + (100 - alignment) * 0.65 + (20 if narrow else 0)))
    return surprise, alignment

def posture(findings: list[Finding], surprise: int, alignment: int) -> tuple[str, str]:
    authority = any(f.category == "authority" for f in findings)
    failure = any(f.category == "failure_modes" and f.severity == "review" for f in findings)
    untested = any(f.category == "tests" and f.severity == "review" for f in findings)
    review = any(f.severity == "review" for f in findings)
    if surprise >= 90 or alignment <= 20 or (authority and failure and untested):
        return "HIGH", "BLOCK"
    if review or surprise >= 45 or alignment < 75:
        return "MODERATE", "REVIEW"
    return "LOW", "PASS"

def render(p: Proof) -> str:
    grouped: dict[str, list[Finding]] = {}
    for finding in p.findings:
        grouped.setdefault(finding.category, []).append(finding)
    lines = [
        MARKER,
        "## DDC PR PROOF",
        "",
        "**Overall impact:** " + p.overall_impact,
        "**Merge posture:** " + p.verdict,
        "",
        "**DDC Surprise Score:** " + str(p.surprise_score) + "/100",
        "**Intent Alignment:** " + str(p.intent_alignment) + "%",
        ""
    ]
    order = [
        ("behavior","Behavior changes"),
        ("input_boundary","Security / input boundary changes"),
        ("authority","Authority changes"),
        ("failure_modes","Failure-mode changes"),
        ("assumptions","New assumptions"),
        ("contradictions","Contradictions"),
        ("dependencies","Dependency changes"),
        ("configuration","Configuration changes"),
        ("tests","Test coverage")
    ]
    for key, heading in order:
        if key not in grouped:
            continue
        lines.append("### " + heading)
        for finding in grouped[key]:
            lines.append(("⚠ " if finding.severity == "review" else "✓ ") + finding.summary)
            for ev in finding.evidence[:4]:
                lines.append("  - `" + ev.replace("`", "'") + "`")
        lines.append("")
    lines += [
        "### DDC verdict",
        "**" + p.verdict + (" BEFORE MERGE" if p.verdict != "PASS" else "") + "**",
        "",
        "DDC PR Proof v" + p.version + " | changed files: " + str(p.changed_files),
        "Proof hash: " + p.proof_hash
    ]
    return "\n".join(lines)

def event_intent() -> tuple[str, str, str | None, int | None]:
    title = os.getenv("DDC_PR_TITLE", "")
    body = os.getenv("DDC_PR_BODY", "")
    repo = os.getenv("GITHUB_REPOSITORY")
    number = None
    path = os.getenv("GITHUB_EVENT_PATH")
    if path and Path(path).exists():
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        pr = data.get("pull_request", {})
        title = title or pr.get("title", "")
        body = body or pr.get("body", "") or ""
        number = pr.get("number") or data.get("number")
    return title, body, repo, int(number) if number else None

def api(method: str, url: str, token: str, payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else None

def upsert_comment(markdown: str, repo: str | None, number: int | None) -> None:
    token = os.getenv("DDC_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token or not repo or not number or os.getenv("DDC_POST_COMMENT", "true").lower() != "true":
        return
    url = "https://api.github.com/repos/" + repo + "/issues/" + str(number) + "/comments"
    try:
        comments = api("GET", url, token)
        existing = next((c for c in comments if MARKER in c.get("body", "")), None)
        if existing:
            api("PATCH", "https://api.github.com/repos/" + repo + "/issues/comments/" + str(existing["id"]), token, {"body": markdown})
        else:
            api("POST", url, token, {"body": markdown})
    except Exception as exc:
        print("warning: PR comment update failed: " + str(exc), file=sys.stderr)

def write_outputs(p: Proof, proof_file: str) -> None:
    path = os.getenv("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write("verdict=" + p.verdict + "\n")
        f.write("surprise_score=" + str(p.surprise_score) + "\n")
        f.write("intent_alignment=" + str(p.intent_alignment) + "\n")
        f.write("proof_file=" + proof_file + "\n")

def command_analyze(args) -> int:
    base = resolve_base(args.base)
    head = args.head or "HEAD"
    title, body, repo, number = event_intent()
    title = args.title or title
    body = args.body or body
    findings, flags = analyze_diff(base, head)
    surprise, alignment = scores(title, body, flags)
    impact, verdict = posture(findings, surprise, alignment)
    base_sha = git("rev-parse", base).strip()
    head_sha = git("rev-parse", head).strip()
    proof = Proof(VERSION, base_sha, head_sha, len(files_changed(base, head)), findings, surprise, alignment, impact, verdict)
    canonical = json.dumps({**asdict(proof), "proof_hash": ""}, sort_keys=True, separators=(",", ":"))
    proof.proof_hash = hashlib.sha256(canonical.encode()).hexdigest()
    out = args.output or ".ddc/pr-proof.json"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(asdict(proof), indent=2), encoding="utf-8")
    markdown = render(proof)
    print(markdown)
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(markdown + "\n")
    write_outputs(proof, out)
    upsert_comment(markdown, repo, number)
    return 2 if os.getenv("DDC_FAIL_ON", "never") == "block" and verdict == "BLOCK" else 0

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ddc-pr-proof", description="Local-first semantic proof-of-change")
    p.add_argument("--version", action="version", version=VERSION)
    sub = p.add_subparsers(dest="command")
    a = sub.add_parser("analyze")
    a.add_argument("--base")
    a.add_argument("--head", default="HEAD")
    a.add_argument("--title", default="")
    a.add_argument("--body", default="")
    a.add_argument("--output")
    return p

def main() -> int:
    p = parser()
    args = p.parse_args()
    if not args.command:
        args = p.parse_args(["analyze"] + sys.argv[1:])
    try:
        return command_analyze(args)
    except Exception as exc:
        print("DDC PR Proof error: " + str(exc), file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
