#!/usr/bin/env python3
"""Build a managed issue candidate from the latest managed package and source workflow fixes."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_FILES = (
    "PVCICollectCreditGovernancescheduled-1AFEDF5C-1396-F111-8076-7CED8D95B46E.json",
    "PVCIApplyCreditGovernanceRequestsscheduled-C8D754C8-1896-F111-8076-7CED8D95B46E.json",
)


def run_pac(*arguments: str) -> None:
    subprocess.run(["pac", *arguments], check=True, cwd=ROOT)


def patch_version(solution_xml: Path, version: str) -> None:
    tree = ET.parse(solution_xml)
    version_node = tree.getroot().find(".//Version")
    if version_node is None:
        raise RuntimeError(f"Solution version is missing from {solution_xml}")
    version_node.text = version
    tree.write(solution_xml, encoding="utf-8", xml_declaration=True)


def build_candidate(base_package: Path, output_package: Path, version: str) -> None:
    if not base_package.is_file():
        raise FileNotFoundError(base_package)
    output_package.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pvci-candidate-") as temporary:
        staging = Path(temporary) / "solution"
        run_pac(
            "solution",
            "unpack",
            "--zipfile",
            str(base_package),
            "--folder",
            str(staging),
            "--packagetype",
            "Managed",
        )
        source_workflows = ROOT / "solution" / "pvConversationInsights" / "src" / "Workflows"
        target_workflows = staging / "Workflows"
        for filename in WORKFLOW_FILES:
            shutil.copy2(source_workflows / filename, target_workflows / filename)
        patch_version(staging / "Other" / "Solution.xml", version)
        run_pac(
            "solution",
            "pack",
            "--zipfile",
            str(output_package),
            "--folder",
            str(staging),
            "--packagetype",
            "Managed",
            "--clobber",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    build_candidate(args.base_package, args.output, args.version)
    print(f"Built {args.output} ({args.version})")


if __name__ == "__main__":
    main()
