#!/usr/bin/env python3
"""Build Dataverse upsert payload from normalized Monitor transcript data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        default="output/transcript_insights/normalized_sessions.json",
        help="Normalized sessions JSON",
    )
    parser.add_argument(
        "--output",
        default="output/transcript_insights/dataverse_upsert_payload.json",
        help="Output payload for Dataverse upsert",
    )
    args = parser.parse_args()

    rows = json.loads(Path(args.input).read_text(encoding="utf-8"))
    payload = []

    for row in rows:
        payload.append(
            {
                "pvci_monitor_sessionid": row.get("monitor_session_id"),
                "pvci_embeddedconversationguid": row.get("embedded_guid"),
                "pvci_startdatetimeutc": row.get("start_datetime_utc"),
                "pvci_sessionoutcome": row.get("session_outcome"),
                "pvci_outcomereason": row.get("outcome_reason"),
                "pvci_isresolvedimplied": row.get("is_resolved_implied"),
                "pvci_turncount": row.get("turn_count"),
                "pvci_initialusermessage": row.get("initial_user_message"),
                "pvci_topicname": row.get("topic_name"),
                "pvci_topicid": row.get("topic_id"),
                "pvci_channel": row.get("channel"),
                "pvci_csat": row.get("csat"),
                "pvci_comments": row.get("comments"),
                "pvci_rawchattranscript": row.get("chat_transcript_raw"),
                "pvci_parsedturnsjson": json.dumps(row.get("parsed_turns", []), ensure_ascii=False),
            }
        )

    Path(args.output).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": "ok", "rows": len(payload), "output": args.output}, indent=2))


if __name__ == "__main__":
    main()
