#!/usr/bin/env python3
"""Rebuild the main forms so a session can be analysed tab-by-tab.

Session form tabs: Summary | Conversation | Agent Reasoning | Full Transcript JSON | Activities
Turn form tabs:    Turn | Value JSON
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path
from xml.sax.saxutils import escape

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dv_token import get_token_from_config  # noqa: E402

SOLUTION = "pvConversationInsights"
SESSION = "pvci_transcriptsession"
TURN = "pvci_transcriptturn"
REL_SESSION_TURN = "pvci_transcriptsession_transcriptturn"

NS = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")

TEXT = "{4273EDBD-AC1D-40d3-9FB2-095C621B552D}"
MEMO = "{E0DECE4B-6FC8-4a8f-A065-082708572369}"
DATE = "{5B773807-9FB2-42db-97C3-7A91EFF8ADFF}"
INT = "{C6D124CA-7EDA-4a60-AEA9-7FB8D318B68F}"
BOOL = "{B0C6723A-8503-4fd7-BB28-C8A06AC933C2}"
LOOKUP = "{270BD3DB-D9AF-4782-9025-509E298DEC0A}"
GRID = "{E7A81278-8635-4d9e-8D4D-59480B391C5B}"

PCF_SUFFIX = "PvciControls.JsonViewer"
# Resolved from Dataverse at runtime; pac pcf push prepends the publisher prefix.
PCF_NAME = PCF_SUFFIX

# Populated by field_cell(pcf=True); consumed by form_xml().
_pcf_bindings: list[tuple[str, str, int, int]] = []


def reset_bindings() -> None:
    _pcf_bindings.clear()


def control_descriptions() -> str:
    if not _pcf_bindings or not PCF_NAME:
        return ""
    blocks = []
    for uid, fieldname, depth, height in _pcf_bindings:
        controls = "".join(
            f'<customControl name="{PCF_NAME}" formFactor="{ff}">'
            f"<parameters>"
            f'<jsonValue>{fieldname}</jsonValue>'
            f'<startCollapsedDepth static="true" type="Whole.None">{depth}</startCollapsedDepth>'
            f'<viewerHeight static="true" type="Whole.None">{height}</viewerHeight>'
            f"</parameters></customControl>"
            for ff in (0, 1, 2)
        )
        blocks.append(f'<controlDescription forControl="{uid}">{controls}</controlDescription>')
    return f"<controlDescriptions>{''.join(blocks)}</controlDescriptions>"


def gid(seed: str) -> str:
    return "{" + str(uuid.uuid5(NS, seed)) + "}"


def label(text: str) -> str:
    return f'<labels><label description="{escape(text)}" languagecode="1033" /></labels>'


def field_cell(
    seed: str,
    name: str,
    classid: str,
    caption: str,
    rowspan: int = 1,
    pcf: bool = False,
    depth: int = 2,
    height: int = 520,
    disabled: bool = False,
) -> str:
    rs = f' rowspan="{rowspan}" colspan="1"' if rowspan > 1 else ""
    uid = gid(seed + "ctrl")
    if pcf:
        _pcf_bindings.append((uid, name, depth, height))
    return (
        f'<cell id="{gid(seed)}"{rs} showlabel="true">'
        f"{label(caption)}"
        f'<control id="{name}" uniqueid="{uid}" classid="{classid}" '
        f'datafieldname="{name}" disabled="{str(disabled).lower()}" />'
        f"</cell>"
    )


def grid_cell(seed: str, ctrl_id: str, target: str, view_id: str, caption: str, rowspan: int = 18) -> str:
    return (
        f'<cell id="{gid(seed)}" rowspan="{rowspan}" colspan="2" showlabel="true">'
        f"{label(caption)}"
        f'<control id="{ctrl_id}" classid="{GRID}" indicationOfSubgrid="true" uniqueid="{gid(seed + "u")}">'
        f"<parameters>"
        f"<TargetEntityType>{target}</TargetEntityType>"
        f"<ViewId>{{{view_id}}}</ViewId>"
        f"<AutoExpand>Fixed</AutoExpand>"
        f"<EnableQuickFind>true</EnableQuickFind>"
        f"<EnableViewPicker>true</EnableViewPicker>"
        f"<EnableChartPicker>false</EnableChartPicker>"
        f"<RecordsPerPage>50</RecordsPerPage>"
        f"<RelationshipName>{REL_SESSION_TURN}</RelationshipName>"
        f"</parameters></control></cell>"
    )


def section(seed: str, caption: str, rows_html: str, columns: str = "11", showlabel: str = "true") -> str:
    return (
        f'<section id="{gid(seed)}" name="{seed}" showlabel="{showlabel}" showbar="false" '
        f'columns="{columns}" labelwidth="140" celllabelalignment="Left" celllabelposition="Left">'
        f"{label(caption)}<rows>{rows_html}</rows></section>"
    )


def tab(seed: str, caption: str, sections_html: str, expanded: str = "true") -> str:
    return (
        f'<tab id="{gid(seed)}" name="{seed}" verticallayout="true" showlabel="true" expanded="{expanded}">'
        f"{label(caption)}"
        f'<columns><column width="100%"><sections>{sections_html}</sections></column></columns>'
        f"</tab>"
    )


def row(*cells: str) -> str:
    return "<row>" + "".join(cells) + "</row>"


def session_formxml(view_all: str, view_conv: str, view_plan: str) -> str:
    summary = section(
        "sec_summary",
        "Session",
        row(field_cell("c_name", "pvci_name", TEXT, "Name"),
            field_cell("c_user", "pvci_userid", LOOKUP, "User"))
        + row(field_cell("c_upn", "pvci_userupn", TEXT, "User UPN"),
              field_cell("c_aad", "pvci_useraadobjectid", TEXT, "Entra Object Id"))
        + row(field_cell("c_chan", "pvci_channel", TEXT, "Channel"),
              field_cell("c_bot", "pvci_botname", TEXT, "Agent"))
        + row(field_cell("c_start", "pvci_startdatetimeutc", DATE, "Started (UTC)"),
              field_cell("c_end", "pvci_enddatetimeutc", DATE, "Ended (UTC)"))
        + row(field_cell("c_dur", "pvci_durationseconds", INT, "Duration (s)"),
              field_cell("c_msg", "pvci_messagecount", INT, "Messages"))
        + row(field_cell("c_user_t", "pvci_userturncount", INT, "User turns"),
              field_cell("c_agent_t", "pvci_agentturncount", INT, "Agent turns"))
        + row(field_cell("c_acts", "pvci_activitycount", INT, "Activities"),
              field_cell("c_ev", "pvci_eventcount", INT, "Events"))
        + row(field_cell("c_test", "pvci_istestmode", BOOL, "Test mode"),
              field_cell("c_anom", "pvci_multiuseranomaly", BOOL, "Multi-user anomaly"))
        + row(field_cell("c_corr", "pvci_correlationstatus", TEXT, "Correlation"),
              field_cell("c_trunc", "pvci_payloadtruncated", BOOL, "Payload truncated"))
        + row(field_cell("c_outcome", "pvci_sessionoutcome", TEXT, "Outcome"),
              field_cell("c_reason", "pvci_outcomereason", TEXT, "Outcome reason"))
        + row(field_cell("c_implied", "pvci_isresolvedimplied", TEXT, "Implied success"),
              field_cell("c_turns", "pvci_turncount", INT, "Turn count"))
        + row(field_cell("c_first", "pvci_firstresponsems", INT, "First response (ms)"),
              field_cell("c_avg", "pvci_avgresponsems", INT, "Avg response (ms)"))
        + row(field_cell("c_maxr", "pvci_maxresponsems", INT, "Slowest response (ms)"),
              field_cell("c_tools", "pvci_toolcallcount", INT, "Tool calls"))
        + row(field_cell("c_toolerr", "pvci_toolerrorcount", INT, "Tool failures"),
              field_cell("c_maxtool", "pvci_maxtoolms", INT, "Slowest tool (ms)"))
        + row(field_cell("c_flowruns", "pvci_flowruncount", INT, "Flow runs matched"),
              field_cell("c_flowfail", "pvci_flowrunfailurecount", INT, "Flow run failures"))
        + row(field_cell("c_tid", "pvci_transcriptid", TEXT, "Transcript Id"),
              field_cell("c_ing", "pvci_ingestedon", DATE, "Ingested (UTC)")),
    )
    first_last = section(
        "sec_firstlast",
        "Opening / closing",
        row(field_cell("c_first", "pvci_initialusermessage", MEMO, "First user message", rowspan=4))
        + row(field_cell("c_last", "pvci_lastagentmessage", MEMO, "Last agent message", rowspan=4)),
        columns="1",
    )

    conv = section(
        "sec_conv_json",
        "Conversation (clean JSON)",
        row(field_cell("c_convjson", "pvci_conversationjson", MEMO, "Conversation JSON",
                       rowspan=22, pcf=True, depth=3, height=520)),
        columns="1",
    ) + section(
        "sec_conv_grid",
        "Message turns",
        row(grid_cell("c_convgrid", "convturns", TURN, view_conv, "Messages")),
        columns="1",
    )

    reasoning = section(
        "sec_plan_json",
        "DynamicPlan events",
        row(field_cell("c_planjson", "pvci_planeventsjson", MEMO, "Plan events JSON",
                       rowspan=22, pcf=True, depth=3, height=520)),
        columns="1",
    ) + section(
        "sec_plan_grid",
        "Reasoning turns",
        row(grid_cell("c_plangrid", "planturns", TURN, view_plan, "DynamicPlan activities")),
        columns="1",
    )

    raw = section(
        "sec_raw",
        "Full activity stream - no Dataverse wrapper, no metadata",
        row(field_cell("c_actsjson", "pvci_activitiesjson", MEMO, "Activities JSON",
                       rowspan=30, pcf=True, depth=2, height=650)),
        columns="1",
    ) + section(
        "sec_meta",
        "Transcript metadata (separate)",
        row(field_cell("c_metajson", "pvci_metadatajson", MEMO, "Metadata JSON",
                       rowspan=5, pcf=True, depth=3, height=180)),
        columns="1",
    )

    activities = section(
        "sec_all_grid",
        "All stored activities",
        row(grid_cell("c_allgrid", "allturns", TURN, view_all, "Activities", rowspan=26)),
        columns="1",
    )

    tools = section(
        "sec_tools_json",
        "Tool and connector calls - duration, output, exception",
        row(field_cell("c_toolsjson", "pvci_toolcallsjson", MEMO, "Tool calls JSON",
                       rowspan=26, pcf=True, depth=3, height=600)),
        columns="1",
    )

    flows = section(
        "sec_flows_json",
        "Correlated Power Automate runs - matched by time overlap",
        row(field_cell("c_flowsjson", "pvci_flowrunsjson", MEMO, "Flow runs JSON",
                       rowspan=26, pcf=True, depth=4, height=600)),
        columns="1",
    )

    tabs = (
        tab("tab_summary", "Summary", summary + first_last)
        + tab("tab_conversation", "Conversation", conv)
        + tab("tab_reasoning", "Agent Reasoning", reasoning)
        + tab("tab_tools", "Tool Calls", tools)
        + tab("tab_flows", "Flow Runs", flows)
        + tab("tab_rawjson", "Full Transcript JSON", raw)
        + tab("tab_activities", "Activities", activities)
    )
    return f"<form><tabs>{tabs}</tabs>{control_descriptions()}</form>"


def turn_formxml() -> str:
    main = section(
        "t_sec_main",
        "Activity",
        row(field_cell("t_name", "pvci_name", TEXT, "Name"),
            field_cell("t_session", "pvci_sessionid", LOOKUP, "Session"))
        + row(field_cell("t_idx", "pvci_turnindex", INT, "Index"),
              field_cell("t_type", "pvci_activitytype", TEXT, "Activity type"))
        + row(field_cell("t_speaker", "pvci_speaker", TEXT, "Speaker"),
              field_cell("t_role", "pvci_role", INT, "Role"))
        + row(field_cell("t_event", "pvci_eventname", TEXT, "Event name"),
              field_cell("t_ts", "pvci_timestamputc", DATE, "Timestamp (UTC)"))
        + row(field_cell("t_chan", "pvci_channelid", TEXT, "Channel"),
              field_cell("t_aad", "pvci_aadobjectid", TEXT, "Entra Object Id"))
        + row(field_cell("t_lat", "pvci_latencyms", INT, "Reply latency (ms)")),
    ) + section(
        "t_sec_text",
        "Text",
        row(field_cell("t_text", "pvci_turntext", MEMO, "Text", rowspan=8)),
        columns="1",
    )
    payload = section(
        "t_sec_value",
        "Activity value payload",
        row(field_cell("t_value", "pvci_valuejson", MEMO, "Value JSON",
                       rowspan=30, pcf=True, depth=4, height=620)),
        columns="1",
    )
    tabs = f"{tab('t_tab_main', 'Turn', main)}{tab('t_tab_value', 'Value JSON', payload)}"
    return f"<form><tabs>{tabs}</tabs>{control_descriptions()}</form>"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="config/transcript_solution_config.dev.json")
    args = ap.parse_args()

    token, dv_url = get_token_from_config(args.config)
    base = f"{dv_url}/api/data/v9.1"
    h = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json; charset=utf-8",
        "OData-Version": "4.0",
        "OData-MaxVersion": "4.0",
        "MSCRM.SolutionUniqueName": SOLUTION,
    }
    hq = {k: v for k, v in h.items() if k != "MSCRM.SolutionUniqueName"}

    with requests.Session() as s:
        global PCF_NAME
        cc = s.get(
            f"{base}/customcontrols?$select=name&$filter=endswith(name,'{PCF_SUFFIX}')&$top=1",
            headers=hq, timeout=60,
        )
        found = cc.json().get("value", []) if cc.ok else []
        if found:
            PCF_NAME = found[0]["name"]
            print(f"pcf control: {PCF_NAME}")
        else:
            print(f"WARNING: custom control ending in '{PCF_SUFFIX}' not found - "
                  "run 'pac pcf push --publisher-prefix pvci' first. Falling back to plain text fields.")

        def view_id(name: str) -> str:
            r = s.get(f"{base}/savedqueries?$select=savedqueryid&$filter=name eq '{name}'&$top=1", headers=hq, timeout=60)
            v = r.json().get("value", [])
            return v[0]["savedqueryid"] if v else ""

        v_all = view_id("Active Transcript Turns")
        v_conv = view_id("Turns - Conversation Only")
        v_plan = view_id("Turns - Agent Reasoning (DynamicPlan)")
        print(f"views: all={v_all[:8]} conv={v_conv[:8]} plan={v_plan[:8]}")

        def main_form(entity: str) -> str | None:
            r = s.get(
                f"{base}/systemforms?$select=formid,name,type&$filter=objecttypecode eq '{entity}' and type eq 2&$top=1",
                headers=hq, timeout=60,
            )
            v = r.json().get("value", [])
            return v[0]["formid"] if v else None

        for entity, builder in ((SESSION, lambda: session_formxml(v_all, v_conv, v_plan)), (TURN, turn_formxml)):
            reset_bindings()
            xml = builder()
            fid = main_form(entity)
            if not fid:
                print(f"{entity}: no main form found")
                continue
            r = s.patch(f"{base}/systemforms({fid})", headers=h, json={"formxml": xml}, timeout=180)
            print(f"{entity} form {fid[:8]}: {'ok' if r.ok else f'{r.status_code} {r.text[:400]}'} "
                  f"({len(xml)} chars, {len(_pcf_bindings)} pcf bindings)")

        r = s.post(f"{base}/PublishXml", headers=hq, json={
            "ParameterXml": f"<importexportxml><entities><entity>{SESSION}</entity>"
                            f"<entity>{TURN}</entity></entities></importexportxml>"
        }, timeout=300)
        print("publish:", "ok" if r.ok else f"{r.status_code} {r.text[:300]}")


if __name__ == "__main__":
    main()
