# Conversation Transcript PII Masker

An offline, dependency-free PowerShell utility for masking Copilot Studio
`ConversationTranscript` JSON before it leaves a customer security boundary. It is intended for
troubleshooting orchestration while hiding Workday and end-user data.

The default configuration implements the code app's `workday-hr-v1` policy. It preserves JSON
property names, array order, Bot Framework activity types, tool and topic names, orchestration
status fields, timestamps, and correlation identifiers that are not themselves sensitive fields.
Sensitive values are replaced with category tokens such as `[MASKED:PERSON]`.

## Requirements

- Windows PowerShell 5.1 or PowerShell 7+
- No modules, package installation, network access, or Dataverse credentials
- A transcript already exported as JSON

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
