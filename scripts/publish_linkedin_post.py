#!/usr/bin/env python3
import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path


LINKEDIN_POSTS_ENDPOINT = "https://api.linkedin.com/rest/posts"


def publish_post(
    commentary: str,
    author_urn: str,
    access_token: str,
    api_version: str,
) -> str:
    payload = {
        "author": author_urn,
        "commentary": commentary,
        "visibility": "PUBLIC",
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    request = urllib.request.Request(
        LINKEDIN_POSTS_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Linkedin-Version": api_version,
            "X-Restli-Protocol-Version": "2.0.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            post_urn = response.headers.get("x-restli-id")
            if response.status != 201 or not post_urn:
                raise RuntimeError(
                    f"LinkedIn returned HTTP {response.status} without x-restli-id"
                )
            return post_urn
    except urllib.error.HTTPError as error:
        response_body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"LinkedIn returned HTTP {error.code}: {response_body}"
        ) from error


def required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Required environment variable {name} is not configured")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish a generated LinkedIn release post")
    parser.add_argument("--post-file", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    commentary = args.post_file.read_text(encoding="utf-8").strip()
    if args.dry_run:
        print(commentary)
        return

    post_urn = publish_post(
        commentary,
        required_environment("LINKEDIN_AUTHOR_URN"),
        required_environment("LINKEDIN_ACCESS_TOKEN"),
        required_environment("LINKEDIN_API_VERSION"),
    )
    print(post_urn)


if __name__ == "__main__":
    main()