#!/usr/bin/env python3
"""Probe both transcript sources:
1) Copilot Studio Monitor endpoint
2) Dataverse v9.1 conversationtranscripts endpoint

Output is a single JSON report for troubleshooting and customer evidence.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dv_token import get_token  # noqa: E402


@dataclass
class ProbeConfig:
    tenant_id: str
    dataverse_url: str
    gateway_base_url: str
    environment_id: str
    bot_id: str
    client_id: str
    monitor_scope: str
    dataverse_scope: str


def load_config(path: Path) -> ProbeConfig:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    dataverse_url = cfg["dataverseUrl"].rstrip("/")
    return ProbeConfig(
        tenant_id=cfg["tenantId"],
        dataverse_url=dataverse_url,
        gateway_base_url=cfg["copilotStudioGatewayBaseUrl"].rstrip("/"),
        environment_id=cfg["environmentId"],
        bot_id=cfg["botId"],
        client_id=cfg["oauth"]["clientId"],
        monitor_scope=cfg["oauth"].get("scope", "https://service.powerapps.com/.default"),
        dataverse_scope=cfg["oauth"].get("dataverseScope", f"{dataverse_url}/.default"),
    )


def acquire_token(tenant_id: str, client_id: str, scope: str) -> str:
    return get_token(tenant_id, client_id, scope)


def monitor_headers(token: str, cfg: ProbeConfig) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "text/csv, application/json, */*",
        "x-ms-bot-id": cfg.bot_id,
        "x-ms-environment-id": cfg.environment_id,
        "Origin": "https://copilotstudio.microsoft.com",
        "Referer": "https://copilotstudio.microsoft.com/",
    }


def dataverse_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "OData-Version": "4.0",
        "OData-MaxVersion": "4.0",
    }


def probe_monitor(session: requests.Session, cfg: ProbeConfig, token: str, lookback_days: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=lookback_days)

    headers = monitor_headers(token, cfg)
    windows_url = (
        f"{cfg.gateway_base_url}/api/botmanagement/v1/transcript/sessionwindows"
        f"?startTime={start.isoformat().replace('+00:00','Z')}"
        f"&endTime={now.isoformat().replace('+00:00','Z')}"
        "&isV2=true"
    )

    windows_resp = session.get(windows_url, headers=headers, timeout=120)
    monitor_report: dict[str, Any] = {
        "sessionwindows": {
            "url": windows_url,
            "status": windows_resp.status_code,
            "ok": windows_resp.ok,
        },
        "transcript": None,
    }

    if not windows_resp.ok:
        monitor_report["sessionwindows"]["error"] = windows_resp.text[:2000]
        return monitor_report

    windows = windows_resp.json()
    monitor_report["sessionwindows"]["count"] = len(windows)
    monitor_report["sessionwindows"]["sample"] = windows[:3]

    if not windows:
        monitor_report["transcript"] = {"skipped": True, "reason": "No windows returned"}
        return monitor_report

    first = windows[-1]
    ws = first["startTime"]
    we = first["endTime"]
    transcript_url = (
        f"{cfg.gateway_base_url}/api/botmanagement/v1/transcript"
        f"?startTime={ws}&endTime={we}&isV2=true"
    )
    t_resp = session.get(transcript_url, headers=headers, timeout=120)
    transcript_info: dict[str, Any] = {
        "url": transcript_url,
        "status": t_resp.status_code,
        "ok": t_resp.ok,
        "window": {"startTime": ws, "endTime": we},
    }
    if t_resp.ok:
        reader = csv.DictReader(io.StringIO(t_resp.text))
        rows = list(reader)
        transcript_info["csv_headers"] = reader.fieldnames
        transcript_info["row_count"] = len(rows)
        transcript_info["sample_session_ids"] = [r.get("SessionId") for r in rows[:3]]
    else:
        transcript_info["error"] = t_resp.text[:2000]

    monitor_report["transcript"] = transcript_info
    return monitor_report


def probe_dataverse(
    session: requests.Session,
    cfg: ProbeConfig,
    token: str,
    conversationtranscript_id: str | None,
) -> dict[str, Any]:
    base = f"{cfg.dataverse_url}/api/data/v9.1"
    headers = dataverse_headers(token)

    report: dict[str, Any] = {}

    list_url = (
        f"{base}/conversationtranscripts"
        "?$select=conversationtranscriptid,createdon,modifiedon"
        "&$orderby=createdon desc&$top=5"
    )
    list_resp = session.get(list_url, headers=headers, timeout=120)
    report["list_recent"] = {
        "url": list_url,
        "status": list_resp.status_code,
        "ok": list_resp.ok,
    }

    if list_resp.ok:
        body = list_resp.json()
        values = body.get("value", [])
        report["list_recent"]["count"] = len(values)
        report["list_recent"]["sample_ids"] = [v.get("conversationtranscriptid") for v in values[:5]]
    else:
        report["list_recent"]["error"] = list_resp.text[:2000]

    if conversationtranscript_id:
        by_id_url = (
            f"{base}/conversationtranscripts({conversationtranscript_id})"
            "?$select=conversationtranscriptid,metadata,content,createdon,modifiedon"
        )
        by_id_resp = session.get(by_id_url, headers=headers, timeout=120)
        report["by_id"] = {
            "url": by_id_url,
            "status": by_id_resp.status_code,
            "ok": by_id_resp.ok,
        }
        if by_id_resp.ok:
            row = by_id_resp.json()
            report["by_id"]["fields"] = {
                "conversationtranscriptid": row.get("conversationtranscriptid"),
                "createdon": row.get("createdon"),
                "modifiedon": row.get("modifiedon"),
                "metadata_length": len(row.get("metadata") or ""),
                "content_length": len(row.get("content") or ""),
            }
        else:
            report["by_id"]["error"] = by_id_resp.text[:2000]
    else:
        report["by_id"] = {"skipped": True, "reason": "No conversationtranscriptId provided"}

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/transcript_solution_config.sample.json")
    parser.add_argument("--lookback-days", type=int, default=2)
    parser.add_argument("--conversationtranscript-id", default=None)
    parser.add_argument("--output", default="output/transcript_insights/dual_endpoint_probe_report.json")
    args = parser.parse_args()

    cfg = load_config(Path(args.config))

    monitor_report: dict[str, Any]
    dataverse_report: dict[str, Any]

    with requests.Session() as session:
        try:
            monitor_token = acquire_token(cfg.tenant_id, cfg.client_id, cfg.monitor_scope)
            monitor_report = probe_monitor(session, cfg, monitor_token, args.lookback_days)
        except Exception as exc:
            monitor_report = {
                "error": {
                    "stage": "token_or_request",
                    "message": str(exc),
                    "scope": cfg.monitor_scope,
                }
            }

        try:
            dataverse_token = acquire_token(cfg.tenant_id, cfg.client_id, cfg.dataverse_scope)
            dataverse_report = probe_dataverse(
                session,
                cfg,
                dataverse_token,
                args.conversationtranscript_id,
            )
        except Exception as exc:
            dataverse_report = {
                "error": {
                    "stage": "token_or_request",
                    "message": str(exc),
                    "scope": cfg.dataverse_scope,
                }
            }

    combined = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "tenant_id": cfg.tenant_id,
        "environment_id": cfg.environment_id,
        "monitor": monitor_report,
        "dataverse_v9_1": dataverse_report,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(combined, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "output": str(out_path)}, indent=2))


if __name__ == "__main__":
    main()
