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
            json={"ParameterXml": f"<importexportxml><entities><entity>{SESSION}</entity>"
                                  f"<entity>{TURN}</entity><entity>{IDENTITY}</entity></entities></importexportxml>"},
            timeout=180,
        )
        print("publish:", pub.status_code if pub.ok else f"{pub.status_code} {pub.text[:200]}")


if __name__ == "__main__":
    main()
