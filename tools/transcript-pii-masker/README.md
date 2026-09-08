# Conversation Transcript PII Masker

An offline, dependency-free PowerShell utility for masking Copilot Studio
`ConversationTranscript` JSON before it leaves a customer security boundary. It is intended for
troubleshooting orchestration while hiding Workday and end-user data.

The default configuration implements the code app's `workday-hr-v1` policy. It preserves JSON
property names, array order, Bot Framework activity types, tool and topic names, orchestration
status fields, timestamps, and correlation identifiers that are not themselves sensitive fields.
Sensitive values are replaced with category tokens such as `[MASKED:PERSON]`.

This matches the masking rules in `codeapp/src/lib/transcriptPrivacy.ts`. When that file changes
a category, field list, or safeguard, update `pii-masker.config.json` and this script to match, so
both implementations enforce the same `workday-hr-v1` policy.

## Get the tool

This folder is self-contained: `Mask-ConversationTranscript.ps1`, `pii-masker.config.json`,
`README.md`, and `tests/` are everything required. It has no dependency on the rest of this
repository and no build step.

To hand it to a customer or attach it to a support ticket, zip this folder and share only the zip:

```powershell
Compress-Archive -Path .\tools\transcript-pii-masker\* -DestinationPath .\transcript-pii-masker.zip
```

Share the zip (or the extracted folder) directly. Do not share the rest of this repository, and do
not ask the customer to clone it.

## Requirements

- Windows PowerShell 5.1 or PowerShell 7+
- No modules, package installation, network access, or Dataverse credentials
- A transcript already exported as JSON. Ask your Copilot Studio administrator or Microsoft support
  contact for the `ConversationTranscript` export; this tool masks an existing export, it does not
  produce one.

## Before you run it

Files extracted from a downloaded zip are often marked by Windows as coming from the internet,
which blocks PowerShell from running them. After extracting the zip, unblock every file once:

```powershell
Get-ChildItem -Path .\transcript-pii-masker -Recurse | Unblock-File
```

If your organization's PowerShell execution policy still refuses to run the script
(`... cannot be loaded because running scripts is disabled on this system`), run it with a
process-scoped bypass instead of changing the system-wide policy:

```powershell
powershell -ExecutionPolicy Bypass -File .\Mask-ConversationTranscript.ps1 -InputPath ... -OutputPath ...
```

`-ExecutionPolicy Bypass` on the command line only affects that one process; it does not change any
persistent setting. If your organization's policy blocks even that, ask your IT administrator to
approve running this specific, reviewable script rather than disabling execution policy generally.

## Run

From this directory:

```powershell
.\Mask-ConversationTranscript.ps1 `
  -InputPath .\conversationtranscript.json `
  -OutputPath .\conversationtranscript.masked.json `
  -AuditReportPath .\conversationtranscript.masking-report.json `
  -FailOnResidual
```

The source file is never modified. Existing output files are refused unless `-Force` is specified.
Writes use a temporary file and an atomic rename.

## Detection model

The script performs two passes:

1. It finds values under configured sensitive fields such as `employeeId`, `fullName`,
   `aadObjectId`, `dateOfBirth`, address, bank, compensation, and HR fields.
2. It replaces those values everywhere they recur, including message text and JSON serialized
   inside string properties. It also masks high-confidence email, UK National Insurance number,
   US Social Security number, IBAN, phone, UK postcode, and IP-address patterns.

Two safeguards keep this from over-masking or corrupting the transcript's own structure:

- **Word-bounded replacement.** A harvested value is only replaced where it appears as a whole
  word or token, never as a fragment inside an unrelated word, GUID, or identifier. Without this,
  a harvested value such as `cane` (from a 3-letter Workday country code) would corrupt words like
  `canonical` or GUIDs that happen to contain the same characters.
- **Minimum harvest length.** Values shorter than 5 characters are only harvested for reuse
  elsewhere when they contain a digit, or when they come from a category that is not
  `WORKDAY_DATA`, `HR_DATA`, or `ADDRESS`. This keeps short country/language codes (`CAN`, `IND`)
  from being masked everywhere they appear as a substring, while still catching short person names.
- **Structural field preservation.** Fields listed in `structuralFields` (trace/activity `id`,
  `nodeId`, `stepId`, `topicDisplayName`, timestamps, enum-like state fields, and similar) are never
  passed through the free-text masking pass unless they sit beneath a recognized sensitive field.
  This keeps diagnostic identifiers and topic names intact for troubleshooting.

The tokens intentionally match the category-only values used by the code app; they cannot be used
to recover or correlate source values. The audit report identifies `workday-hr-v1` and contains
counts only. It never contains source values.

Field names are normalized by removing punctuation and casing, matching the code app. A recognized
Workday response field masks every scalar below it, including fields not otherwise known to the
policy. Edit `pii-masker.config.json` only when a customer-specific policy extension is required;
doing so means the output no longer represents the unmodified `workday-hr-v1` rules.

## Validate before sharing

Run the included synthetic test:

```powershell
.\tests\Test-MaskConversationTranscript.ps1
```

Then review the masked JSON inside the customer environment. `-FailOnResidual` blocks output when a
configured detector or harvested value remains, but rule-based detection cannot identify every
person name or context-specific identifier.

For environments that allow Python or containers and require multilingual named-entity
recognition, [Presidio](https://presidio.dataprivacystack.org/) is a more capable alternative. It
also explicitly does not guarantee detection of all sensitive information, so human review and
data-loss-prevention controls remain necessary.

## Scope and security boundary

- This utility processes local files only and performs no telemetry or network calls.
- It does not query Dataverse or require access to the Workday extension.
- It applies masking to any supplied JSON; the caller must verify that the transcript is from the
  intended ESS HR/Workday session.
- It reduces accidental disclosure risk; it does not claim complete anonymization.
- Keep the original transcript and review process within approved customer controls.
- Share only the masked JSON after customer review, never the original.
