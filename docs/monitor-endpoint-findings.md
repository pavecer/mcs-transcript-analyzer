# Dual Endpoint Playbook: Monitor and Dataverse v9.1

## Purpose

This playbook documents and operationalizes two transcript retrieval paths that can behave differently:

1. Monitor service path
2. Dataverse v9.1 `conversationtranscripts` path

The goal is to test both, compare outcomes, and explain why one can return data while the other appears empty.

## Endpoints Under Validation

## A) Monitor service path (observed in HAR)

1. `GET {gateway}/api/botmanagement/v1/transcript/sessionwindows?startTime={ISO}&endTime={ISO}&isV2=true`
2. `GET {gateway}/api/botmanagement/v1/transcript?startTime={ISO}&endTime={ISO}&isV2=true`

Observed response format:

- `sessionwindows`: JSON array with date window objects.
- `transcript`: CSV with columns:
  - SessionId
  - StartDateTime(UTC)
  - SessionOutcome
  - OutcomeReason
  - IsResolvedImplied
  - Turns
  - ChatTranscript
  - InitialUserMessage
  - TopicName
  - TopicId
  - Channel
  - CSAT
  - Comments

## B) Dataverse path

`GET {organizationUrl}/api/data/v9.1/conversationtranscripts({conversationtranscriptId})?$select=conversationtranscriptid,metadata,content,createdon,modifiedon`

Also recommended for testing list availability:

`GET {organizationUrl}/api/data/v9.1/conversationtranscripts?$select=conversationtranscriptid,createdon,modifiedon&$orderby=createdon desc&$top=5`

## Why the Path Is Not Easy

The biggest complexity is ID correlation:

1. Monitor returns `SessionId` as an opaque composite value.
2. Dataverse endpoint requires exact `conversationtranscriptid`.
3. `/debug conversationid` may not equal `conversationtranscriptid` in all scenarios.
4. Materialization timing and security context can differ between stores.

Result: You can see sessions in Monitor while direct Dataverse-by-ID lookup returns not found.

## Practical Test Procedure

Use the dual probe script:

`python3 scripts/transcript_insights/probe_dual_endpoints.py --config config/transcript_solution_config.sample.json --lookback-days 2 --output output/transcript_insights/dual_endpoint_probe_report.json`

What this proves:

1. Monitor endpoint availability and payload contract.
2. Dataverse endpoint availability and row presence.
3. Whether specific `conversationtranscriptid` returns full `metadata/content`.

Then run correlation attempt:

`python3 scripts/transcript_insights/correlate_monitor_to_dataverse.py --config config/transcript_solution_config.sample.json --normalized output/transcript_insights/normalized_sessions.json --output output/transcript_insights/correlation_report.json`

What this proves:

1. How many monitor sessions contain GUID-like candidates.
2. How many candidate GUIDs actually resolve in Dataverse v9.1.
3. Exact mismatch rate for customer troubleshooting evidence.

## Solution Pattern for Both Endpoints

The delivered solution uses both sources deliberately:

1. Monitor endpoint as primary operational ingest source.
2. Dataverse v9.1 as enrichment and deep content source when row is resolvable.
3. Custom Dataverse analytics tables as unified reporting store.

This avoids single-source dependency and gives stable troubleshooting visibility.

## Recommended Data Contract in Unified Store

For each transcript session record:

1. `monitor_session_id` (immutable source key)
2. `conversationtranscriptid` (nullable enrichment key)
3. `correlation_status` (`unmatched`, `heuristic`, `exact`)
4. `monitor_payload_version`
5. `dataverse_payload_version`
6. `chat_transcript_raw`
7. `parsed_turns_json`

## Expected Failure Modes and What They Mean

1. Monitor 200, Dataverse list 200, Dataverse by ID 404:
   - ID mismatch or not materialized row.
2. Monitor 200, Dataverse list empty:
   - pipeline lag, role visibility, or environment mismatch.
3. Monitor 401/403:
   - missing scope/permissions on service endpoint.
4. Dataverse 401/403:
   - missing API permissions or role assignment.

## Customer Messaging

Use this statement in customer communication:

"Transcript retrieval in Copilot Studio can involve multiple storage/read paths. In our tests, Monitor endpoints returned valid session transcript exports while Dataverse v9.1 by-ID retrieval may require a separate correlation and lifecycle timing model. We implemented a dual-endpoint ingestion and analysis approach to ensure reliable forensic visibility."
