#!/usr/bin/env python3
"""Collect transcripts from readable source environments into one collector Dataverse.

This is the first central-collector slice. It deliberately keeps source reads and collector
writes on separate Dataverse clients, uses a composite transcript key, and records one watermark
per source environment. Flow-run correlation remains source-local for now.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dv_token import get_token, get_token_from_config  # noqa: E402
from sync_transcripts import (  # noqa: E402
    Dv,
    IDENTITY,
    SESSIONS,
    SYNCSTATE,
    TURNS,
    environment_payload,
    iso,
    jdump,
    parse_transcript,
    resolve_user,
    s1000,
)


def composite_transcript_id(tenant_id: str, environment_id: str, transcript_id: str) -> str:
    """Return the stable cross-organization key stored in pvci_transcriptid."""
    return f"{tenant_id}:{environment_id}:{transcript_id}".lower()


def source_is_enabled(source: dict[str, Any]) -> bool:
    return bool(source.get("enabled")) and source.get("status") in {
        "readable_with_rows",
        "readable_empty",
    }


def source_since(collector: Dv, source_key: str) -> str | None:
    escaped = source_key.replace("'", "''")
    rows = collector.get_all(
        f"{SYNCSTATE}?$select=pvci_lastsyncedcreatedon&$filter=pvci_name eq '{escaped}'&$top=1"
    )
    return rows[0].get("pvci_lastsyncedcreatedon") if rows else None


def find_record(collector: Dv, entity_set: str, field: str, value: str, select: str) -> dict[str, Any] | None:
    escaped = value.replace("'", "''")
    body = collector.get(
        f"{entity_set}?$select={select}&$filter={field} eq '{escaped}'&$top=1"
    )
    values = body.get("value", [])
    return values[0] if values else None


def build_session_payload(
    parsed: dict[str, Any],
    source_ctx: dict[str, str],
    composite_id: str,
    user: dict[str, Any] | None,
) -> dict[str, Any]:
    activities_json, truncated_a = jdump(parsed["activities"])
    conversation_json, truncated_c = jdump(parsed["conversation"])
    plan_json, _ = jdump(parsed["plan_events"])
    metadata_json, _ = jdump(parsed["metadata"])
    tools_json, _ = jdump(parsed["tool_calls"])
    knowledge_json, _ = jdump(parsed["knowledge_calls"])
    display = (user or {}).get("fullname") or (parsed["user_aad"] or "unknown")[:8]
    name = f"{display} · {parsed['channel'] or '?'} · {iso(parsed['start']) or parsed['created_on']}"
    payload: dict[str, Any] = {
        "pvci_name": s1000(name),
        "pvci_transcriptid": s1000(composite_id),
        "pvci_botid": s1000(parsed["bot_id"]),
        "pvci_botname": s1000(parsed["bot_name"]),
        "pvci_topicname": s1000(parsed["topic_name"]),
        "pvci_topicid": s1000(parsed["topic_id"]),
        "pvci_tenantid": s1000(parsed["tenant_id"] or source_ctx["tenant_id"]),
        **environment_payload(source_ctx),
        "pvci_useraadobjectid": s1000(parsed["user_aad"]),
        "pvci_userupn": s1000((user or {}).get("domainname")),
        "pvci_userdisplayname": s1000((user or {}).get("fullname")),
        "pvci_channel": s1000(parsed["channel"]),
        "pvci_startdatetimeutc": iso(parsed["start"]),
        "pvci_enddatetimeutc": iso(parsed["end"]),
        "pvci_durationseconds": parsed["duration_s"],
        "pvci_activitycount": parsed["activity_count"],
        "pvci_messagecount": parsed["message_count"],
        "pvci_eventcount": parsed["event_count"],
        "pvci_userturncount": parsed["user_turns"],
        "pvci_agentturncount": parsed["agent_turns"],
        "pvci_lastagentmessage": parsed["last_agent_message"],
        "pvci_istestmode": bool(parsed["test_mode"]),
        "pvci_multiuseranomaly": bool(parsed["multi_user"]),
        "pvci_firstresponsems": parsed["first_response_ms"],
        "pvci_avgresponsems": parsed["avg_response_ms"],
        "pvci_maxresponsems": parsed["max_response_ms"],
        "pvci_toolcallcount": parsed["tool_call_count"],
        "pvci_toolerrorcount": parsed["tool_error_count"],
        "pvci_tooltotalms": parsed["tool_total_ms"],
        "pvci_maxtoolms": parsed["max_tool_ms"],
        "pvci_toolcallsjson": tools_json,
        "pvci_knowledgecallcount": parsed["knowledge_call_count"],
        "pvci_knowledgesourcecount": parsed["knowledge_source_count"],
        "pvci_knowledgefailurecount": parsed["knowledge_failure_count"],
        "pvci_knowledgecallsjson": knowledge_json,
        "pvci_flowruncount": 0,
        "pvci_flowrunfailurecount": 0,
        "pvci_sessionoutcome": s1000(parsed["session_outcome"]),
        "pvci_outcomereason": s1000(parsed["outcome_reason"]),
        "pvci_usererrorcount": parsed["user_error_count"],
        "pvci_primaryerrorcode": s1000(parsed["primary_error_code"]),
        "pvci_primaryerrormessage": parsed["primary_error_message"],
        "pvci_primaryerrortopic": s1000(parsed["primary_error_topic"]),
        "pvci_errorcategory": s1000(parsed["error_category"]),
        "pvci_isresolvedimplied": s1000(
            str(parsed["implied_success"]).lower() if parsed["implied_success"] is not None else None
        ),
        "pvci_turncount": parsed["session_turn_count"],
        "pvci_planeventsjson": plan_json,
        "pvci_activitiesjson": activities_json,
        "pvci_conversationjson": conversation_json,
        "pvci_metadatajson": metadata_json,
        "pvci_payloadtruncated": bool(truncated_a or truncated_c),
        "pvci_transcriptcreatedon": parsed["created_on"],
        "pvci_ingestedon": iso(datetime.now(timezone.utc)),
        "pvci_correlationstatus": "exact" if user else ("heuristic" if parsed["user_aad"] else "unmatched"),
    }
    if user:
        payload["pvci_UserId@odata.bind"] = f"/systemusers({user['systemuserid']})"
    return {key: value for key, value in payload.items() if value is not None}


def build_turn_payload(activity: dict[str, Any], index: int, session_id: str, composite_id: str) -> dict[str, Any]:
    sender = activity.get("from") or {}
    role = sender.get("role")
    speaker = "user" if role == 1 else "agent"
    payload: dict[str, Any] = {
        "pvci_name": s1000(f"{index:04d} {speaker} {activity.get('type') or '?'}"),
        "pvci_transcriptid": s1000(composite_id),
        "pvci_turnindex": index,
        "pvci_activitytype": s1000(activity.get("type")),
        "pvci_speaker": s1000(speaker),
        "pvci_role": role if isinstance(role, int) else None,
        "pvci_aadobjectid": s1000(sender.get("aadObjectId")),
        "pvci_eventname": s1000(activity.get("name") or activity.get("valueType")),
        "pvci_channelid": s1000(activity.get("channelId")),
        "pvci_timestamputc": iso(datetime.fromtimestamp(int(activity["timestamp"]), tz=timezone.utc))
        if str(activity.get("timestamp", "")).isdigit() else None,
        "pvci_SessionId@odata.bind": f"/{SESSIONS}({session_id})",
    }
    if activity.get("value") is not None:
        payload["pvci_valuejson"] = jdump(activity["value"])[0][:100_000]
    return {key: value for key, value in payload.items() if value is not None}


def import_one(
    source: Dv,
    collector: Dv,
    row: dict[str, Any],
    source_ctx: dict[str, str],
    include_traces: bool,
    reprocess: bool,
    dry_run: bool,
) -> tuple[str, int]:
    parsed = parse_transcript(row)
    composite_id = composite_transcript_id(
        source_ctx["tenant_id"], source_ctx["environment_id"], parsed["transcript_id"]
    )
    existing = find_record(collector, SESSIONS, "pvci_transcriptid", composite_id, "pvci_transcriptsessionid")
    if existing and not reprocess:
        return "skipped", 0
    user_cache: dict[str, dict[str, Any] | None] = {}
    user = resolve_user(collector, parsed["user_aad"], user_cache)
    payload = build_session_payload(parsed, source_ctx, composite_id, user)
    if dry_run:
        return "would_update" if existing else "would_create", len(parsed["activities"])

    if existing:
        session_id = existing["pvci_transcriptsessionid"]
        collector.patch(SESSIONS, session_id, payload)
        stale = collector.get_all(
            f"{TURNS}?$select=pvci_transcriptturnid&$filter=pvci_transcriptid eq '{composite_id}'"
        )
    else:
        session_id = collector.post(SESSIONS, payload)
        stale = []

    index = 0
    for activity in parsed["activities"]:
        value = activity.get("value")
        is_user_error_trace = (
            activity.get("valueType") == "ErrorTraceData"
            and isinstance(value, dict)
            and value.get("isUserError") is True
        )
        if not include_traces and not is_user_error_trace and (
            activity.get("type") in {"trace"} or activity.get("name") == "DialogTracing"
        ):
            continue
        collector.post(TURNS, build_turn_payload(activity, index, session_id, composite_id))
        index += 1
    for turn in stale:
        collector.delete(TURNS, turn["pvci_transcriptturnid"])
    return "updated" if existing else "created", index


def collect(args: argparse.Namespace) -> dict[str, Any]:
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    registry = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    collector_token, collector_url = get_token_from_config(args.config)
    collector = Dv(f"{collector_url}/api/data/v9.1", collector_token)
    results: list[dict[str, Any]] = []

    for source in registry.get("sources", []):
        if not source_is_enabled(source):
            continue
        source_name = f"central:{source['environmentId']}"
        since = args.since or (None if args.full else source_since(collector, source_name))
        source_ctx = {
            "source": "dataverse_v9.1",
            "tenant_id": registry["tenantId"],
            "environment_id": source["environmentId"],
            "environment_name": source["environmentName"],
            "org": source["dataverseUrl"].replace("https://", ""),
        }
        token = get_token(config["tenantId"], config["oauth"]["clientId"], f"{source['dataverseUrl']}/.default", allow_interactive=False)
        source_dv = Dv(f"{source['dataverseUrl']}/api/data/v9.1", token)
        escaped_since = f"&$filter=createdon ge {since}" if since else ""
        rows = source_dv.get_all(
            "conversationtranscripts?$select=conversationtranscriptid,metadata,content,createdon"
            f"{escaped_since}&$orderby=createdon asc"
        )
        if args.limit:
            rows = rows[:args.limit]
        counts = {"created": 0, "updated": 0, "skipped": 0, "turns": 0, "errors": []}
        watermark = since
        for row in rows:
            try:
                status, turns = import_one(source_dv, collector, row, source_ctx, args.include_traces, args.reprocess, args.dry_run)
                counts[status] = counts.get(status, 0) + 1
                counts["turns"] += turns
                watermark = row.get("createdon") or watermark
            except Exception as exc:  # noqa: BLE001
                counts["errors"].append(f"{row.get('conversationtranscriptid', '')[:8]}: {type(exc).__name__}: {exc}")
        if not args.dry_run:
            state = {
                "pvci_name": source_name,
                "pvci_lastrunon": iso(datetime.now(timezone.utc)),
                "pvci_lastrunstatus": "success" if not counts["errors"] else "partial",
                "pvci_recordsprocessed": len(rows),
                "pvci_lasterror": "\n".join(counts["errors"])[:100_000],
            }
            if watermark:
                state["pvci_lastsyncedcreatedon"] = watermark
            found = find_record(collector, SYNCSTATE, "pvci_name", source_name, "pvci_syncstateid")
            if found:
                collector.patch(SYNCSTATE, found["pvci_syncstateid"], state)
            else:
                collector.post(SYNCSTATE, state)
        results.append({"environmentId": source["environmentId"], "status": "success", **counts})
    return {"status": "failed" if any(r["errors"] for r in results) else "success", "sources": results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/transcript_solution_config.dev.json")
    parser.add_argument("--registry", default="output/transcript-source-registry.json")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--since")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--include-traces", action="store_true")
    parser.add_argument("--reprocess", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Read and parse without writing to collector Dataverse")
    args = parser.parse_args()
    print(json.dumps(collect(args), indent=2))


if __name__ == "__main__":
    main()