---
name: linkedin-release
description: "Generate, validate, configure, or publish MCS Transcript Analyzer LinkedIn release announcements. Use when preparing a stable release, drafting a LinkedIn post, setting LinkedIn API credentials, dry-running social publication, or troubleshooting the publish LinkedIn release workflow."
argument-hint: "Provide a stable release version or LinkedIn publication task"
---

# LinkedIn Release Publication

Use the deterministic repository scripts and workflow. Do not compose release claims from memory.

## Prepare and validate

1. Confirm the stable version is present in both `CHANGELOG.md` and
   `site/downloads/release-manifest.json`.
2. Generate the post:

   ```text
   python scripts/generate_linkedin_post.py --version <version>
   ```

3. Verify the post retains shipped capabilities, explicit boundaries, the public Pages link, and
   the GitHub Release link. The generator enforces LinkedIn's 3,000-character limit.
4. Run:

   ```text
   python -m unittest scripts.test_generate_linkedin_post scripts.test_publish_linkedin_post
   ```

## Publish

The `publish LinkedIn release` workflow runs for non-prerelease GitHub Releases. It verifies the
tag against the synchronized manifest, generates copy from the matching changelog section, checks
the public Pages URL, publishes through the LinkedIn Posts API, and records the returned post URN
in a hidden GitHub Release marker.

Use `workflow_dispatch` with `dry_run=true` before enabling a new LinkedIn identity or API version.
Never place an access token in repository files, logs, variables, or generated post content.

## Required GitHub environment

Configure the `linkedin-production` environment with:

- secret `LINKEDIN_ACCESS_TOKEN`;
- variable `LINKEDIN_AUTHOR_URN`, such as `urn:li:person:<id>` or
  `urn:li:organization:<id>`;
- variable `LINKEDIN_API_VERSION`, using an active LinkedIn version in `YYYYMM` format.

The LinkedIn application needs `w_member_social` to post for a person. Organization posting needs
`w_organization_social`, and the authenticated member must hold an eligible LinkedIn Page role for
that organization. Follow the official [Posts API documentation](https://learn.microsoft.com/linkedin/marketing/community-management/shares/posts-api)
for the currently supported API versions and roles. Token issuance, expiration, and LinkedIn
product approval remain external prerequisites; GitHub Actions cannot create or renew those grants
by itself.

If publication fails, correct credentials, permission, author URN, or API version and rerun the
workflow manually. Do not edit the release marker unless LinkedIn confirms no post was created.