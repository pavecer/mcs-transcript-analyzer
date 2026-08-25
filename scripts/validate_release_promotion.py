#!/usr/bin/env python3
"""Validate that a stable release exactly promotes a reviewed candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RELEASE_CONFIG_PATH = ROOT / "config" / "release-packages.json"
STABLE_MANIFEST_PATH = ROOT / "site" / "downloads" / "release-manifest.json"
PACKAGE_INPUTS = (
    "codeapp",
    "plugin",
    "pcf",
    "solution",
    "scripts/transcript_insights",
    "config/release-packages.json",
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package_source_commit() -> str:
    result = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", *PACKAGE_INPUTS],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--candidate-directory", type=Path, default=Path("output/candidate"))
    args = parser.parse_args()

    candidate_directory = (ROOT / args.candidate_directory).resolve()
    candidate_manifest = load_json(
        candidate_directory / f"candidate-manifest-{args.version}.json"
    )
    release_config = load_json(RELEASE_CONFIG_PATH)
    stable_manifest = load_json(STABLE_MANIFEST_PATH)
    errors: list[str] = []

    configured_versions = {release_config[key]["version"] for key in ("core", "codeApp")}
    if configured_versions != {args.version}:
        errors.append(f"release config versions do not equal {args.version}: {sorted(configured_versions)}")
    if candidate_manifest.get("version") != args.version:
        errors.append("candidate manifest version does not match the requested version")
    if candidate_manifest.get("tenantNeutral") is not True:
        errors.append("candidate manifest does not assert tenant neutrality")

    promoted: dict[str, Any] = {}
    for key in ("core", "codeApp"):
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

    source_commit = package_source_commit()
    if stable_manifest.get("sourceCommit") != source_commit:
        errors.append(
            "stable manifest sourceCommit does not match the latest package-input commit: "
            f"manifest={stable_manifest.get('sourceCommit')}, source={source_commit}"
        )

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)

    print(json.dumps({
        "status": "ok",
        "version": args.version,
        "sourceCommit": source_commit,
        "tenantNeutral": True,
        "artifacts": promoted,
    }, indent=2))


if __name__ == "__main__":
    main()