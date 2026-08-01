#!/usr/bin/env python3
"""Attempt correlation between Monitor SessionId candidates and Dataverse conversationtranscripts IDs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dv_token import get_token  # noqa: E402


def acquire_token(tenant_id: str, client_id: str, scope: str) -> str:
    return get_token(tenant_id, client_id, scope)


def extract_guid_candidates(session_id: str) -> list[str]:
    if not session_id:
        return []
    return re.findall(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", session_id)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/transcript_solution_config.sample.json")
    parser.add_argument("--normalized", default="output/transcript_insights/normalized_sessions.json")
    parser.add_argument("--output", default="output/transcript_insights/correlation_report.json")
    args = parser.parse_args()

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    rows = json.loads(Path(args.normalized).read_text(encoding="utf-8"))

    dataverse_url = cfg["dataverseUrl"].rstrip("/")
    tenant_id = cfg["tenantId"]
    client_id = cfg["oauth"]["clientId"]
    scope = cfg["oauth"].get("dataverseScope", f"{dataverse_url}/.default")

    token = acquire_token(tenant_id, client_id, scope)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "OData-Version": "4.0",
        "OData-MaxVersion": "4.0",
    }

    results = []
    with requests.Session() as s:
        for row in rows:
            sid = row.get("monitor_session_id")
            candidates = extract_guid_candidates(sid or "")
            candidate_hits = []
            for guid in candidates:
                url = (
                    f"{dataverse_url}/api/data/v9.1/conversationtranscripts({guid})"
                    "?$select=conversationtranscriptid,createdon,modifiedon"
                )
                resp = s.get(url, headers=headers, timeout=60)
                candidate_hits.append(
                    {
                        "candidate_guid": guid,
                        "status": resp.status_code,
                        "matched": resp.ok,
                    }
                )

            results.append(
                {
                    "monitor_session_id": sid,
                    "guid_candidates": candidates,
                    "candidate_hits": candidate_hits,
                }
            )

    summary = {
        "total_sessions": len(results),
        "sessions_with_guid_candidates": sum(1 for r in results if r["guid_candidates"]),
        "sessions_with_match": sum(1 for r in results if any(h["matched"] for h in r["candidate_hits"])),
    }

    out = {
        "summary": summary,
        "details": results,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "output": str(out_path), "summary": summary}, indent=2))


if __name__ == "__main__":
    main()
