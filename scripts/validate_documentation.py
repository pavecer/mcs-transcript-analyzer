#!/usr/bin/env python3
"""Validate release documentation coverage against shipped product behavior."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config" / "documentation-contract.json"
RELEASE_CONFIG_PATH = ROOT / "config" / "release-packages.json"
SOLUTION_DEFINITION_PATH = ROOT / "solution" / "pvConversationInsights" / "solution-definition.json"
RESOURCE_NAME_PATTERN = re.compile(
    r"--resource-name(?:=|\s+)(?:\"([^\"]+)\"|'([^']+)'|([A-Za-z0-9_.-]+))"
)


class DocumentationFacts(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def fail(messages: list[str]) -> None:
    for message in messages:
        print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def product_digest(paths: list[str]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(paths):
        path = ROOT / relative
        if not path.is_file():
            raise FileNotFoundError(relative)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def discover_surfaces() -> set[str]:
    candidates = {
        ROOT / "README.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / ".github" / "pull_request_template.md",
        *(ROOT / "docs").glob("*.md"),
        *(ROOT / "site").glob("*.md"),
        *(ROOT / "site").glob("*.html"),
        *(ROOT / "scripts").glob("**/README.md"),
        *(ROOT / ".github" / "skills").glob("*/SKILL.md"),
        *(ROOT / ".github" / "workflows").glob("*.yml"),
        *(ROOT / ".github" / "instructions").glob("**/*.md"),
        *(ROOT / ".github" / "ISSUE_TEMPLATE").glob("**/*.yml"),
    }
    return {path.relative_to(ROOT).as_posix() for path in candidates if path.is_file()}


def release_facts() -> dict[str, Any]:
    release = load_json(RELEASE_CONFIG_PATH)
    definition = load_json(SOLUTION_DEFINITION_PATH)
    return DocumentationFacts({
        "version": release["core"]["version"],
        "customTableCount": len(definition["tables"]),
        "roleCount": len(definition["securityRoles"]),
        "workflowCount": len(release["core"]["requiredWorkflows"]),
        "codeAppDependencyCount": len(release["codeApp"]["requiredCoreTables"]),
    })


def validate(contract: dict[str, Any]) -> None:
    errors: list[str] = []
    facts = release_facts()
    product_inputs = contract.get("productInputs", [])
    indexed = set(contract.get("indexedSurfaces", []))

    try:
        current_digest = product_digest(product_inputs)
    except FileNotFoundError as exc:
        errors.append(f"documentation product input is missing: {exc}")
        current_digest = ""
    if contract.get("productSourceDigest") != current_digest:
        errors.append(
            "credit product inputs changed without documentation review; update the documented surfaces, "
            "then set productSourceDigest to the value from --print-digest"
        )

    discovered = discover_surfaces()
    unindexed = sorted(discovered - indexed)
    if unindexed:
        errors.append(f"credit/release documentation surfaces are not indexed: {unindexed}")
    missing_indexed = sorted(relative for relative in indexed if not (ROOT / relative).is_file())
    if missing_indexed:
        errors.append(f"indexed documentation surfaces are missing: {missing_indexed}")

    for relative, templates in contract.get("surfaceCoverage", {}).items():
        path = ROOT / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        expected = [template.format_map(facts) for template in templates]
        missing = [value for value in expected if value not in text]
        if missing:
            errors.append(f"{relative} is missing required release documentation: {missing}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    configured_data_sources = {
        next(value for value in match.groups() if value)
        for match in RESOURCE_NAME_PATTERN.finditer(readme)
    }
    missing_data_sources = [
        table
        for table in load_json(RELEASE_CONFIG_PATH)["codeApp"]["requiredCoreTables"]
        if table not in configured_data_sources
    ]
    if missing_data_sources:
        errors.append(f"README code-app setup is missing Dataverse data sources: {missing_data_sources}")

    if errors:
        fail(errors)
    print(
        "PASS: release documentation contract, indexed surfaces, product digest, component counts, "
        "Copilot Credit coverage, and code-app setup are synchronized"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print-digest", action="store_true", help="Print the current product-source digest")
    parser.add_argument("--list-surfaces", action="store_true", help="Print discovered release documentation surfaces")
    args = parser.parse_args()
    contract = load_json(CONTRACT_PATH)
    if args.print_digest:
        print(product_digest(contract["productInputs"]))
        return
    if args.list_surfaces:
        print("\n".join(sorted(discover_surfaces())))
        return
    validate(contract)


if __name__ == "__main__":
    main()