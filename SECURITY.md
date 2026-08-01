# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Use [GitHub private vulnerability reporting](https://github.com/pavecer/mcs-transcript-analyzer/security/advisories/new),
or contact the maintainer directly. Expect an acknowledgement within a few working days.

When reporting, describe the impact and how to reproduce it — but **never include real
transcript content, user identifiers, tenant or environment GUIDs, or tokens**. Redacted or
synthetic examples only.

## Data this project handles

This tool reads and stores **conversation transcripts**, which routinely contain personal data:

- User-authored message text, which may include anything a user typed
- Entra object ids, user principal names and display names
- Tool and connector payloads — in the ESS scenario, ServiceNow ticket contents
- Full Power Automate action inputs and outputs

Treat every `pvci_*` table as containing personal data.

## Operating it safely

1. **Restrict table privileges.** Grant read on the `pvci_*` tables only to people who need to
   investigate conversations. Dataverse security roles apply to both apps automatically.
2. **Set a retention policy.** The sync copies transcripts out of Copilot Studio's own
   retention window, so data will otherwise persist indefinitely. Decide how long you need it.
3. **Enable auditing** on the transcript tables if your compliance regime requires access logs.
4. **Never commit HAR captures.** They contain conversation text and user identifiers.
   `evidence/` and `*.har` are gitignored — keep it that way.
5. **Use a service principal for scheduled runs.** The connection reference behind the sync
   flow runs as its owner; a departing employee's account will break it and over-grants access.
6. **Review before sharing.** Screenshots of either app can expose real conversations.

## Credentials

The tooling never stores long-lived secrets:

- Tokens come from Azure CLI, an MSAL disk cache (`.msal_token_cache.json`, chmod 600,
  gitignored), or device-code flow — in that order.
- No client secrets appear anywhere in the repository.
- `plugin/plugin.snk` is a .NET **strong-name key**, not a code-signing certificate. Per
  Microsoft's guidance a strong name is not a security boundary, so it is committed to keep
  builds reproducible. Generate your own with `pac plugin init` if you prefer.

## Scope

This is a community project with no affiliation to Microsoft, provided under the MIT license
with no warranty. It relies partly on **observed rather than documented** platform behaviour
(see [docs/api-reference.md](docs/api-reference.md)); Microsoft may change it without notice.
