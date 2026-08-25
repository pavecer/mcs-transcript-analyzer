#!/usr/bin/env python3
"""Fetch full Power Automate run details for flow runs correlated to transcripts.

The Flow management API needs a different token audience than Dataverse, so a plugin
cannot do this - it runs here and stores the result in pvci_flowrundetail.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dv_token import get_token_from_config, require_authorized_config  # noqa: E402

FLOW_API = "https://api.flow.microsoft.com"
FLOW_RESOURCE = "https://service.flow.microsoft.com/"
API_VERSION = "2016-11-01"
DETAILS = "pvci_flowrundetails"

MEMO_LIMIT = 900_000
PER_ACTION_LIMIT = 40_000


def flow_token() -> str:
    proc = subprocess.run(
        ["az", "account", "get-access-token", "--resource", FLOW_RESOURCE, "-o", "json"],
        capture_output=True, text=True, timeout=90,
    )
    if proc.returncode != 0:
        raise SystemExit(f"Could not get a Flow API token. Run: az login\n{proc.stderr[:300]}")
    return json.loads(proc.stdout)["accessToken"]


def fetch_content(session: requests.Session, link: dict[str, Any] | None) -> Any:
    """Inputs/outputs live behind short-lived SAS URIs, not in the action payload."""
    if not link or not link.get("uri"):
        return None
    size = link.get("contentSize") or 0
    if size > PER_ACTION_LIMIT:
        return {"_truncated": True, "_contentSize": size}
    try:
        r = session.get(link["uri"], timeout=90)
        if not r.ok:
            return {"_error": f"HTTP {r.status_code}"}
        text = r.text
        try:
            return json.loads(text)
        except ValueError:
            return text[:PER_ACTION_LIMIT]
    except requests.RequestException as exc:
        return {"_error": str(exc)[:200]}


def fetch_collection(
    session: requests.Session,
    url: str,
    headers: dict[str, str],
) -> tuple[list[dict[str, Any]], str | None]:
    values: list[dict[str, Any]] = []
    while url:
        response = session.get(url, headers=headers, timeout=120)
        if not response.ok:
            return values, f"HTTP {response.status_code}: {response.text[:200]}"
        body = response.json()
        values.extend(body.get("value") or [])
        url = body.get("nextLink") or body.get("@odata.nextLink") or ""
    return values, None


def action_entry(session: requests.Session, action: dict[str, Any]) -> dict[str, Any]:
    properties = action.get("properties") or {}
    entry: dict[str, Any] = {
        "name": action.get("name"),
        "status": properties.get("status"),
        "start": properties.get("startTime"),
        "end": properties.get("endTime"),
        "code": properties.get("code"),
    }
    if properties.get("error"):
        entry["error"] = properties["error"]
    if properties.get("status") != "Skipped":
        entry["inputs"] = fetch_content(session, properties.get("inputsLink"))
        entry["outputs"] = fetch_content(session, properties.get("outputsLink"))
    return entry


def collect_action_definitions(
    actions: dict[str, Any] | None,
    parent: str | None = None,
    branch: str | None = None,
) -> dict[str, dict[str, Any]]:
    collected: dict[str, dict[str, Any]] = {}
    for name, definition in (actions or {}).items():
        if not isinstance(definition, dict):
            continue
        inputs = definition.get("inputs") or {}
        host = inputs.get("host") or {} if isinstance(inputs, dict) else {}
        collected[name] = {
            "type": definition.get("type"),
            "run_after": definition.get("runAfter") or {},
            "parent": parent,
            "branch": branch,
            "operation": host.get("operationId"),
        }
        collected.update(collect_action_definitions(definition.get("actions"), name, "body"))
        collected.update(collect_action_definitions((definition.get("else") or {}).get("actions"), name, "else"))
        for case_name, case in (definition.get("cases") or {}).items():
            collected.update(collect_action_definitions(case.get("actions"), name, f"case:{case_name}"))
        collected.update(collect_action_definitions((definition.get("default") or {}).get("actions"), name, "default"))
    return collected


def add_definition(entry: dict[str, Any], definition: dict[str, Any] | None) -> None:
    if not definition:
        return
    for field in ("type", "run_after", "parent", "branch", "operation"):
        if definition.get(field) is not None:
            entry[field] = definition[field]


def without_bodies(entry: dict[str, Any]) -> dict[str, Any]:
    compact = {key: value for key, value in entry.items() if key not in ("inputs", "outputs")}
    if entry.get("repetitions"):
        compact["repetitions"] = [without_bodies(item) for item in entry["repetitions"]]
    return compact


def contains_truncated_body(entry: dict[str, Any]) -> bool:
    for field in ("inputs", "outputs"):
        value = entry.get(field)
        if isinstance(value, dict) and value.get("_truncated"):
            return True
    return any(contains_truncated_body(item) for item in entry.get("repetitions") or [])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="config/transcript_solution_config.dev.json")
    ap.add_argument("--limit", type=int, default=None, help="Cap how many runs to fetch")
    ap.add_argument("--run-name", default=None, help="Fetch only this correlated run name")
    ap.add_argument("--refresh", action="store_true", help="Re-fetch runs already stored")
    args = ap.parse_args()
    require_authorized_config(args.config)

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    env_id = cfg["environmentId"]
    dv_token, dv_url = get_token_from_config(args.config)
    base = f"{dv_url}/api/data/v9.1"
    dh = {
        "Authorization": f"Bearer {dv_token}",
        "Accept": "application/json",
        "Content-Type": "application/json; charset=utf-8",
    }

    ft = flow_token()
    fh = {"Authorization": f"Bearer {ft}", "Accept": "application/json"}

    with requests.Session() as s:
        flows, flow_error = fetch_collection(
            s,
            f"{FLOW_API}/providers/Microsoft.ProcessSimple/environments/{env_id}/flows?api-version={API_VERSION}",
            fh,
        )
        if flow_error:
            raise SystemExit(f"Could not list flows: {flow_error}")
        # The Flow API id differs from the Dataverse workflowid; workflowEntityId bridges them.
        by_entity: dict[str, dict[str, str]] = {}
        for f in flows:
            props = f.get("properties") or {}
            entity = (props.get("workflowEntityId") or "").lower()
            if entity:
                by_entity[entity] = {"flowApiId": f["name"], "displayName": props.get("displayName") or ""}
        print(f"flows discovered: {len(flows)} ({len(by_entity)} with a Dataverse id)")
        definition_cache: dict[str, dict[str, dict[str, Any]]] = {}

        sessions = s.get(
            f"{base}/pvci_transcriptsessions?$select=pvci_transcriptid,pvci_flowrunsjson"
            "&$filter=pvci_flowruncount gt 0", headers=dh, timeout=120,
        ).json().get("value", [])

        wanted: dict[str, dict[str, str]] = {}
        for row in sessions:
            for corr in json.loads(row.get("pvci_flowrunsjson") or "[]"):
                for run in corr.get("runs", []):
                    name = run.get("run_name")
                    if name:
                        wanted[name] = {
                            "workflow_id": (run.get("workflow_id") or "").lower(),
                            "transcript_id": row.get("pvci_transcriptid") or "",
                        }
        print(f"correlated runs to fetch: {len(wanted)}")

        existing = {
            r["pvci_runname"]: {
                "id": r["pvci_flowrundetailid"],
                "fetched_on": r.get("pvci_fetchedon"),
            }
            for r in s.get(f"{base}/{DETAILS}?$select=pvci_runname,pvci_flowrundetailid,pvci_fetchedon",
                           headers=dh, timeout=120).json().get("value", [])
        }

        done = skipped = failed = 0
        candidates = list(wanted.items())
        if args.run_name:
            candidates = [(args.run_name, wanted[args.run_name])] if args.run_name in wanted else []
            if not candidates:
                raise SystemExit(f"Run {args.run_name} is not present in correlated transcript data.")
        if args.limit is not None:
            candidates = candidates[:args.limit]

        for run_name, meta in candidates:
            if run_name in existing and existing[run_name]["fetched_on"] and not args.refresh:
                skipped += 1
                continue

            flow = by_entity.get(meta["workflow_id"])
            if not flow:
                print(f"  {run_name[:28]} - no Flow API mapping for workflow {meta['workflow_id'][:8]}")
                failed += 1
                continue

            root = (f"{FLOW_API}/providers/Microsoft.ProcessSimple/environments/{env_id}"
                    f"/flows/{flow['flowApiId']}/runs/{run_name}")

            flow_api_id = flow["flowApiId"]
            if flow_api_id not in definition_cache:
                definition_response = s.get(
                    f"{FLOW_API}/providers/Microsoft.ProcessSimple/environments/{env_id}"
                    f"/flows/{flow_api_id}?api-version={API_VERSION}",
                    headers=fh, timeout=120,
                )
                if definition_response.ok:
                    definition = (definition_response.json().get("properties") or {}).get("definition") or {}
                    definition_cache[flow_api_id] = collect_action_definitions(definition.get("actions"))
                else:
                    definition_cache[flow_api_id] = {}
            action_definitions = definition_cache[flow_api_id]

            rd = s.get(f"{root}?api-version={API_VERSION}", headers=fh, timeout=120)
            if not rd.ok:
                print(f"  {run_name[:28]} - run detail HTTP {rd.status_code}")
                failed += 1
                continue

            props = rd.json().get("properties", {})
            actions, action_error = fetch_collection(
                s, f"{root}/actions?api-version={API_VERSION}", fh,
            )

            detailed = []
            errors = []
            if action_error:
                errors.append(f"Action history: {action_error}")
            for act in actions:
                p = act.get("properties") or {}
                entry = action_entry(s, act)
                add_definition(entry, action_definitions.get(str(act.get("name") or "")))
                if p.get("error") and p.get("status") not in ("Skipped", "Succeeded"):
                    errors.append(f"{act.get('name')}: {json.dumps(p['error'])[:300]}")

                action_name = quote(str(act.get("name") or ""), safe="")
                repetitions, repetition_error = fetch_collection(
                    s,
                    f"{root}/actions/{action_name}/repetitions?api-version={API_VERSION}",
                    fh,
                )
                if repetitions:
                    entry["repetitions"] = [action_entry(s, repetition) for repetition in repetitions]
                    for repetition in repetitions:
                        rp = repetition.get("properties") or {}
                        if rp.get("error") and rp.get("status") not in ("Skipped", "Succeeded"):
                            errors.append(
                                f"{act.get('name')}[{repetition.get('name')}]: "
                                f"{json.dumps(rp['error'])[:300]}"
                            )
                elif repetition_error and not repetition_error.startswith("HTTP 404"):
                    entry["repetitions_error"] = repetition_error
                detailed.append(entry)

            trigger = props.get("trigger") or {}
            trigger_entry = {
                "name": trigger.get("name"),
                "status": trigger.get("status"),
                "start": trigger.get("startTime"),
                "end": trigger.get("endTime"),
                "inputs": fetch_content(s, trigger.get("inputsLink")),
                "outputs": fetch_content(s, trigger.get("outputsLink")),
            }
            response = props.get("response") or {}
            response_entry = {
                "name": response.get("name"),
                "status": response.get("status"),
                "start": response.get("startTime"),
                "end": response.get("endTime"),
                "code": response.get("code"),
                "outputs": fetch_content(s, response.get("outputsLink")),
            } if response else None
            run_context = {
                "correlation": props.get("correlation"),
                "trigger": trigger_entry,
                "response": response_entry,
            }

            actions_json = json.dumps(detailed, ensure_ascii=False, indent=1)
            aggregate_truncated = len(actions_json) > MEMO_LIMIT
            body_truncated = any(contains_truncated_body(entry) for entry in detailed)
            if aggregate_truncated:
                actions_json = json.dumps(
                    [without_bodies(entry) for entry in detailed],
                    ensure_ascii=False, indent=1,
                )
            truncated = aggregate_truncated or body_truncated

            start = props.get("startTime")
            end = props.get("endTime")
            duration = None
            if start and end:
                try:
                    fmt = "%Y-%m-%dT%H:%M:%S.%f%z"
                    duration = int((datetime.strptime(end.replace("Z", "+0000")[:26] + "+0000", fmt)
                                    - datetime.strptime(start.replace("Z", "+0000")[:26] + "+0000", fmt))
                                   .total_seconds() * 1000)
                except ValueError:
                    duration = None

            statuses = [(a.get("properties") or {}).get("status") for a in actions]
            payload = {
                "pvci_name": f"{flow['displayName'][:80]} · {run_name[-12:]}",
                "pvci_runname": run_name,
                "pvci_flowapiid": flow["flowApiId"],
                "pvci_workflowentityid": meta["workflow_id"],
                "pvci_flowdisplayname": flow["displayName"][:1000],
                "pvci_status": props.get("status"),
                "pvci_starttime": start,
                "pvci_endtime": end,
                "pvci_durationms": duration,
                "pvci_actioncount": len(actions),
                "pvci_failedactioncount": sum(1 for x in statuses if x not in ("Succeeded", "Skipped", None)),
                "pvci_skippedactioncount": sum(1 for x in statuses if x == "Skipped"),
                "pvci_triggerjson": json.dumps(run_context, ensure_ascii=False, indent=1)[:MEMO_LIMIT],
                "pvci_actionsjson": actions_json,
                "pvci_errorsummary": ("\n".join(errors))[:100_000],
                "pvci_transcriptid": meta["transcript_id"],
                "pvci_payloadtruncated": truncated,
                "pvci_fetchedon": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
            payload = {k: v for k, v in payload.items() if v is not None}

            if run_name in existing:
                r = s.patch(
                    f"{base}/{DETAILS}({existing[run_name]['id']})",
                    headers=dh, json=payload, timeout=180,
                )
            else:
                r = s.post(f"{base}/{DETAILS}", headers=dh, json=payload, timeout=180)

            if r.ok:
                done += 1
                print(f"  {run_name[-14:]}  {flow['displayName'][:38]:<38} "
                      f"{props.get('status'):<10} {len(actions)} actions")
            else:
                failed += 1
                print(f"  {run_name[-14:]} - save failed {r.status_code} {r.text[:200]}")

    print(json.dumps({"fetched": done, "skipped": skipped, "failed": failed}, indent=2))


if __name__ == "__main__":
    main()
