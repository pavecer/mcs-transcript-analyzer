#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHANGELOG = ROOT / "CHANGELOG.md"
DEFAULT_MANIFEST = ROOT / "site" / "downloads" / "release-manifest.json"
LINKEDIN_CHARACTER_LIMIT = 3000
LINKEDIN_MARKETING_LIMIT = 600


def release_version(manifest_path: Path) -> str:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    core = manifest.get("artifacts", {}).get("core")
    if not isinstance(core, dict) or not core.get("version"):
        raise ValueError("Release manifest has no core artifact version")
    return str(core["version"])


def changelog_release(changelog_path: Path, version: str) -> tuple[str, list[str]]:
    text = changelog_path.read_text(encoding="utf-8")
    match = re.search(
        rf"^## {re.escape(version)} - \d{{4}}-\d{{2}}-\d{{2}}\s*$\n(?P<body>.*?)(?=^## |\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise ValueError(f"CHANGELOG.md has no release section for {version}")

    lines = match.group("body").splitlines()
    summary_parts = []
    for line in lines:
        stripped = line.strip()
        if summary_parts and not stripped:
            break
        if stripped:
            summary_parts.append(stripped)
    summary = " ".join(summary_parts)

    bullets = []
    current_bullet = ""
    for line in lines:
        stripped = line.strip()
        if stripped in {"Artifacts:", "Published downloads:"}:
            break
        if stripped.startswith("- "):
            if current_bullet:
                bullets.append(current_bullet)
            current_bullet = stripped
        elif current_bullet and stripped:
            current_bullet = f"{current_bullet} {stripped}"
        elif current_bullet:
            bullets.append(current_bullet)
            current_bullet = ""
    if current_bullet:
        bullets.append(current_bullet)

    if not summary or not bullets:
        raise ValueError(f"Release section for {version} needs a summary and shipped bullets")
    return summary, bullets


def build_post(
    version: str,
    pages_url: str,
) -> str:
    post = "\n".join(
        [
            f"MCS Transcript Analyzer {version} is here.",
            "",
            "Explore Copilot Studio conversation insights across environments, operational "
            "trends, and optional Copilot Credit reporting in the latest managed Power "
            "Platform release.",
            "",
            f"See what's new and get the release: {pages_url.rstrip('/')}/",
            "",
            "#MicrosoftCopilotStudio #PowerPlatform #Dataverse",
        ]
    )
    if len(post) > LINKEDIN_MARKETING_LIMIT:
        raise ValueError(
            f"LinkedIn post is {len(post)} characters; marketing limit is "
            f"{LINKEDIN_MARKETING_LIMIT}"
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
    changelog_release(changelog_path, version)
    return build_post(version, pages_url)


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