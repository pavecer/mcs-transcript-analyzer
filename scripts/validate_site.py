#!/usr/bin/env python3
"""Validate the GitHub Pages site and its installable Dataverse package."""

from __future__ import annotations

import hashlib
import re
import struct
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
INDEX = SITE / "index.html"
EXPECTED_SOLUTION = "pvConversationInsights"
EXPECTED_VERSION = "1.0.0.0"
PACKAGE_NAME = f"{EXPECTED_SOLUTION}-managed-{EXPECTED_VERSION}.zip"
PACKAGE = SITE / "downloads" / PACKAGE_NAME
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


def validate_html(html: str, checksum: str) -> None:
    required = [
        'id="capabilities"',
        'id="architecture"',
        'id="install"',
        PACKAGE_NAME,
        EXPECTED_VERSION,
        checksum,
        'id="trust-package"',
        'id="download-package"',
        "Import only what you trust",
        "downloadPackage.disabled = !trustPackage.checked",
        "The preview code app is not part of this ZIP.",
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


def validate_package() -> str:
    if not PACKAGE.is_file():
        fail(f"missing managed solution package: {PACKAGE.relative_to(ROOT)}")

    checksum = hashlib.sha256(PACKAGE.read_bytes()).hexdigest()
    with ZipFile(PACKAGE) as bundle:
        corrupt = bundle.testzip()
        if corrupt:
            fail(f"corrupt file in solution package: {corrupt}")
        try:
            manifest = ET.fromstring(bundle.read("solution.xml"))
        except KeyError:
            fail("solution package has no solution.xml")

        unique_name = manifest.findtext(".//UniqueName")
        version = manifest.findtext(".//Version")
        managed = manifest.findtext(".//Managed")
        if (unique_name, version, managed) != (EXPECTED_SOLUTION, EXPECTED_VERSION, "1"):
            fail(
                "unexpected solution identity: "
                f"name={unique_name!r}, version={version!r}, managed={managed!r}"
            )

        controls = [
            item for item in manifest.findall(".//RootComponent")
            if item.attrib.get("type") == "66"
            and item.attrib.get("schemaName") == "pvci_PvciControls.JsonViewer"
        ]
        if len(controls) != 1:
            fail("JSON Viewer PCF must be included exactly once as a root component")

        missing_controls = [
            item for item in manifest.findall(".//MissingDependency")
            if item.find("Required") is not None
            and item.find("Required").attrib.get("type") == "66"
        ]
        if missing_controls:
            fail("solution package still has an unresolved PCF dependency")

    return checksum


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
    checksum = validate_package()
    validate_preview()
    html = INDEX.read_text(encoding="utf-8")
    validate_html(html, checksum)
    print(
        f"PASS: Pages site, {EXPECTED_SOLUTION} {EXPECTED_VERSION}, "
        f"package checksum, PCF dependency, and local references are valid"
    )


if __name__ == "__main__":
    main()