#!/usr/bin/env python3
"""Report or remove stale files under the gitignored ``output/`` working directory.

``output/`` accumulates managed package exports, extracted solution trees, and one-off probe
captures. Only two kinds of file there are worth keeping:

* the managed packages named by ``config/release-packages.json`` (in-flight candidates) and
  ``site/downloads/release-manifest.json`` (currently published bytes), plus their candidate
  manifests; and
* files that tracked documentation, configuration, scripts, or workflows reference by path.

The reference scan is deliberately dynamic so a newly referenced capture is retained without
editing this script.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = "output"
CANDIDATE_DIR = "candidate"
MANIFEST_PREFIX = "candidate-manifest-"

PACKAGE_SOURCES = (
    "config/release-packages.json",
    "site/downloads/release-manifest.json",
)

REFERENCE_GLOBS = (
    "*.md",
    "docs/*.md",
    "config/*.json",
    "scripts/*.py",
    "scripts/*/*.py",
    "scripts/*/*.md",
    ".github/workflows/*.yml",
    ".github/skills/*/SKILL.md",
    ".github/instructions/*.md",
)

REFERENCE_PATTERN = re.compile(r"output/([A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)*)")


def package_filenames(root: Path) -> set[str]:
    names: set[str] = set()
    for relative in PACKAGE_SOURCES:
        path = root / relative
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        artifacts = data.get("artifacts", data)
        if not isinstance(artifacts, dict):
            continue
        for entry in artifacts.values():
            if isinstance(entry, dict) and isinstance(entry.get("filename"), str):
                names.add(entry["filename"])
    return names


def referenced_relative_paths(root: Path) -> set[str]:
    references: set[str] = set()
    for pattern in REFERENCE_GLOBS:
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            references.update(REFERENCE_PATTERN.findall(text))
    return references


def keep_relative_paths(root: Path) -> set[str]:
    """Paths relative to ``output/`` that must survive a clean."""
    keep = {f"{CANDIDATE_DIR}/{name}" for name in package_filenames(root)}
    keep.update(referenced_relative_paths(root))
    return keep


def stale_files(root: Path) -> list[Path]:
    output = root / OUTPUT_DIR
    if not output.is_dir():
        return []
    keep = keep_relative_paths(root)
    stale: list[Path] = []
    for path in sorted(output.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(output).as_posix()
        if relative in keep:
            continue
        if path.parent.name == CANDIDATE_DIR and path.name.startswith(MANIFEST_PREFIX):
            continue
        stale.append(path)
    return stale


def prune_empty_directories(root: Path) -> None:
    output = root / OUTPUT_DIR
    if not output.is_dir():
        return
    for path in sorted(output.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Delete the stale files instead of reporting them")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()

    stale = stale_files(args.root)
    total = sum(path.stat().st_size for path in stale)
    output = args.root / OUTPUT_DIR

    for path in stale:
        print(f"stale  {path.relative_to(output).as_posix()}")

    verb = "Removed" if args.apply else "Would remove"
    print(f"{verb} {len(stale)} file(s), {total / 1_048_576:.2f} MB")

    if args.apply:
        for path in stale:
            path.unlink()
        prune_empty_directories(args.root)
    elif stale:
        print("Run with --apply to delete them.")


if __name__ == "__main__":
    main()
