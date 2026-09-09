---
name: transcript-pii-masking
description: "Mask an exported ESS HR Workday ConversationTranscript JSON file before it leaves a customer security boundary, using the offline PowerShell masker included with this package. Use when masking, redacting, anonymizing, sanitizing, or reviewing a conversation transcript for residual PII."
---

# Transcript PII Masking

Use this skill with the `transcript-pii-masker` folder supplied with it. The masker processes local
files only, requires no repository checkout, network access, modules, or credentials, and supports
Windows PowerShell 5.1 and PowerShell 7+.

## 1. Confirm the input

- Use a genuine ESS HR Workday `ConversationTranscript` JSON export, not an already-masked file.
- Never mask in place. The input and output paths must be different.
- Keep the original transcript inside the approved customer security boundary.

## 2. Run the masker

From the directory containing `Mask-ConversationTranscript.ps1`:

```powershell
.\Mask-ConversationTranscript.ps1 `
  -InputPath <path-to-exported-transcript.json> `
  -OutputPath <path-to-masked-output.json> `
  -AuditReportPath <path-to-masking-report.json> `
  -FailOnResidual
```

`-FailOnResidual` prevents output when a configured detector or harvested sensitive value remains.
Treat that failure as a problem to investigate; do not bypass it by removing the switch.

## 3. Validate before sharing

Run the included regression test from the masker package:

```powershell
.\tests\Test-MaskConversationTranscript.ps1
```

Then review the masked JSON, including message text, `finalized*Data` blocks, and embedded JSON
strings. The audit report must contain `residualHighConfidenceMatches: 0` before sharing.

Rule-based masking cannot identify every person name or context-specific identifier in freeform
text. Human review remains required, even when the audit report is clean.

## 4. What the masker preserves

The masker keeps orchestration and diagnostic structure usable, including activity types, trace
identifiers, node IDs, timestamps, topic names, and correlation fields that are not sensitive.
Sensitive values are replaced with category tokens such as `[MASKED:PERSON]` wherever they recur,
including inside message text and JSON serialized in string properties.

It also detects high-confidence email, phone, address, date-of-birth, bank, financial, identifier,
UK National Insurance, US Social Security, IBAN, UK postcode, and IP-address patterns according to
the package's `workday-hr-v1` policy.

## 5. If masking leaves PII

Do not share the file. Preserve the original and masked files within the customer boundary, record
the field or text that was missed, and contact the support or engineering owner of the masker with
the audit report and a synthetic reproduction that contains no real customer data.

Do not hand-edit the output or create a second masking script. The maintained package must be
updated and retested so future exports receive the same fix.

## Boundaries

- The tool is local-only and makes no telemetry, network, Dataverse, or Workday calls.
- It reduces accidental disclosure risk; it does not guarantee complete anonymization.
- Share only the reviewed masked JSON and audit report, never the original transcript.
