#!/usr/bin/env python3
"""Validate that a stable release exactly promotes a reviewed candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from validate_candidate_packages import (
    artifact_keys,
    candidate_manifest_name,
    package_source_commit,
)


ROOT = Path(__file__).resolve().parents[1]
RELEASE_CONFIG_PATH = ROOT / "config" / "release-packages.json"
STABLE_MANIFEST_PATH = ROOT / "site" / "downloads" / "release-manifest.json"
PROMOTABLE_ARTIFACTS = ("core", "credits", "codeApp")
def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def published_source_commit(manifest: dict[str, Any], key: str) -> str | None:
    artifact = manifest.get("artifacts", {}).get(key, {})
    if isinstance(artifact, dict) and artifact.get("sourceCommit"):
        return str(artifact["sourceCommit"])
    legacy = manifest.get("sourceCommit")
    return str(legacy) if legacy else None


def candidate_scope_errors(manifest: dict[str, Any], selected_keys: tuple[str, ...]) -> list[str]:
    expected = set(selected_keys)
    scope = manifest.get("artifactScope")
    artifacts = manifest.get("artifacts")
    errors: list[str] = []
    if scope != list(selected_keys):
        errors.append("candidate manifest artifact scope does not match the requested scope")
    if not isinstance(artifacts, dict) or set(artifacts) != expected:
        errors.append("candidate manifest artifacts do not exactly match the requested scope")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--artifact", choices=PROMOTABLE_ARTIFACTS, required=True)
    parser.add_argument("--candidate-directory", type=Path, default=Path("output/candidate"))
    args = parser.parse_args()

    candidate_directory = (ROOT / args.candidate_directory).resolve()
    selected_keys = artifact_keys(args.artifact)
    selected_versions = {key: args.version for key in selected_keys}
    candidate_manifest = load_json(
        candidate_directory / candidate_manifest_name(args.artifact, selected_versions)
    )
    release_config = load_json(RELEASE_CONFIG_PATH)
    stable_manifest = load_json(STABLE_MANIFEST_PATH)
    errors: list[str] = []

    configured_versions = {key: release_config[key]["version"] for key in selected_keys}
    if set(configured_versions.values()) != {args.version}:
        errors.append(
            f"selected release config versions do not equal {args.version}: {configured_versions}"
        )
    if candidate_manifest.get("version") != args.version:
        errors.append("candidate manifest version does not match the requested version")
    errors.extend(candidate_scope_errors(candidate_manifest, selected_keys))
    if candidate_manifest.get("tenantNeutral") is not True:
        errors.append("candidate manifest does not assert tenant neutrality")

    promoted: dict[str, Any] = {}
    for key in selected_keys:
        configured = release_config[key]
        candidate = candidate_manifest.get("artifacts", {}).get(key, {})
        stable = stable_manifest.get("artifacts", {}).get(key, {})
        filename = configured["filename"]
        candidate_path = candidate_directory / filename
        stable_path = ROOT / "site" / "downloads" / filename
        if not candidate_path.is_file() or not stable_path.is_file():
            errors.append(f"{key} candidate or stable package is missing: {filename}")
            continue

        candidate_hash = sha256(candidate_path)
        stable_hash = sha256(stable_path)
        observed_hashes = {
            candidate_hash,
            stable_hash,
            str(candidate.get("sha256", "")).lower(),
            str(stable.get("sha256", "")).lower(),
        }
        if len(observed_hashes) != 1:
            errors.append(f"{key} candidate, stable package, and manifests are not byte-identical")
        if candidate.get("filename") != filename or stable.get("filename") != filename:
            errors.append(f"{key} manifest filename does not match release config: {filename}")
        if stable.get("version") != args.version:
            errors.append(f"{key} stable manifest version does not match {args.version}")
        promoted[key] = {"filename": filename, "sha256": stable_hash}

    source_commit = package_source_commit(args.artifact)
    if candidate_manifest.get("sourceCommit") != source_commit:
        errors.append(
            "candidate manifest sourceCommit does not match the latest package-input commit: "
            f"manifest={candidate_manifest.get('sourceCommit')}, source={source_commit}"
        )
    for key in selected_keys:
        if published_source_commit(stable_manifest, key) == source_commit:
            continue
        errors.append(
            f"stable {key} sourceCommit does not match the latest package-input commit: "
            f"manifest={published_source_commit(stable_manifest, key)}, source={source_commit}"
        )

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)

    print(json.dumps({
        "status": "ok",
        "version": args.version,
        "artifactScope": list(selected_keys),
        "sourceCommit": source_commit,
        "tenantNeutral": True,
        "artifacts": promoted,
    }, indent=2))


if __name__ == "__main__":
    main()