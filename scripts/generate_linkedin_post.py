#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHANGELOG = ROOT / "CHANGELOG.md"
DEFAULT_MANIFEST = ROOT / "site" / "downloads" / "release-manifest.json"
LINKEDIN_CHARACTER_LIMIT = 3000


def release_version(manifest_path: Path) -> str:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    versions = {artifact["version"] for artifact in manifest["artifacts"].values()}
    if len(versions) != 1:
        raise ValueError(f"Release manifest versions are not synchronized: {sorted(versions)}")
    return versions.pop()


def changelog_release(changelog_path: Path, version: str) -> tuple[str, list[str]]:
    text = changelog_path.read_text(encoding="utf-8")
    match = re.search(
        rf"^## {re.escape(version)} - \d{{4}}-\d{{2}}-\d{{2}}\s*$\n(?P<body>.*?)(?=^## |\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise ValueError(f"CHANGELOG.md has no release section for {version}")

    lines = [line.strip() for line in match.group("body").splitlines()]
    summary = next((line for line in lines if line and not line.startswith("- ")), "")
    bullets = []
    for line in lines:
        if line == "Artifacts:":
            break
        if line.startswith("- "):
            bullets.append(line)

    if not summary or not bullets:
        raise ValueError(f"Release section for {version} needs a summary and shipped bullets")
    return summary, bullets


def build_post(
    version: str,
    summary: str,
    bullets: list[str],
    repository: str,
    pages_url: str,
) -> str:
    release_url = f"https://github.com/{repository}/releases/tag/v{version}"
    post = "\n".join(
        [
            f"MCS Transcript Analyzer {version} is now available.",
            "",
            summary,
            "",
            "What's included:",
            *bullets,
            "",
            f"Explore the solution and download the managed packages: {pages_url.rstrip('/')}/",
            f"Release notes and checksums: {release_url}",
            "",
            "#MicrosoftCopilotStudio #PowerPlatform #Dataverse #PowerAutomate",
        ]
    )
    if len(post) > LINKEDIN_CHARACTER_LIMIT:
        raise ValueError(
            f"LinkedIn post is {len(post)} characters; limit is {LINKEDIN_CHARACTER_LIMIT}"
        )
    return post


def generate_post(
    version: str,
    repository: str,
    pages_url: str,
    changelog_path: Path = DEFAULT_CHANGELOG,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> str:
    current_version = release_version(manifest_path)
    if version != current_version:
        raise ValueError(
            f"Requested version {version} does not match release manifest {current_version}"
        )
    summary, bullets = changelog_release(changelog_path, version)
    return build_post(version, summary, bullets, repository, pages_url)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a LinkedIn post for a stable release")
    parser.add_argument("--version", help="Stable four-part release version")
    parser.add_argument("--repository", default="pavecer/mcs-transcript-analyzer")
    parser.add_argument(
        "--pages-url",
        default="https://pavecer.github.io/mcs-transcript-analyzer",
    )
    parser.add_argument("--output", type=Path, help="Write the post to this file")
    args = parser.parse_args()

    version = args.version or release_version(DEFAULT_MANIFEST)
    post = generate_post(version, args.repository, args.pages_url)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{post}\n", encoding="utf-8")
    else:
        print(post)


if __name__ == "__main__":
    main()