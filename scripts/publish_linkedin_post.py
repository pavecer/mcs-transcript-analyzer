#!/usr/bin/env python3
import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


LINKEDIN_POSTS_ENDPOINT = "https://api.linkedin.com/rest/posts"


def linkedin_headers(access_token: str, api_version: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Linkedin-Version": api_version,
        "X-Restli-Protocol-Version": "2.0.0",
    }


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
        headers=linkedin_headers(access_token, api_version),
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


def update_post(
    commentary: str,
    post_urn: str,
    access_token: str,
    api_version: str,
) -> str:
    encoded_post_urn = urllib.parse.quote(post_urn, safe="")
    payload = {"patch": {"$set": {"commentary": commentary}}}
    headers = linkedin_headers(access_token, api_version)
    headers["X-RestLi-Method"] = "PARTIAL_UPDATE"
    request = urllib.request.Request(
        f"{LINKEDIN_POSTS_ENDPOINT}/{encoded_post_urn}",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status != 204:
                raise RuntimeError(f"LinkedIn returned HTTP {response.status} during update")
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
    parser.add_argument("--post-urn", help="Update the recorded post instead of creating one")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    commentary = args.post_file.read_text(encoding="utf-8").strip()
    if args.dry_run:
        print(commentary)
        return

    access_token = required_environment("LINKEDIN_ACCESS_TOKEN")
    api_version = required_environment("LINKEDIN_API_VERSION")
    if args.post_urn:
        post_urn = update_post(commentary, args.post_urn, access_token, api_version)
    else:
        post_urn = publish_post(
            commentary,
            required_environment("LINKEDIN_AUTHOR_URN"),
            access_token,
            api_version,
        )
    print(post_urn)


if __name__ == "__main__":
    main()