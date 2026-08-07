#!/usr/bin/env python3
"""Sync Copilot Studio conversation transcripts into custom Dataverse tables.

Reads `conversationtranscripts`, parses the Bot Framework activity stream,
resolves the end user via `from.aadObjectId`, and upserts into:
  pvci_transcriptsession  - one row per transcript
  pvci_transcriptturn     - one row per activity
  pvci_transcriptidentitymap - one row per distinct end user
  pvci_syncstate          - incremental watermark

Incremental by default; re-running is safe (idempotent upsert).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dv_token import get_token_from_config  # noqa: E402

SESSIONS = "pvci_transcriptsessions"
TURNS = "pvci_transcriptturns"
IDENTITY = "pvci_transcriptidentitymaps"
FLOW_DETAILS = "pvci_flowrundetails"
SYNCSTATE = "pvci_syncstates"

SYNC_ROW_NAME = "default"
NOISE_TYPES = {"trace"}
NOISE_EVENTS = {"DialogTracing"}

# Dataverse memo ceiling is 1,048,576; stay clear of it.
MEMO_LIMIT = 900_000

MAX_RETRIES = 5
RETRY_STATUS = {429, 502, 503, 504}

# Flow runs carry no conversation id, so correlation is by time overlap only.
FLOWRUN_TOLERANCE_S = 20


def load_source_context(config_path: str) -> dict[str, str]:
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    dv_url = cfg.get("dataverseUrl", "")
    org = urlparse(dv_url).netloc or dv_url.replace("https://", "").replace("http://", "")
    out = {
        "tenant_id": str(cfg.get("tenantId", "") or ""),
        "environment_id": str(cfg.get("environmentId", "") or ""),
        "environment_name": str(cfg.get("environmentName", "") or ""),
        "org": org,
        "source": "dataverse_v9.1",
    }
    return out


def build_source_stamp(source_ctx: dict[str, str]) -> str:
    parts = [source_ctx.get("source", "dataverse_v9.1")]
    if source_ctx.get("tenant_id"):
        parts.append(f"tenant:{source_ctx['tenant_id']}")
    if source_ctx.get("environment_id"):
        parts.append(f"env:{source_ctx['environment_id']}")
    if source_ctx.get("environment_name"):
        parts.append(f"envName:{source_ctx['environment_name']}")
    if source_ctx.get("org"):
        parts.append(f"org:{source_ctx['org']}")
    return "|".join(parts)


class Dv:
    def __init__(self, base: str, token: str) -> None:
        self.base = base
        self.s = requests.Session()
        self.s.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json; charset=utf-8",
                "OData-Version": "4.0",
                "OData-MaxVersion": "4.0",
            }
        )

    def _request(self, method: str, url: str, **kw: Any) -> requests.Response:
        """Retries on Dataverse throttling (429) and transient 5xx, honouring Retry-After."""
        delay = 2.0
        last: requests.Response | None = None
        for attempt in range(MAX_RETRIES):
            r = self.s.request(method, url, timeout=180, **kw)
            if r.status_code not in RETRY_STATUS:
                return r
            last = r
            wait = float(r.headers.get("Retry-After") or delay)
            print(f"    [retry {attempt + 1}/{MAX_RETRIES}] {r.status_code} on {method} - waiting {wait:.0f}s", flush=True)
            time.sleep(wait)
            delay = min(delay * 2, 60)
        return last if last is not None else r

    def get(self, path: str) -> dict[str, Any]:
        r = self._request("GET", f"{self.base}/{path}")
        if not r.ok:
            raise RuntimeError(f"GET {path[:120]} -> {r.status_code} {r.text[:400]}")
        return r.json()

    def get_all(self, path: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        url = f"{self.base}/{path}"
        while url:
            r = self._request("GET", url)
            if not r.ok:
                raise RuntimeError(f"GET {url[:120]} -> {r.status_code} {r.text[:400]}")
            body = r.json()
            out.extend(body.get("value", []))
            url = body.get("@odata.nextLink")
        return out

    def post(self, entity_set: str, payload: dict[str, Any]) -> str:
        r = self._request("POST", f"{self.base}/{entity_set}", json=payload)
        if not r.ok:
            raise RuntimeError(f"POST {entity_set} -> {r.status_code} {r.text[:500]}")
        loc = r.headers.get("OData-EntityId") or r.headers.get("odata-entityid") or ""
        return loc.split("(")[-1].split(")")[0]

    def patch(self, entity_set: str, rid: str, payload: dict[str, Any]) -> None:
        r = self._request("PATCH", f"{self.base}/{entity_set}({rid})", json=payload)
        if not r.ok:
            raise RuntimeError(f"PATCH {entity_set}({rid}) -> {r.status_code} {r.text[:500]}")

    def delete(self, entity_set: str, rid: str) -> None:
        self._request("DELETE", f"{self.base}/{entity_set}({rid})")


def s1000(v: Any) -> str | None:
    if v is None:
        return None
    t = str(v)
    return t[:1000] if t else None


def epoch_utc(ts: Any) -> datetime | None:
    if ts is None:
        return None
    try:
        n = int(ts)
    except (TypeError, ValueError):
        return None
    if n > 10_000_000_000:  # milliseconds
        n //= 1000
    return datetime.fromtimestamp(n, tz=timezone.utc)


def iso(dt: datetime | None) -> str | None:
    return dt.isoformat().replace("+00:00", "Z") if dt else None


def jdump(obj: Any, indent: int | None = 2) -> tuple[str, bool]:
    """Serialise for a memo column; returns (text, was_truncated)."""
    text = json.dumps(obj, ensure_ascii=False, indent=indent)
    if len(text) <= MEMO_LIMIT:
        return text, False
    compact = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if len(compact) <= MEMO_LIMIT:
        return compact, False
    return compact[:MEMO_LIMIT] + "\n/* TRUNCATED */", True


def _ms(activity: dict[str, Any]) -> int | None:
    v = activity.get("timestampMs")
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def response_latencies(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """User utterance -> first agent reply, in ms. One entry per answered user turn."""
    ordered = sorted([m for m in messages if _ms(m) is not None], key=_ms)
    out: list[dict[str, Any]] = []
    for i, m in enumerate(ordered):
        if (m.get("from") or {}).get("role") != 1:
            continue
        for nxt in ordered[i + 1:]:
            if (nxt.get("from") or {}).get("role") == 1:
                break  # user spoke again before any reply
            out.append({
                "at": iso(epoch_utc(m.get("timestamp"))),
                "prompt": (m.get("text") or "")[:200],
                "latency_ms": _ms(nxt) - _ms(m),
            })
            break
    return out


INVOKE_PREFIX = "invoke"


def tool_calls(activities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pair DialogTracing action entries into start/end spans.

    Each invoked action is traced twice - once on entry (empty state) and once on
    completion (result variable populated, or `exception` set). Alternating pairs
    therefore bracket one execution; an action invoked twice yields four entries.
    """
    seen: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for a in activities:
        if a.get("name") != "DialogTracing":
            continue
        ts = _ms(a)
        if ts is None:
            continue
        for act in ((a.get("value") or {}).get("actions") or []):
            action_type = (act.get("actionType") or "")
            if not action_type.lower().startswith(INVOKE_PREFIX):
                continue
            seen.setdefault(act.get("actionId") or "?", []).append((ts, act))

    calls: list[dict[str, Any]] = []
    for action_id, occurrences in seen.items():
        occurrences.sort(key=lambda x: x[0])
        for i in range(0, len(occurrences) - 1, 2):
            start_ts, start_act = occurrences[i]
            end_ts, end_act = occurrences[i + 1]
            output = (end_act.get("variableState") or {}).get("dialogState") or {}
            exception = end_act.get("exception") or ""
            calls.append({
                "action_id": action_id,
                "action_type": end_act.get("actionType"),
                "topic": (end_act.get("topicId") or "").split(".")[-1],
                "started_utc": iso(datetime.fromtimestamp(start_ts / 1000, tz=timezone.utc)),
                "duration_ms": end_ts - start_ts,
                "failed": bool(exception),
                "exception": exception,
                "output": output,
            })
        if len(occurrences) % 2 == 1:
            ts, act = occurrences[-1]
            calls.append({
                "action_id": action_id,
                "action_type": act.get("actionType"),
                "topic": (act.get("topicId") or "").split(".")[-1],
                "started_utc": iso(datetime.fromtimestamp(ts / 1000, tz=timezone.utc)),
                "duration_ms": None,
                "failed": True,
                "exception": "no completion trace - call did not finish",
                "output": {},
            })

    calls.sort(key=lambda c: c["started_utc"] or "")
    return calls


