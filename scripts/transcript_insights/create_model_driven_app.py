#!/usr/bin/env python3
"""Create the 'Conversation Insights' model-driven app (sitemap + app module)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dv_token import get_token_from_config, require_authorized_config  # noqa: E402

SOLUTION = "pvConversationInsights"
APP_UNIQUE = "pvci_conversationinsights"
APP_NAME = "Conversation Insights"
TABLES = [
    "pvci_transcriptsession",
    "pvci_transcriptturn",
    "pvci_transcriptidentitymap",
    "pvci_environmentinventory",
    "pvci_inventorysyncrun",
    "pvci_agentthresholdsnapshot",
    "pvci_governancesyncrun",
    "pvci_thresholdchangerequest",
    "pvci_agentinventory",
    "pvci_creditusage",
    "pvci_creditcapacitysnapshot",
    "pvci_creditsyncrun",
    "pvci_credituserusage",
    "pvci_creditprivacysetting",
]

SITEMAP_XML = """<SiteMap IntroducedVersion="1.0">
  <Area Id="pvci_area" Title="Conversation Insights" ShowGroups="true">
    <Group Id="pvci_group_analysis" Title="Analysis">
      <SubArea Id="pvci_sa_sessions" Entity="pvci_transcriptsession" Title="Sessions" />
      <SubArea Id="pvci_sa_turns" Entity="pvci_transcriptturn" Title="Turns" />
      <SubArea Id="pvci_sa_identity" Entity="pvci_transcriptidentitymap" Title="Users" />
    </Group>
        <Group Id="pvci_group_credits" Title="Credits and Capacity">
            <SubArea Id="pvci_sa_environments" Entity="pvci_environmentinventory" Title="Environment Inventory" />
            <SubArea Id="pvci_sa_inventorysync" Entity="pvci_inventorysyncrun" Title="Inventory Sync Runs" />
            <SubArea Id="pvci_sa_thresholds" Entity="pvci_agentthresholdsnapshot" Title="Agent Credit Limits" />
            <SubArea Id="pvci_sa_governancesync" Entity="pvci_governancesyncrun" Title="Governance Sync Runs" />
            <SubArea Id="pvci_sa_thresholdrequests" Entity="pvci_thresholdchangerequest" Title="Threshold Requests" />
            <SubArea Id="pvci_sa_creditusage" Entity="pvci_creditusage" Title="Credit Usage" />
            <SubArea Id="pvci_sa_capacity" Entity="pvci_creditcapacitysnapshot" Title="Capacity" />
            <SubArea Id="pvci_sa_agents" Entity="pvci_agentinventory" Title="Agent Inventory" />
            <SubArea Id="pvci_sa_creditsync" Entity="pvci_creditsyncrun" Title="Sync Runs" />
            <SubArea Id="pvci_sa_userusage" Entity="pvci_credituserusage" Title="User Consumption" />
            <SubArea Id="pvci_sa_privacy" Entity="pvci_creditprivacysetting" Title="Privacy Approval" />
        </Group>
  </Area>
</SiteMap>"""


def hdr(token: str, solution: str | None = None) -> dict[str, str]:
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


def eid(resp: requests.Response) -> str:
    loc = resp.headers.get("OData-EntityId") or resp.headers.get("odata-entityid") or ""
    return loc.split("(")[-1].split(")")[0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="config/transcript_solution_config.dev.json")
    args = ap.parse_args()
    require_authorized_config(args.config)

    token, dv_url = get_token_from_config(args.config)
    base = f"{dv_url}/api/data/v9.1"

    with requests.Session() as s:
        # App module
        q = s.get(f"{base}/appmodules?$select=appmoduleid,name&$filter=uniquename eq '{APP_UNIQUE}'&$top=1",
                  headers=hdr(token), timeout=60)
        rows = q.json().get("value", []) if q.ok else []
        if rows:
            app_id = rows[0]["appmoduleid"]
            print(f"app exists: {app_id}")
        else:
            icon = s.get(
                f"{base}/webresourceset?$select=webresourceid"
                "&$filter=name eq 'msdyn_CopilotIcon.svg'&$top=1",
                headers=hdr(token), timeout=60,
            )
            icon_rows = icon.json().get("value", []) if icon.ok else []
            if not icon_rows:
                icon = s.get(f"{base}/webresourceset?$select=webresourceid&$filter=webresourcetype eq 11&$top=1",
                             headers=hdr(token), timeout=60)
                icon_rows = icon.json().get("value", []) if icon.ok else []

            body: dict[str, Any] = {
                "name": APP_NAME,
                "uniquename": APP_UNIQUE,
                "description": "Analyse Copilot Studio conversation transcripts",
                "clienttype": 4,
                "navigationtype": 1,
            }
            if icon_rows:
                body["webresourceid"] = icon_rows[0]["webresourceid"]

            r = s.post(f"{base}/appmodules", headers=hdr(token, SOLUTION), json=body, timeout=90)
            if not r.ok:
                print(f"FAILED create appmodule: {r.status_code} {r.text[:400]}")
                return
            app_id = eid(r)
            print(f"app created: {app_id}")

        # Sitemap
        q = s.get(f"{base}/sitemaps?$select=sitemapid&$filter=sitemapnameunique eq '{APP_UNIQUE}_sitemap'&$top=1",
                  headers=hdr(token), timeout=60)
        rows = q.json().get("value", []) if q.ok else []
        if rows:
            sitemap_id = rows[0]["sitemapid"]
            s.patch(f"{base}/sitemaps({sitemap_id})", headers=hdr(token, SOLUTION),
                    json={"sitemapxml": SITEMAP_XML}, timeout=90)
            print(f"sitemap updated: {sitemap_id}")
        else:
            r = s.post(f"{base}/sitemaps", headers=hdr(token, SOLUTION), json={
                "sitemapname": APP_NAME,
                "sitemapnameunique": f"{APP_UNIQUE}_sitemap",
                "sitemapxml": SITEMAP_XML,
            }, timeout=90)
            if not r.ok:
                print(f"FAILED create sitemap: {r.status_code} {r.text[:400]}")
                return
            sitemap_id = eid(r)
            print(f"sitemap created: {sitemap_id}")

        # Components
        components: list[dict[str, Any]] = [
            {"@odata.type": "Microsoft.Dynamics.CRM.sitemap", "sitemapid": sitemap_id}
        ]
        for t in TABLES:
            m = s.get(f"{base}/EntityDefinitions(LogicalName='{t}')?$select=MetadataId",
                      headers=hdr(token), timeout=60)
            if m.ok:
                components.append(
                    {"@odata.type": "Microsoft.Dynamics.CRM.entity", "entityid": m.json()["MetadataId"]}
                )

        r = s.post(f"{base}/AddAppComponents", headers=hdr(token),
                   json={"AppId": app_id, "Components": components}, timeout=180)
        print("AddAppComponents:", "ok" if r.ok else f"{r.status_code} {r.text[:400]}")

        r = s.post(f"{base}/PublishXml", headers=hdr(token), json={
            "ParameterXml": "<importexportxml><entities>"
                            + "".join(f"<entity>{t}</entity>" for t in TABLES)
                            + "</entities><appmodules><appmodule>"
                            + app_id
                            + "</appmodule></appmodules></importexportxml>"
        }, timeout=300)
        print("publish:", "ok" if r.ok else f"{r.status_code} {r.text[:300]}")
        print(f"\nApp URL: {dv_url}/main.aspx?appid={app_id}")


if __name__ == "__main__":
    main()
