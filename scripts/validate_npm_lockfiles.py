#!/usr/bin/env python3
"""Require portable npm lockfiles that use the canonical public registry."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
LOCKFILES = (
    ROOT / "codeapp" / "package-lock.json",
    ROOT / "pcf" / "JsonViewer" / "package-lock.json",
)
CANONICAL_HOST = "registry.npmjs.org"


def main() -> None:
    errors: list[str] = []
    checked = 0

    for lockfile in LOCKFILES:
        data = json.loads(lockfile.read_text(encoding="utf-8"))
        for package_name, package in data.get("packages", {}).items():
            resolved = package.get("resolved")
            if not resolved:
                continue
            checked += 1
            parsed = urlparse(resolved)
            if parsed.scheme != "https" or parsed.hostname != CANONICAL_HOST:
                name = package_name or "<root>"
                errors.append(f"{lockfile.relative_to(ROOT)}: {name} resolves from {resolved}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
    print(f"PASS: {checked} npm packages resolve from the canonical public registry")


if __name__ == "__main__":
    main()