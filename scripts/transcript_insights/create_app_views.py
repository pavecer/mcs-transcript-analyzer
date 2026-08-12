#!/usr/bin/env python3
"""Create model-driven app surface: views + sitemap + app module."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dv_token import get_token_from_config  # noqa: E402

SESSION = "pvci_transcriptsession"
TURN = "pvci_transcriptturn"
IDENTITY = "pvci_transcriptidentitymap"
ENVIRONMENT = "pvci_environmentinventory"
INVENTORY_SYNC = "pvci_inventorysyncrun"
THRESHOLD = "pvci_agentthresholdsnapshot"
GOVERNANCE_SYNC = "pvci_governancesyncrun"
AGENT = "pvci_agentinventory"
CREDIT = "pvci_creditusage"
CAPACITY = "pvci_creditcapacitysnapshot"
CREDIT_SYNC = "pvci_creditsyncrun"
USER_USAGE = "pvci_credituserusage"
PRIVACY = "pvci_creditprivacysetting"
SOLUTION = "pvConversationInsights"


def headers(token: str, solution: str | None = None) -> dict[str, str]:
    h = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json; charset=utf-8",
        "OData-Version": "4.0",
        "OData-MaxVersion": "4.0",
    }
    if solution:
        h["MSCRM.SolutionUniqueName"] = solution
    return h


def otc(s: requests.Session, base: str, h: dict[str, str], logical: str) -> int:
    r = s.get(f"{base}/EntityDefinitions(LogicalName='{logical}')?$select=ObjectTypeCode", headers=h, timeout=60)
    r.raise_for_status()
    return r.json()["ObjectTypeCode"]


def grid(code: int, idcol: str, cells: list[tuple[str, int]]) -> str:
    c = "".join(f'<cell name="{n}" width="{w}" />' for n, w in cells)
    return (
        f'<grid name="resultset" object="{code}" jump="pvci_name" select="1" icon="1" preview="1">'
        f'<row name="result" id="{idcol}">{c}</row></grid>'
    )


def fetch(entity: str, attrs: list[str], order: str, desc: bool = True, filt: str = "") -> str:
    a = "".join(f'<attribute name="{x}" />' for x in attrs)
    return (
        f'<fetch version="1.0" mapping="logical"><entity name="{entity}">{a}'
        f'{filt}<order attribute="{order}" descending="{str(desc).lower()}" /></entity></fetch>'
    )


def upsert_view(
    s: requests.Session,
    base: str,
    token: str,
    entity: str,
    name: str,
    fetchxml: str,
    layoutxml: str,
    is_default: bool = False,
) -> str:
    h = headers(token)
    q = s.get(
        f"{base}/savedqueries?$select=savedqueryid,name&$filter=returnedtypecode eq '{entity}' and name eq '{name}'&$top=1",
        headers=h,
        timeout=60,
    )
    existing = q.json().get("value", []) if q.ok else []
    payload: dict[str, Any] = {
        "name": name,
        "description": name,
        "fetchxml": fetchxml,
        "layoutxml": layoutxml,
        "returnedtypecode": entity,
        "querytype": 0,
    }
    if existing:
        sid = existing[0]["savedqueryid"]
        body = {k: v for k, v in payload.items() if k in ("fetchxml", "layoutxml", "description")}
        r = s.patch(f"{base}/savedqueries({sid})", headers=headers(token, SOLUTION), json=body, timeout=60)
        return f"updated {name}" if r.ok else f"FAILED update {name}: {r.status_code} {r.text[:200]}"

    if is_default:
        payload["isdefault"] = True
    r = s.post(f"{base}/savedqueries", headers=headers(token, SOLUTION), json=payload, timeout=60)
    return f"created {name}" if r.ok else f"FAILED create {name}: {r.status_code} {r.text[:250]}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="config/transcript_solution_config.dev.json")
    args = ap.parse_args()

    token, dv_url = get_token_from_config(args.config)
    base = f"{dv_url}/api/data/v9.1"
    h = headers(token)

    with requests.Session() as s:
        sc = otc(s, base, h, SESSION)
        tc = otc(s, base, h, TURN)
        ic = otc(s, base, h, IDENTITY)
        ec = otc(s, base, h, ENVIRONMENT)
        isc = otc(s, base, h, INVENTORY_SYNC)
        thc = otc(s, base, h, THRESHOLD)
        gsc = otc(s, base, h, GOVERNANCE_SYNC)
        ac = otc(s, base, h, AGENT)
        cc = otc(s, base, h, CREDIT)
        capc = otc(s, base, h, CAPACITY)
        csc = otc(s, base, h, CREDIT_SYNC)
        uuc = otc(s, base, h, USER_USAGE)
        pc = otc(s, base, h, PRIVACY)

        results = []

        sess_cols = [
            ("pvci_name", 200),
            ("pvci_userdisplayname", 120),
            ("pvci_channel", 90),
            ("pvci_startdatetimeutc", 130),
            ("pvci_messagecount", 70),
            ("pvci_firstresponsems", 95),
            ("pvci_maxresponsems", 95),
            ("pvci_toolcallcount", 70),
            ("pvci_toolerrorcount", 75),
            ("pvci_sessionoutcome", 95),
            ("pvci_istestmode", 70),
        ]
        sess_attrs = [c[0] for c in sess_cols] + ["pvci_transcriptsessionid"]

        results.append(
            upsert_view(
                s, base, token, SESSION, "Active Transcript Sessions",
                fetch(SESSION, sess_attrs, "pvci_startdatetimeutc"),
                grid(sc, "pvci_transcriptsessionid", sess_cols),
            )
        )

        credit_cols = [
            ("pvci_usagedate", 120),
            ("pvci_agentname", 220),
            ("pvci_environmentid", 240),
            ("pvci_harness", 110),
            ("pvci_featurename", 180),
            ("pvci_billedcredits", 110),
            ("pvci_nonbilledcredits", 120),
            ("pvci_resolutionstatus", 120),
        ]
        credit_attrs = [c[0] for c in credit_cols] + ["pvci_creditusageid"]
        results.append(
            upsert_view(
                s, base, token, CREDIT, "Credit Usage - Latest",
                fetch(CREDIT, credit_attrs, "pvci_usagedate"),
                grid(cc, "pvci_creditusageid", credit_cols),
            )
        )
        results.append(
            upsert_view(
                s, base, token, CREDIT, "Credit Usage - Unresolved Resources",
                fetch(
                    CREDIT,
                    credit_attrs,
                    "pvci_usagedate",
                    filt=(
                        '<filter type="and"><condition attribute="pvci_resolutionstatus" '
                        'operator="ne" value="exact" /></filter>'
                    ),
                ),
                grid(cc, "pvci_creditusageid", credit_cols),
            )
        )

        capacity_cols = [
            ("pvci_asofdate", 120),
            ("pvci_environmentname", 180),
            ("pvci_entitlementid", 120),
            ("pvci_allocated", 100),
            ("pvci_consumed", 100),
            ("pvci_available", 100),
            ("pvci_status", 110),
            ("pvci_drawfromtenantpool", 90),
        ]
        results.append(
            upsert_view(
                s, base, token, CAPACITY, "Credit Capacity - Latest",
                fetch(
                    CAPACITY,
                    [c[0] for c in capacity_cols] + ["pvci_creditcapacitysnapshotid"],
                    "pvci_asofdate",
                ),
                grid(capc, "pvci_creditcapacitysnapshotid", capacity_cols),
            )
        )

        agent_cols = [
            ("pvci_displayname", 220),
            ("pvci_environmentname", 180),
            ("pvci_environmenttype", 120),
            ("pvci_resourceid", 240),
            ("pvci_resourcetype", 130),
            ("pvci_harness", 110),
            ("pvci_classificationconfidence", 130),
            ("pvci_model", 120),
            ("pvci_agentstatus", 100),
            ("pvci_hasdetailedaccess", 100),
            ("pvci_published", 70),
        ]
        agent_attrs = [c[0] for c in agent_cols] + ["pvci_agentinventoryid"]
        results.append(
            upsert_view(
                s, base, token, AGENT, "Agent Inventory - All Resources",
                fetch(AGENT, agent_attrs, "pvci_displayname", desc=False),
                grid(ac, "pvci_agentinventoryid", agent_cols),
            )
        )

        environment_cols = [
            ("pvci_displayname", 220),
            ("pvci_environmentid", 260),
            ("pvci_environmenttype", 120),
            ("pvci_geo", 90),
            ("pvci_state", 100),
            ("pvci_hasdataverse", 100),
            ("pvci_hasdetailedaccess", 110),
            ("pvci_lastsyncedon", 140),
        ]
        results.append(
            upsert_view(
                s, base, token, ENVIRONMENT, "Environment Inventory - All",
                fetch(
                    ENVIRONMENT,
                    [c[0] for c in environment_cols] + ["pvci_environmentinventoryid"],
                    "pvci_displayname",
                    desc=False,
                ),
                grid(ec, "pvci_environmentinventoryid", environment_cols),
            )
        )

        inventory_sync_cols = [
            ("pvci_name", 220),
            ("pvci_status", 90),
            ("pvci_startedon", 140),
            ("pvci_completedon", 140),
            ("pvci_environmentcount", 100),
            ("pvci_agentcount", 90),
            ("pvci_createdcount", 90),
            ("pvci_updatedcount", 90),
            ("pvci_rejectedcount", 90),
        ]
        results.append(
            upsert_view(
                s, base, token, INVENTORY_SYNC, "Inventory Sync Runs - Latest",
                fetch(
                    INVENTORY_SYNC,
                    [c[0] for c in inventory_sync_cols] + ["pvci_inventorysyncrunid"],
                    "pvci_startedon",
                ),
                grid(isc, "pvci_inventorysyncrunid", inventory_sync_cols),
            )
        )
        results.append(
            upsert_view(
                s, base, token, AGENT, "Agent Inventory - Unknown Harness",
                fetch(
                    AGENT,
                    agent_attrs,
                    "pvci_displayname",
                    desc=False,
                    filt='<filter type="and"><condition attribute="pvci_harness" operator="eq" value="unknown" /></filter>',
                ),
                grid(ac, "pvci_agentinventoryid", agent_cols),
            )
        )
        results.append(
            upsert_view(
                s, base, token, AGENT, "Agent Inventory - GitHub Copilot Harness",
                fetch(
                    AGENT,
                    agent_attrs,
                    "pvci_displayname",
                    desc=False,
                    filt='<filter type="and"><condition attribute="pvci_harness" operator="eq" value="github_copilot" /></filter>',
                ),
                grid(ac, "pvci_agentinventoryid", agent_cols),
            )
        )

        threshold_cols = [
            ("pvci_resourceid", 240),
            ("pvci_environmentid", 240),
            ("pvci_resourceconsumption", 110),
            ("pvci_limit", 110),
            ("pvci_notificationthreshold", 100),
            ("pvci_notifyifovercapacity", 90),
            ("pvci_stopifovercapacity", 90),
            ("pvci_stopresource", 90),
            ("pvci_capturedon", 140),
        ]
        results.append(
            upsert_view(
                s, base, token, THRESHOLD, "Agent Credit Thresholds - Latest",
                fetch(
                    THRESHOLD,
                    [c[0] for c in threshold_cols] + ["pvci_agentthresholdsnapshotid"],
                    "pvci_capturedon",
                ),
                grid(thc, "pvci_agentthresholdsnapshotid", threshold_cols),
            )
        )

        governance_sync_cols = [
            ("pvci_name", 220),
            ("pvci_status", 90),
            ("pvci_startedon", 140),
            ("pvci_completedon", 140),
            ("pvci_thresholdcount", 100),
            ("pvci_createdcount", 90),
            ("pvci_updatedcount", 90),
            ("pvci_rejectedcount", 90),
        ]
        results.append(
            upsert_view(
                s, base, token, GOVERNANCE_SYNC, "Credit Governance Sync Runs - Latest",
                fetch(
                    GOVERNANCE_SYNC,
                    [c[0] for c in governance_sync_cols] + ["pvci_governancesyncrunid"],
                    "pvci_startedon",
                ),
                grid(gsc, "pvci_governancesyncrunid", governance_sync_cols),
            )
        )

        sync_cols = [
            ("pvci_name", 220),
            ("pvci_source", 120),
            ("pvci_startedon", 130),
            ("pvci_completedon", 130),
            ("pvci_status", 90),
            ("pvci_sourcecount", 90),
            ("pvci_createdcount", 90),
            ("pvci_updatedcount", 90),
            ("pvci_rejectedcount", 90),
        ]
        results.append(
            upsert_view(
                s, base, token, CREDIT_SYNC, "Credit Sync Runs - Latest",
                fetch(
                    CREDIT_SYNC,
                    [c[0] for c in sync_cols] + ["pvci_creditsyncrunid"],
                    "pvci_startedon",
                ),
                grid(csc, "pvci_creditsyncrunid", sync_cols),
            )
        )

        user_cols = [
            ("pvci_name", 220),
            ("pvci_userid", 260),
            ("pvci_usagedate", 120),
            ("pvci_billedcredits", 110),
            ("pvci_nonbilledcredits", 120),
            ("pvci_nameresolutionstatus", 150),
        ]
        results.append(
            upsert_view(
                s, base, token, USER_USAGE, "Credit User Usage - Latest",
                fetch(USER_USAGE, [c[0] for c in user_cols] + ["pvci_credituserusageid"], "pvci_usagedate"),
                grid(uuc, "pvci_credituserusageid", user_cols),
            )
        )

        privacy_cols = [
            ("pvci_name", 240),
            ("pvci_revealusernames", 140),
            ("pvci_approvedbyname", 180),
            ("pvci_approvedon", 140),
            ("pvci_revokedon", 140),
        ]
        results.append(
            upsert_view(
                s, base, token, PRIVACY, "Credit Privacy Approval",
                fetch(PRIVACY, [c[0] for c in privacy_cols] + ["pvci_creditprivacysettingid"], "pvci_name", desc=False),
                grid(pc, "pvci_creditprivacysettingid", privacy_cols),
            )
        )
        results.append(
            upsert_view(
                s, base, token, SESSION, "Sessions - Production Only",
                fetch(SESSION, sess_attrs, "pvci_startdatetimeutc",
                      filt='<filter type="and"><condition attribute="pvci_istestmode" operator="ne" value="1" /></filter>'),
                grid(sc, "pvci_transcriptsessionid", sess_cols),
            )
        )
        results.append(
            upsert_view(
                s, base, token, SESSION, "Sessions - Unresolved User",
                fetch(SESSION, sess_attrs, "pvci_startdatetimeutc",
                      filt='<filter type="and"><condition attribute="pvci_correlationstatus" operator="ne" value="exact" /></filter>'),
                grid(sc, "pvci_transcriptsessionid", sess_cols),
            )
        )

        turn_cols = [
            ("pvci_name", 160),
            ("pvci_speaker", 80),
            ("pvci_activitytype", 110),
            ("pvci_eventname", 180),
            ("pvci_turntext", 380),
            ("pvci_timestamputc", 140),
        ]
        turn_attrs = [c[0] for c in turn_cols] + ["pvci_transcriptturnid"]
        results.append(
            upsert_view(
                s, base, token, TURN, "Active Transcript Turns",
                fetch(TURN, turn_attrs, "pvci_timestamputc", desc=False),
                grid(tc, "pvci_transcriptturnid", turn_cols),
            )
        )
        results.append(
            upsert_view(
                s, base, token, TURN, "Turns - Conversation Only",
                fetch(TURN, turn_attrs, "pvci_timestamputc", desc=False,
                      filt='<filter type="and"><condition attribute="pvci_activitytype" operator="eq" value="message" /></filter>'),
                grid(tc, "pvci_transcriptturnid", turn_cols),
            )
        )
        results.append(
            upsert_view(
                s, base, token, TURN, "Turns - Agent Reasoning (DynamicPlan)",
                fetch(TURN, turn_attrs, "pvci_timestamputc", desc=False,
                      filt='<filter type="and"><condition attribute="pvci_eventname" operator="like" value="DynamicPlan%" /></filter>'),
                grid(tc, "pvci_transcriptturnid", turn_cols),
            )
        )

        id_cols = [
            ("pvci_name", 180),
            ("pvci_userprincipalname", 260),
            ("pvci_aadobjectid", 260),
            ("pvci_correlationconfidence", 120),
            ("pvci_lastseenon", 140),
        ]
        results.append(
            upsert_view(
                s, base, token, IDENTITY, "Active Identity Map",
                fetch(IDENTITY, [c[0] for c in id_cols] + ["pvci_transcriptidentitymapid"], "pvci_lastseenon"),
                grid(ic, "pvci_transcriptidentitymapid", id_cols),
            )
        )

        for r in results:
            print(" ", r)

        pub = s.post(
            f"{base}/PublishXml",
            headers=headers(token),
            json={"ParameterXml": "<importexportxml><entities>"
                                  + "".join(
                                      f"<entity>{entity}</entity>"
                                      for entity in (
                                          SESSION, TURN, IDENTITY, AGENT, CREDIT, CAPACITY, CREDIT_SYNC,
                                          USER_USAGE, PRIVACY,
                                      )
                                  )
                                  + "</entities></importexportxml>"},
            timeout=180,
        )
        print("publish:", pub.status_code if pub.ok else f"{pub.status_code} {pub.text[:200]}")


if __name__ == "__main__":
    main()
