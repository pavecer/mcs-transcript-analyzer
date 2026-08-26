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

3. Verify the post is a short awareness announcement: release name, one audience-focused value
   statement, one public Pages call to action, and a small relevant hashtag set. Do not copy package
   inventories, validation evidence, checksums, setup instructions, or detailed product boundaries
   into LinkedIn; those remain on the public site and GitHub Release. The generator enforces a
   600-character marketing limit, well below LinkedIn's technical 3,000-character limit.
4. Run:

   ```text
   python -m unittest scripts.test_generate_linkedin_post scripts.test_publish_linkedin_post
   ```

## Publish

The `publish LinkedIn release` workflow runs for non-prerelease GitHub Releases. It verifies the
tag against the synchronized manifest, generates copy from the matching changelog section, checks
the public Pages URL, publishes through the LinkedIn Posts API, and records the returned post URN
in a hidden GitHub Release marker. If any required LinkedIn setting is absent, an automatic stable-
release run still generates and validates the copy, emits a GitHub notice, and skips the public
Pages request, LinkedIn publication, and release marker. A successful workflow without that marker
is not evidence that a LinkedIn post occurred.

Use `workflow_dispatch` with `dry_run=true` before enabling a new LinkedIn identity or API version.
Dry runs invoke the publisher with `--dry-run` and require no LinkedIn credentials. Never place an
access token in repository files, logs, variables, or generated post content.

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

After an unconfigured stable-release run, configure all three values, manually run the workflow for
the same tag with `dry_run=true`, review the generated copy, and only then make an intentional manual
run with `dry_run=false`. If publication fails, correct credentials, permission, author URN, or API
version and repeat that recovery sequence. Never claim publication without the hidden release marker.
Do not edit the release marker unless LinkedIn confirms no post was created.

To shorten or correct an existing announcement, dispatch the workflow from the default branch with
the stable tag and `update_post_urn` set to the exact URN in that release's hidden marker. The
workflow refuses any mismatch, updates commentary in place, creates no second post, and leaves the
original publication marker unchanged. Use `dry_run=true` first to review the corrected copy.