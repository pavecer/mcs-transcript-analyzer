#!/usr/bin/env python3
"""Validate the GitHub Pages site and its installable Dataverse package."""

from __future__ import annotations

import json
import hashlib
import struct
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from update_release_manifest import FULL_COMMIT_PATTERN, MANIFEST_PATH
from validate_release_evidence import main as validate_release_evidence
from validate_solution_ownership import main as validate_solution_ownership


ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
INDEX = SITE / "index.html"
PREVIEW = SITE / "assets" / "conversation-insights-preview.png"
RELEASE_CONFIG = ROOT / "config" / "release-packages.json"
LEGACY_ARTIFACT_KEYS = {"core", "codeApp"}
PUBLIC_COPY_FORBIDDEN_PHRASES = (
    "PVE",
    "Contoso TPM",
    "79/6/1",
    "shared VS Code browser",
    "exact retained",
    "target-tenant",
)


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


def expected_published_artifacts(
    configured_artifacts: set[str],
    published_artifacts: dict[str, object],
    configured_core_version: str,
) -> set[str]:
    if "credits" in published_artifacts:
        return configured_artifacts
    published_core_version = published_artifacts.get("core", {}).get("version")
    return LEGACY_ARTIFACT_KEYS if published_core_version != configured_core_version else configured_artifacts


def public_copy_violations(html: str) -> list[str]:
    normalized_html = html.casefold()
    return [
        phrase
        for phrase in PUBLIC_COPY_FORBIDDEN_PHRASES
        if phrase.casefold() in normalized_html
    ]


def validate_html(html: str, manifest: dict[str, object]) -> None:
    forbidden_phrases = public_copy_violations(html)
    if forbidden_phrases:
        fail(f"site/index.html exposes internal release details: {forbidden_phrases}")

    artifacts = manifest.get("artifacts", {})
    if not isinstance(artifacts, dict):
        fail("published release manifest artifacts must be an object")
    release_config = json.loads(RELEASE_CONFIG.read_text(encoding="utf-8"))
    candidate_version = release_config["core"]["version"]
    promoted = artifacts.get("core", {}).get("version") == candidate_version
    required = [
        'id="capabilities"',
        'id="credits"',
        'id="architecture"',
        'id="install"',
        'id="codeapp-download"',
        artifacts["core"]["filename"],
        "downloads/release-manifest.json",
        'id="trust-package"',
        'id="download-package"',
        "Import only what you trust",
        'id="trust-codeapp"',
        'id="download-codeapp"',
        "Review the supported code app",
        "Optional · supported",
        "Download code app ZIP",
        'data-release-version="core"',
        'data-release-version="codeApp"',
        'id="import-command"',
        'wireDownloadGate("trust-package", "download-package")',
        'wireDownloadGate("trust-codeapp", "download-codeapp")',
        "This maintainer-supported code app uses fully supported Microsoft technologies",
        "I understand this is a supported code app",
        "Documented platform limitations apply",
        "Per-user limits are not available",
        "pvConversationInsightsCredits",
        "Fresh install",
        "Upgrade from 2.0.0.5",
        "Upgrade from 1.4.0.15",
        "Credits is unchanged and should not be reimported.",
        "Microsoft Dataverse",
        "Power Platform for Admins V2",
        "HTTP with Microsoft Entra ID",
        "Release manifest and checksums",
        "docs/clean-install.md",
        "docs/operations.md",
        "docs/credit-reporting.md",
        "docs/permissions-and-inventory.md",
    ]
    if promoted:
        required.extend([
            artifacts["credits"]["filename"],
            'id="trust-credits"',
            'id="download-credits"',
            'data-release-version="credits"',
            'wireDownloadGate("trust-credits", "download-credits")',
        ])
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


def validate_packages() -> dict[str, object]:
    if not MANIFEST_PATH.is_file():
        fail(f"missing release manifest: {MANIFEST_PATH.relative_to(ROOT)}")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    schema_version = manifest.get("schemaVersion", 1)
    if schema_version == 1:
        if not FULL_COMMIT_PATTERN.fullmatch(manifest.get("sourceCommit", "")):
            fail("release manifest sourceCommit must be a full 40-character lowercase Git commit SHA")
    elif schema_version != 2:
        fail(f"unsupported release manifest schemaVersion: {schema_version}")
    artifacts = manifest.get("artifacts", {})
    release_config = json.loads(RELEASE_CONFIG.read_text(encoding="utf-8"))
    configured_artifacts = set(release_config)
    expected_artifacts = expected_published_artifacts(
        configured_artifacts,
        artifacts,
        release_config["core"]["version"],
    )
    if set(artifacts) != expected_artifacts:
        fail(
            "published release manifest artifact set does not match its release generation: "
            f"expected={sorted(expected_artifacts)}, actual={sorted(artifacts)}"
        )
    for key, published in artifacts.items():
        if schema_version == 2 and not FULL_COMMIT_PATTERN.fullmatch(
            published.get("sourceCommit", "")
        ):
            fail(f"published {key} sourceCommit must be a full lowercase Git SHA")
        path = SITE / "downloads" / published["filename"]
        if not path.is_file():
            fail(f"missing published {key} package: {path.relative_to(ROOT)}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != published["sha256"]:
            fail(f"published {key} package checksum does not match release manifest")
        with ZipFile(path) as bundle:
            corrupt = bundle.testzip()
            if corrupt:
                fail(f"corrupt file in {path.name}: {corrupt}")
            solution = ET.fromstring(bundle.read("solution.xml"))
        observed = (
            solution.findtext(".//UniqueName"),
            solution.findtext(".//Version"),
            solution.findtext(".//Managed"),
        )
        expected = (published["solutionUniqueName"], published["version"], "1")
        if observed != expected:
            fail(f"published {key} package identity does not match release manifest")
    return manifest


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
    validate_solution_ownership()
    validate_release_evidence()
    manifest = validate_packages()
    validate_preview()
    html = INDEX.read_text(encoding="utf-8")
    validate_html(html, manifest)
    print(
        "PASS: Pages site, published managed packages, release manifest, "
        "trust gates, package components, and local references are valid"
    )


if __name__ == "__main__":
    main()