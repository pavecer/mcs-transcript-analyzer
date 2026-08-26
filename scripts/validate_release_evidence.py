#!/usr/bin/env python3
"""Validate machine-readable evidence for the currently published release."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = ROOT / "config" / "release-evidence.json"
MANIFEST_PATH = ROOT / "site" / "downloads" / "release-manifest.json"
FULL_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_GATES = {
    "pvePackageAndRuntime",
    "hostedUiSmoke",
    "tpmManualUpgrade",
}


def fail(errors: list[str]) -> None:
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def valid_timestamp(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    offset = parsed.utcoffset()
    return parsed.tzinfo is not None and offset is not None and offset.total_seconds() == 0


def main() -> None:
    evidence = load_json(EVIDENCE_PATH)
    manifest = load_json(MANIFEST_PATH)
    errors: list[str] = []

    if evidence.get("schemaVersion") != 1:
        errors.append("release evidence schemaVersion must be 1")

    source_commit = evidence.get("sourceCommit")
    if not isinstance(source_commit, str) or not FULL_COMMIT_PATTERN.fullmatch(source_commit):
        errors.append("release evidence sourceCommit must be a full lowercase Git SHA")
    if source_commit != manifest.get("sourceCommit"):
        errors.append("release evidence sourceCommit does not match the published manifest")

    manifest_artifacts = manifest.get("artifacts", {})
    if not isinstance(manifest_artifacts, dict):
        errors.append("published manifest artifacts must be an object")
        manifest_artifacts = {}
    versions = {
        artifact.get("version")
        for artifact in manifest_artifacts.values()
        if isinstance(artifact, dict)
    }
    if len(versions) != 1 or evidence.get("version") not in versions:
        errors.append("release evidence version does not match all published artifacts")

    candidate = evidence.get("candidate", {})
    if not isinstance(candidate, dict):
        errors.append("release evidence candidate must be an object")
        candidate = {}
    if candidate.get("sourceCommit") != source_commit:
        errors.append("candidate evidence sourceCommit does not match the published source commit")
    candidate_artifacts = candidate.get("artifacts", {})
    if not isinstance(candidate_artifacts, dict):
        errors.append("candidate evidence artifacts must be an object")
        candidate_artifacts = {}
    if set(candidate_artifacts) != set(manifest_artifacts):
        errors.append("candidate evidence artifact set does not match the published manifest")
    else:
        for key, published in manifest_artifacts.items():
            recorded = candidate_artifacts.get(key, {})
            if not isinstance(published, dict) or not isinstance(recorded, dict):
                errors.append(f"{key} artifact evidence must be an object")
                continue
            if recorded.get("filename") != published.get("filename"):
                errors.append(f"{key} candidate evidence filename does not match the published manifest")
            if recorded.get("sha256") != published.get("sha256"):
                errors.append(f"{key} candidate evidence hash does not match the published package")

    gates = evidence.get("gates", {})
    if not isinstance(gates, dict):
        errors.append("release evidence gates must be an object")
        gates = {}
    if set(gates) != REQUIRED_GATES:
        errors.append(
            "release evidence gates must be exactly "
            + ", ".join(sorted(REQUIRED_GATES))
        )
    for name in sorted(REQUIRED_GATES):
        gate = gates.get(name, {})
        if not isinstance(gate, dict):
            errors.append(f"{name} release gate must be an object")
            continue
        if gate.get("status") != "passed":
            errors.append(f"{name} release gate is not passed")
        if not valid_timestamp(gate.get("completedAtUtc")):
            errors.append(f"{name} completedAtUtc is not a valid ISO-8601 timestamp")
        evidence_ref = gate.get("evidence", {})
        if not isinstance(evidence_ref, dict):
            errors.append(f"{name} evidence reference must be an object")
            continue
        relative = evidence_ref.get("path")
        marker = evidence_ref.get("contains")
        if not isinstance(relative, str) or not isinstance(marker, str) or not marker:
            errors.append(f"{name} evidence reference is incomplete")
            continue
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"{name} evidence file does not exist: {relative}")
        elif marker not in path.read_text(encoding="utf-8"):
            errors.append(f"{name} evidence marker is missing from {relative}")

    if errors:
        fail(errors)
    print(
        "PASS: published packages are tied to the approved candidate source, hashes, "
        "PVE validation, hosted UI smoke, and manual TPM upgrade evidence"
    )


if __name__ == "__main__":
    main()