def flow_action_spans(activities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Windows in which a backend flow may have run.

    Two sources, in order of precision:
      1. DialogTracing InvokeFlowAction - exact, but only emitted in design/test mode.
      2. DynamicPlan step Triggered/Finished - coarser, but present on production channels,
         which is the only signal available for msteams / m365copilot sessions.
    """
    seen: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for a in activities:
        if a.get("name") != "DialogTracing":
            continue
        ts = _ms(a)
        if ts is None:
            continue
        for act in ((a.get("value") or {}).get("actions") or []):
            if act.get("actionType") != "InvokeFlowAction":
                continue
            seen.setdefault(act.get("actionId") or "?", []).append((ts, act))

    spans: list[dict[str, Any]] = []
    for action_id, occ in seen.items():
        occ.sort(key=lambda x: x[0])
        for i in range(0, len(occ) - 1, 2):
            spans.append({
                "action_id": action_id,
                "topic": (occ[i][1].get("topicId") or "").split(".")[-1],
                "start_ms": occ[i][0],
                "end_ms": occ[i + 1][0],
                "exception": occ[i + 1][1].get("exception") or "",
                "source": "flow_action",
            })
        if len(occ) % 2 == 1:
            spans.append({
                "action_id": action_id,
                "topic": (occ[-1][1].get("topicId") or "").split(".")[-1],
                "start_ms": occ[-1][0],
                "end_ms": None,
                "exception": "no completion trace - call did not finish",
                "source": "flow_action",
            })

    if spans:
        return spans
    return plan_step_spans(activities)


PLAN_STEP_FALLBACK_MS = 90_000


def plan_step_spans(activities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    steps: dict[str, dict[str, Any]] = {}
    for a in activities:
        name = a.get("name") or ""
        if not name.startswith("DynamicPlanStep"):
            continue
        value = a.get("value") or {}
        step_id = value.get("stepId")
        ts = _ms(a)
        if not step_id or ts is None:
            continue
        rec = steps.setdefault(step_id, {})
        if name == "DynamicPlanStepTriggered":
            rec["start_ms"] = ts
            rec["topic"] = (value.get("taskDialogId") or "").split(".")[-1]
            rec["thought"] = value.get("thought")
        elif name == "DynamicPlanStepFinished":
            rec["end_ms"] = ts

    ordered = sorted(
        [(sid, r) for sid, r in steps.items() if r.get("start_ms")],
        key=lambda x: x[1]["start_ms"],
    )

    spans: list[dict[str, Any]] = []
    for idx, (step_id, rec) in enumerate(ordered):
        end = rec.get("end_ms")
        if end is None:
            # No completion event: stop at the next step, else cap the window.
            nxt = ordered[idx + 1][1]["start_ms"] if idx + 1 < len(ordered) else None
            end = min(nxt, rec["start_ms"] + PLAN_STEP_FALLBACK_MS) if nxt else rec["start_ms"] + PLAN_STEP_FALLBACK_MS
        spans.append({
            "action_id": step_id,
            "topic": rec.get("topic") or "?",
            "start_ms": rec["start_ms"],
            "end_ms": end,
            "exception": "",
            "source": "plan_step",
            "thought": rec.get("thought"),
        })
    return spans


def correlate_flow_runs(spans: list[dict[str, Any]], runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach overlapping flow runs to each span, best (closest start) first.

    ESS-style agents call a parent orchestrator that invokes child flows, so several
    genuine runs can overlap one action - all are kept rather than guessing one.
    """
    out: list[dict[str, Any]] = []
    for span in spans:
        lo = span["start_ms"] / 1000 - FLOWRUN_TOLERANCE_S
        hi = (span["end_ms"] or span["start_ms"]) / 1000 + FLOWRUN_TOLERANCE_S

        matches = []
        for r in runs:
            started = r.get("_start_epoch")
            if started is None or not (lo <= started <= hi):
                continue
            matches.append({
                "flow_run_id": r.get("flowrunid"),
                "run_name": r.get("name"),
                "workflow_id": r.get("workflowid"),
                "status": r.get("status"),
                "started_utc": r.get("starttime"),
                "ended_utc": r.get("endtime"),
                "duration_ms": r.get("duration"),
                "error_code": r.get("errorcode"),
                "error_message": r.get("errormessage"),
                "parent_run_id": r.get("parentrunid"),
                "calling_product_run_id": r.get("callingproductrunid"),
                "is_primary": r.get("isprimary"),
                "workflow_name": r.get("workflowname"),
                "conversation_id": r.get("conversationid"),
                "offset_ms": int(started * 1000 - span["start_ms"]),
            })

        matches.sort(key=lambda m: abs(m["offset_ms"]))
        for rank, m in enumerate(matches):
            m["rank"] = rank
            m["best"] = rank == 0

        out.append({
            "action_id": span["action_id"],
            "topic": span["topic"],
            "source": span.get("source", "flow_action"),
            "thought": span.get("thought"),
            "started_utc": iso(datetime.fromtimestamp(span["start_ms"] / 1000, tz=timezone.utc)),
            "span_ms": (span["end_ms"] - span["start_ms"]) if span["end_ms"] else None,
            "exception": span["exception"],
            "confidence": "none" if not matches else ("high" if len(matches) == 1 else "multiple"),
            "runs": matches,
        })
    return out


def fetch_flow_runs(dv: Dv, since_iso: str | None) -> list[dict[str, Any]]:
    fields = [
        "flowrunid",
        "name",
        "status",
        "starttime",
        "endtime",
        "duration",
        "workflowid",
        "workflowname",
        "errorcode",
        "errormessage",
        "parentrunid",
        "callingproductrunid",
        "isprimary",
        "conversationid",
    ]
    flt = f"&$filter=starttime ge {since_iso}" if since_iso else ""

    while True:
        try:
            rows = dv.get_all(
                f"flowruns?$select={','.join(fields)}{flt}&$orderby=starttime desc"
            )
            break
        except RuntimeError as exc:
            text = str(exc)
            match = re.search(r"Could not find a property named '([^']+)'", text)
            missing = match.group(1) if match else None
            if not missing or missing not in fields:
                raise
            fields.remove(missing)
            print(f"  warning: flowrun column '{missing}' not available in this environment; retrying without it", flush=True)

    unparsed = 0
    for r in rows:
        try:
            r["_start_epoch"] = datetime.strptime(
                r["starttime"], "%Y-%m-%dT%H:%M:%SZ"
            ).replace(tzinfo=timezone.utc).timestamp()
        except (KeyError, TypeError, ValueError):
            r["_start_epoch"] = None
            unparsed += 1
    if unparsed:
        print(f"  warning: {unparsed}/{len(rows)} flow runs had unparsable starttime", flush=True)
    return rows


def parse_transcript(row: dict[str, Any]) -> dict[str, Any]:
    meta = json.loads(row["metadata"]) if row.get("metadata") else {}
    content = json.loads(row["content"]) if row.get("content") else {}
    acts = content.get("activities") or []

    users = {
        a["from"]["aadObjectId"]
        for a in acts
        if isinstance(a.get("from"), dict) and a["from"].get("aadObjectId")
    }
    channels = {a["channelId"] for a in acts if a.get("channelId")}
    stamps = [int(a["timestamp"]) for a in acts if str(a.get("timestamp", "")).isdigit()]

    messages = [a for a in acts if a.get("type") == "message" and (a.get("text") or "").strip()]
    user_msgs = [a for a in messages if (a.get("from") or {}).get("role") == 1]
    agent_msgs = [a for a in messages if (a.get("from") or {}).get("role") != 1]
    events = [a for a in acts if a.get("type") == "event"]
    plan_events = [
        {"name": a.get("name"), "at": a.get("timestamp"), "value": a.get("value")}
        for a in events
        if (a.get("name") or "").startswith("DynamicPlan")
    ]

    test_mode = any(
        isinstance(a.get("channelData"), dict) and a["channelData"].get("testMode")
        for a in acts
    )
    # Authoritative test signal: the maker-portal test chat sets isDesignMode on ConversationInfo.
    for a in acts:
        if a.get("valueType") == "ConversationInfo" and isinstance(a.get("value"), dict):
            if a["value"].get("isDesignMode"):
                test_mode = True

    session_info: dict[str, Any] = {}
    for a in acts:
        if a.get("valueType") == "SessionInfo" and isinstance(a.get("value"), dict):
            session_info = a["value"]

    latencies = response_latencies(messages)
    lat_values = [x["latency_ms"] for x in latencies if x.get("latency_ms") is not None]
    calls = tool_calls(acts)
    call_durations = [c["duration_ms"] for c in calls if c.get("duration_ms") is not None]

    start = epoch_utc(min(stamps)) if stamps else None
    end = epoch_utc(max(stamps)) if stamps else None

    conversation = [
        {
            "n": i,
            "speaker": "user" if (a.get("from") or {}).get("role") == 1 else "agent",
            "at": iso(epoch_utc(a.get("timestamp"))),
            "text": a.get("text"),
            **({"attachments": a["attachments"]} if a.get("attachments") else {}),
        }
        for i, a in enumerate(messages, start=1)
    ]

    return {
        "transcript_id": row["conversationtranscriptid"],
        "created_on": row.get("createdon"),
        "metadata": meta,
        "conversation": conversation,
        "bot_id": meta.get("BotId"),
        "bot_name": meta.get("BotName"),
        "tenant_id": meta.get("AADTenantId"),
        "user_aad": next(iter(users), None),
        "multi_user": len(users) > 1,
        "channel": next(iter(channels), None),
        "start": start,
        "end": end,
        "duration_s": int((end - start).total_seconds()) if start and end else None,
        "activity_count": len(acts),
        "message_count": len(messages),
        "event_count": len(events),
        "user_turns": len(user_msgs),
        "agent_turns": len(agent_msgs),
        "initial_user_message": (user_msgs[0].get("text") if user_msgs else None),
        "last_agent_message": (agent_msgs[-1].get("text") if agent_msgs else None),
        "plan_events": plan_events,
        "test_mode": test_mode,
        "session_outcome": session_info.get("outcome"),
        "outcome_reason": session_info.get("outcomeReason"),
        "implied_success": session_info.get("impliedSuccess"),
        "session_turn_count": session_info.get("turnCount"),
        "latencies": latencies,
        "first_response_ms": lat_values[0] if lat_values else None,
        "avg_response_ms": int(sum(lat_values) / len(lat_values)) if lat_values else None,
        "max_response_ms": max(lat_values) if lat_values else None,
        "tool_calls": calls,
        "tool_call_count": len(calls),
        "tool_error_count": sum(1 for c in calls if c.get("failed")),
        "tool_total_ms": sum(call_durations) if call_durations else None,
        "max_tool_ms": max(call_durations) if call_durations else None,
        "activities": acts,
    }


def resolve_user(dv: Dv, aad: str | None, cache: dict[str, dict[str, Any] | None]) -> dict[str, Any] | None:
    if not aad:
        return None
    if aad in cache:
        return cache[aad]
    body = dv.get(
        f"systemusers?$select=systemuserid,fullname,domainname,internalemailaddress"
        f"&$filter=azureactivedirectoryobjectid eq {aad}&$top=1"
    )
    vals = body.get("value", [])
    cache[aad] = vals[0] if vals else None
    return cache[aad]


def resolve_bot_name(dv: Dv, schema_name: str | None, cache: dict[str, str]) -> str | None:
    if not schema_name:
        return schema_name
    if schema_name in cache:
        return cache[schema_name]
    escaped = schema_name.replace("'", "''")
    try:
        body = dv.get(
            "bots?$select=name"
            f"&$filter=schemaname eq '{escaped}' and componentstate eq 0&$top=1"
        )
        values = body.get("value", [])
        display_name = values[0].get("name") if values else None
    except RuntimeError:
        display_name = None
    cache[schema_name] = display_name or schema_name
    return cache[schema_name]


def find_by(dv: Dv, entity_set: str, field: str, value: str, idfield: str) -> str | None:
    escaped = value.replace("'", "''")
    body = dv.get(f"{entity_set}?$select={idfield}&$filter={field} eq '{escaped}'&$top=1")
    vals = body.get("value", [])
    return vals[0][idfield] if vals else None


def ensure_flow_run_placeholders(
    dv: Dv,
    matched_runs: list[dict[str, Any]],
    transcript_id: str,
) -> None:
    for run in matched_runs:
        run_name = run.get("run_name")
        if not run_name:
            continue
        existing = find_by(dv, FLOW_DETAILS, "pvci_runname", run_name, "pvci_flowrundetailid")
        if existing:
            continue
        payload = {
            "pvci_name": s1000(f"Pending · {run_name}"),
            "pvci_runname": s1000(run_name),
            "pvci_workflowentityid": s1000(run.get("workflow_id")),
            "pvci_status": s1000(run.get("status")),
            "pvci_transcriptid": s1000(transcript_id),
        }
        dv.post(FLOW_DETAILS, {key: value for key, value in payload.items() if value is not None})


def _sync_one(
    dv: Dv,
    row: dict[str, Any],
    user_cache: dict[str, dict[str, Any] | None],
    bot_name_cache: dict[str, str],
    stats: dict[str, Any],
    include_traces: bool,
    reprocess: bool,
    flow_runs: list[dict[str, Any]],
    source_ctx: dict[str, str],
) -> str:
    transcript_id = row["conversationtranscriptid"]

    # Transcripts are immutable once Copilot Studio finalises them, so an already-ingested
    # one is skipped before any parsing or writing. --reprocess overrides.
    existing = find_by(dv, SESSIONS, "pvci_transcriptid", transcript_id, "pvci_transcriptsessionid")
    if existing and not reprocess:
        stats["transcripts"] += 1
        stats["sessions_skipped"] += 1
        return f"  {transcript_id[:8]} skipped (already ingested)"

    p = parse_transcript(row)
    su = resolve_user(dv, p["user_aad"], user_cache)
    bot_display_name = resolve_bot_name(dv, p["bot_name"], bot_name_cache)

    display = (su or {}).get("fullname") or (p["user_aad"] or "unknown")[:8]
    name = f"{display} · {p['channel'] or '?'} · {iso(p['start']) or p['created_on']}"

    activities_json, trunc_a = jdump(p["activities"])
    conversation_json, trunc_c = jdump(p["conversation"])
    plan_json, _ = jdump(p["plan_events"])
    metadata_json, _ = jdump(p["metadata"])
    tools_json, _ = jdump(p["tool_calls"])

    flow_correlation = correlate_flow_runs(flow_action_spans(p["activities"]), flow_runs)
    flows_json, _ = jdump(flow_correlation)
    matched_runs = [r for fc in flow_correlation for r in fc["runs"]]
    failed_runs = [r for r in matched_runs if (r.get("status") or "").lower() not in ("succeeded", "running", "")]
    run_durations = [r["duration_ms"] for r in matched_runs if isinstance(r.get("duration_ms"), int)]

    payload: dict[str, Any] = {
        "pvci_name": s1000(name),
        "pvci_transcriptid": s1000(p["transcript_id"]),
        "pvci_botid": s1000(p["bot_id"]),
        "pvci_botname": s1000(bot_display_name),
        "pvci_tenantid": s1000(p["tenant_id"]),
        "pvci_useraadobjectid": s1000(p["user_aad"]),
        "pvci_userupn": s1000((su or {}).get("domainname")),
        "pvci_userdisplayname": s1000((su or {}).get("fullname")),
        "pvci_channel": s1000(p["channel"]),
        "pvci_startdatetimeutc": iso(p["start"]),
        "pvci_enddatetimeutc": iso(p["end"]),
        "pvci_durationseconds": p["duration_s"],
        "pvci_activitycount": p["activity_count"],
        "pvci_messagecount": p["message_count"],
        "pvci_eventcount": p["event_count"],
        "pvci_userturncount": p["user_turns"],
        "pvci_agentturncount": p["agent_turns"],
        "pvci_initialusermessage": p["initial_user_message"],
        "pvci_lastagentmessage": p["last_agent_message"],
        "pvci_istestmode": bool(p["test_mode"]),
        "pvci_multiuseranomaly": bool(p["multi_user"]),
        "pvci_firstresponsems": p["first_response_ms"],
        "pvci_avgresponsems": p["avg_response_ms"],
        "pvci_maxresponsems": p["max_response_ms"],
        "pvci_toolcallcount": p["tool_call_count"],
        "pvci_toolerrorcount": p["tool_error_count"],
        "pvci_tooltotalms": p["tool_total_ms"],
        "pvci_maxtoolms": p["max_tool_ms"],
        "pvci_toolcallsjson": tools_json,
        "pvci_flowrunsjson": flows_json,
        "pvci_flowruncount": len(matched_runs),
        "pvci_flowrunfailurecount": len(failed_runs),
        "pvci_flowrunmaxms": max(run_durations) if run_durations else None,
        "pvci_sessionoutcome": s1000(p["session_outcome"]),
        "pvci_outcomereason": s1000(p["outcome_reason"]),
        "pvci_isresolvedimplied": s1000(str(p["implied_success"]).lower() if p["implied_success"] is not None else None),
        "pvci_turncount": p["session_turn_count"],
        "pvci_planeventsjson": plan_json,
        "pvci_activitiesjson": activities_json,
        "pvci_conversationjson": conversation_json,
        "pvci_metadatajson": metadata_json,
        "pvci_payloadtruncated": bool(trunc_a or trunc_c),
        "pvci_transcriptcreatedon": p["created_on"],
        "pvci_ingestedon": iso(datetime.now(timezone.utc)),
        "pvci_datasource": build_source_stamp(source_ctx),
        "pvci_correlationstatus": "exact" if su else ("heuristic" if p["user_aad"] else "unmatched"),
    }
    if su:
        payload["pvci_UserId@odata.bind"] = f"/systemusers({su['systemuserid']})"
    payload = {k: v for k, v in payload.items() if v is not None}

    existing = find_by(dv, SESSIONS, "pvci_transcriptid", p["transcript_id"], "pvci_transcriptsessionid")

    # Capture stale turns before writing new ones so the session is never left empty on failure.
    stale: list[str] = []
    if existing:
        dv.patch(SESSIONS, existing, payload)
        session_id = existing
        stats["sessions_updated"] += 1
        stale = [
            t["pvci_transcriptturnid"]
            for t in dv.get_all(
                f"{TURNS}?$select=pvci_transcriptturnid&$filter=pvci_transcriptid eq '{p['transcript_id']}'"
            )
        ]
    else:
        session_id = dv.post(SESSIONS, payload)
        stats["sessions_created"] += 1

    ensure_flow_run_placeholders(dv, matched_runs, p["transcript_id"])

    idx = 0
    last_user_ms: int | None = None
    for a in p["activities"]:
        atype = a.get("type")
        ename = a.get("name")
        if not include_traces and (atype in NOISE_TYPES or ename in NOISE_EVENTS):
            continue
        frm = a.get("from") or {}
        role = frm.get("role")
        speaker = "user" if role == 1 else "agent"

        this_ms = _ms(a)
        latency_ms: int | None = None
        if atype == "message" and (a.get("text") or "").strip():
            if role == 1:
                last_user_ms = this_ms
            elif last_user_ms is not None and this_ms is not None:
                latency_ms = this_ms - last_user_ms
                last_user_ms = None  # only the first reply carries the latency

        turn: dict[str, Any] = {
            "pvci_name": s1000(f"{idx:04d} {speaker} {atype or '?'}"),
            "pvci_transcriptid": s1000(p["transcript_id"]),
            "pvci_turnindex": idx,
            "pvci_activitytype": s1000(atype),
            "pvci_speaker": s1000(speaker),
            "pvci_role": role if isinstance(role, int) else None,
            "pvci_aadobjectid": s1000(frm.get("aadObjectId")),
            "pvci_eventname": s1000(ename),
            "pvci_channelid": s1000(a.get("channelId")),
            "pvci_timestamputc": iso(epoch_utc(a.get("timestamp"))),
            "pvci_turntext": (a.get("text") or None),
            "pvci_latencyms": latency_ms,
            "pvci_SessionId@odata.bind": f"/{SESSIONS}({session_id})",
        }
        if a.get("value") is not None:
            turn["pvci_valuejson"] = jdump(a["value"])[0][:100_000]
        dv.post(TURNS, {k: v for k, v in turn.items() if v is not None})
        stats["turns"] += 1
        idx += 1

    for old_id in stale:
        dv.delete(TURNS, old_id)

    if p["multi_user"]:
        stats["anomalies"] += 1
    stats["transcripts"] += 1

    return (f"  {p['transcript_id'][:8]} {str(p['channel']):<12} acts={p['activity_count']:3d} "
            f"msgs={p['message_count']:2d} user={display}")


def sync(dv: Dv, cfg_path: str, since: str | None, full: bool, include_traces: bool,
         limit: int | None, reprocess: bool = False, source_ctx: dict[str, str] | None = None) -> dict[str, Any]:
    # `ge` not `gt`: same-second records at the boundary would otherwise be skipped forever.
    # Re-processing the boundary row is harmless because upsert is keyed on pvci_transcriptid.
    flt = "" if full or not since else f"&$filter=createdon ge {since}"
    query = (
        "conversationtranscripts"
        "?$select=conversationtranscriptid,metadata,content,createdon"
        f"{flt}&$orderby=createdon asc"
    )
    rows = dv.get_all(query)
    if limit:
        rows = rows[:limit]

    earliest = rows[0].get("createdon") if rows else None
    # Flow runs precede the transcript row being written, so widen the window generously.
    flow_runs = fetch_flow_runs(dv, None) if rows else []
    print(f"flow runs in window: {len(flow_runs)} (earliest transcript {earliest})")

    if source_ctx is None:
        source_ctx = load_source_context(cfg_path)

    user_cache: dict[str, dict[str, Any] | None] = {}
    bot_name_cache: dict[str, str] = {}
    stats = {"transcripts": 0, "sessions_created": 0, "sessions_updated": 0, "sessions_skipped": 0,
             "turns": 0, "users": 0, "anomalies": 0}
    errors: list[str] = []
    watermark = since
    watermark_frozen = False

    for row in rows:
        transcript_id = row["conversationtranscriptid"]
        try:
            processed = _sync_one(
                dv, row, user_cache, bot_name_cache, stats, include_traces, reprocess, flow_runs, source_ctx
            )
            # Only advance while every prior transcript succeeded, so a failure is retried next run.
            if not watermark_frozen:
                watermark = row.get("createdon") or watermark
            print(processed, flush=True)
        except Exception as exc:
            watermark_frozen = True
            msg = f"{transcript_id[:8]}: {type(exc).__name__}: {exc}"
            errors.append(msg)
            print(f"  FAILED {msg}", flush=True)

    for aad, su in user_cache.items():
        if not aad:
            continue
        rec = {
            "pvci_name": s1000((su or {}).get("fullname") or aad),
            "pvci_aadobjectid": s1000(aad),
            "pvci_userprincipalname": s1000((su or {}).get("domainname")),
            "pvci_displayname": s1000((su or {}).get("fullname")),
            "pvci_systemuserid": s1000((su or {}).get("systemuserid")),
            "pvci_correlationsource": "conversationtranscript.from.aadObjectId",
            "pvci_correlationconfidence": "exact" if su else "unresolved",
            "pvci_lastseenon": iso(datetime.now(timezone.utc)),
        }
        rec = {k: v for k, v in rec.items() if v is not None}
        found = find_by(dv, IDENTITY, "pvci_aadobjectid", aad, "pvci_transcriptidentitymapid")
        if found:
            dv.patch(IDENTITY, found, rec)
        else:
            dv.post(IDENTITY, rec)
        stats["users"] += 1

    state = {
        "pvci_name": SYNC_ROW_NAME,
        "pvci_lastrunon": iso(datetime.now(timezone.utc)),
        "pvci_lastrunstatus": "success" if not errors else ("partial" if stats["transcripts"] else "failed"),
        "pvci_recordsprocessed": stats["transcripts"],
        "pvci_lasterror": ("\n".join(errors))[:100_000] if errors else "",
    }
    if watermark:
        state["pvci_lastsyncedcreatedon"] = watermark
    found = find_by(dv, SYNCSTATE, "pvci_name", SYNC_ROW_NAME, "pvci_syncstateid")
    if found:
        dv.patch(SYNCSTATE, found, state)
    else:
        dv.post(SYNCSTATE, state)

    stats["watermark"] = watermark
    stats["errors"] = errors
    stats["status"] = state["pvci_lastrunstatus"]
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="config/transcript_solution_config.dev.json")
    ap.add_argument("--full", action="store_true", help="Ignore watermark and reprocess everything")
    ap.add_argument("--since", default=None, help="ISO timestamp override, e.g. 2026-07-29T00:00:00Z")
    ap.add_argument("--include-traces", action="store_true", help="Also store trace/DialogTracing activities")
    ap.add_argument("--reprocess", action="store_true",
                    help="Rewrite transcripts already ingested (default: skip them)")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    token, dv_url = get_token_from_config(args.config)
    dv = Dv(f"{dv_url}/api/data/v9.1", token)
    source_ctx = load_source_context(args.config)

    since = args.since
    if not since and not args.full:
        rows = dv.get_all(f"{SYNCSTATE}?$select=pvci_lastsyncedcreatedon&$filter=pvci_name eq '{SYNC_ROW_NAME}'&$top=1")
        if rows:
            since = rows[0].get("pvci_lastsyncedcreatedon")

    mode = "FULL" if args.full else (f"INCREMENTAL since {since}" if since else "INITIAL")
    print(f"sync mode: {mode}")

    stats = sync(
        dv,
        args.config,
        since,
        args.full,
        args.include_traces,
        args.limit,
        args.reprocess,
        source_ctx,
    )
    print("\n" + json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
