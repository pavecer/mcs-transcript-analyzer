---
name: transcript-pii-masking
description: "Mask an exported ESS HR Workday ConversationTranscript JSON file before it leaves a customer security boundary, using the repository's offline PowerShell masker. Use when a customer or support engineer needs to mask, redact, anonymize, or sanitize a conversation transcript, review a masked transcript for residual PII, or check whether transcript masking matches the code app's workday-hr-v1 policy."
---

# Transcript PII Masking

**Audience:** this repository copy is for maintainers and support engineers. The customer-facing,
standalone copy is included at `tools/transcript-pii-masker/skill/SKILL.md`; give customers that
file with the masker package when they want to install the skill in their own VS Code workspace.

Use this workflow whenever someone needs to mask an exported Copilot Studio `ConversationTranscript`
JSON file for the ESS HR Workday agent family before sharing it outside the customer's security
boundary (for example, attaching it to a support ticket). The authoritative tool is
[`tools/transcript-pii-masker`](../../../tools/transcript-pii-masker/), and its policy must stay in
sync with [`codeapp/src/lib/transcriptPrivacy.ts`](../../../codeapp/src/lib/transcriptPrivacy.ts),
which implements the same `workday-hr-v1` rules inside the code app.

If the customer will run the tool themselves, point them to
[`tools/transcript-pii-masker/README.md`](../../../tools/transcript-pii-masker/README.md) — it is
written for them directly and covers getting the tool, execution-policy prerequisites, and running
it. Do not paraphrase that guidance into a chat message; share the README itself with the zip.

Do not write a one-off masking script or hand-edit the transcript. Always run the maintained tool so
fixes and safeguards are applied consistently across every masked export.

## 1. Confirm the input

- The file must be a genuine `ConversationTranscript` export (or an array/object containing one),
  not already-masked output, and not a different agent family's transcript.
- Never mask in place. `-InputPath` and `-OutputPath` must be different files; the tool refuses to
  run otherwise.

## 2. Run the masker

From `tools/transcript-pii-masker/`:

```powershell
.\Mask-ConversationTranscript.ps1 `
  -InputPath <path-to-exported-transcript.json> `
  -OutputPath <path-to-masked-output.json> `
  -AuditReportPath <path-to-masking-report.json> `
  -FailOnResidual
```

`-FailOnResidual` blocks output entirely when a configured detector or harvested value would still
be present in the result. Treat that failure as a real problem to diagnose, not something to bypass
by omitting the switch.

## 3. Validate before trusting the output

Run the synthetic regression suite so a change to PowerShell, .NET regex behavior, or the config
file has not silently reintroduced a known failure mode:

```powershell
.\tests\Test-MaskConversationTranscript.ps1
```

The suite specifically guards against three previously real bugs, so never remove or weaken these
assertions:

- **Over-masking:** short country/language codes (`CAN`, `IND`) or harvested substrings must not
  corrupt unrelated words or GUIDs (for example, turning `canonical` into a masked fragment).
- **Structural corruption:** trace/activity `id`, `nodeId`, `replyToId`, and `topicDisplayName`
  values must survive untouched, since they carry no PII and are needed for diagnosis.
- **Under-masking:** a tenant ID or other `IDENTIFIER`-category value must be masked everywhere it
  recurs, including inside free-text message content, not only in the field it was first seen in.

## 4. Review the masked JSON and the audit report

- Open the masked file and skim message text, `finalized*Data` blocks, and any embedded JSON
  strings for anything that still reads as a real name, email, address, date of birth, or ID.
- Check `residualHighConfidenceMatches` in the audit report; it must be `0` before sharing.
- Rule-based detection cannot identify every person name or context-specific identifier (for
  example, a manager's name mentioned only in freeform generated text, never under a recognized
  field). Human review remains required; do not treat a clean audit report as a guarantee.
- Share only the masked JSON and the audit report. Never share the original transcript or a
  masked file that still fails the residual audit.

## 5. If you find a masking gap

If review or a customer-provided sample surfaces PII that was not masked, or a structural field
that was incorrectly masked:

1. Reproduce the gap as a new fixture in `tests/Test-MaskConversationTranscript.ps1` first.
2. Fix `pii-masker.config.json` (field names, categories, `structuralFields`) and, if the detection
   logic itself needs to change, `Mask-ConversationTranscript.ps1`.
3. Make the equivalent change in `codeapp/src/lib/transcriptPrivacy.ts` and its test file so the
   code app and the offline tool never diverge on what counts as sensitive.
4. Re-run both test suites (`tests/Test-MaskConversationTranscript.ps1` and the code app's Vitest
   suite) before considering the fix complete.

## Boundaries

- This tool processes local files only; it makes no network or Dataverse calls and requires no
  credentials. Do not add telemetry, network access, or Dataverse queries to it.
- Only `tools/transcript-pii-masker` and `codeapp/src/lib/transcriptPrivacy.ts` may define the
  `workday-hr-v1` policy. Do not create a third parallel implementation.
