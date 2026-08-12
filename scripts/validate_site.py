#!/usr/bin/env python3
"""Validate the GitHub Pages site and its installable Dataverse package."""

from __future__ import annotations

import json
import struct
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

from update_release_manifest import FULL_COMMIT_PATTERN, MANIFEST_PATH, inspect_package, read_config


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
INDEX = SITE / "index.html"
PREVIEW = SITE / "assets" / "conversation-insights-preview.png"


class ReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        attribute = "href" if tag in {"a", "link"} else "src" if tag in {"img", "script"} else None
        if attribute and values.get(attribute):
            self.references.append(values[attribute] or "")


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def validate_html(html: str, config: dict[str, dict[str, str]]) -> None:
    required = [
        'id="capabilities"',
        'id="architecture"',
        'id="install"',
        'id="preview-download"',
        config["core"]["filename"],
        "downloads/release-manifest.json",
        'id="trust-package"',
        'id="download-package"',
        "Import only what you trust",
        'id="trust-codeapp"',
        'id="download-codeapp"',
        "Understand the preview risk",
        'data-release-version="core"',
        'data-release-version="codeApp"',
        'id="import-command"',
        'wireDownloadGate("trust-package", "download-package")',
        'wireDownloadGate("trust-codeapp", "download-codeapp")',
        "Preview features can change, have limited support, or become unavailable.",
        "docs/permissions-and-inventory.md",
    ]
    missing = [value for value in required if value not in html]
    if missing:
        fail(f"site/index.html is missing required release content: {missing}")

    parser = ReferenceParser()
    parser.feed(html)
    for reference in parser.references:
        parsed = urlparse(reference)
        if parsed.scheme or parsed.netloc or reference.startswith(("#", "mailto:")):
            continue
        path = (SITE / parsed.path).resolve()
        if SITE.resolve() not in path.parents and path != SITE.resolve():
            fail(f"local reference escapes site/: {reference}")
        if not path.exists():
            fail(f"broken local reference in site/index.html: {reference}")


def validate_packages(config: dict[str, dict[str, str]]) -> None:
    try:
        actual = {
            "core": inspect_package("core", config["core"]),
            "codeApp": inspect_package("codeApp", config["codeApp"]),
        }
    except (FileNotFoundError, KeyError, RuntimeError, ValueError) as exc:
        fail(str(exc))

    if not MANIFEST_PATH.is_file():
        fail(f"missing release manifest: {MANIFEST_PATH.relative_to(ROOT)}")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not FULL_COMMIT_PATTERN.fullmatch(manifest.get("sourceCommit", "")):
        fail("release manifest sourceCommit must be a full 40-character lowercase Git commit SHA")
    for key, package in actual.items():
        published = manifest.get("artifacts", {}).get(key)
        if published != package:
            fail(f"release manifest is stale for {key}; run scripts/update_release_manifest.py")


def validate_preview() -> None:
    if not PREVIEW.is_file():
        fail(f"missing product preview: {PREVIEW.relative_to(ROOT)}")
    with PREVIEW.open("rb") as image:
        signature = image.read(24)
    if signature[:8] != b"\x89PNG\r\n\x1a\n":
        fail("product preview is not a PNG")
    width, height = struct.unpack(">II", signature[16:24])
    if width < 1200 or height < 700:
        fail(f"product preview is too small: {width}x{height}")


def main() -> None:
    if not INDEX.is_file():
        fail("site/index.html is missing")
    config = read_config()
    validate_packages(config)
    validate_preview()
    html = INDEX.read_text(encoding="utf-8")
    validate_html(html, config)
    print(
        "PASS: Pages site, core and preview managed packages, release manifest, "
        "trust gates, package components, and local references are valid"
    )


if __name__ == "__main__":
    main()