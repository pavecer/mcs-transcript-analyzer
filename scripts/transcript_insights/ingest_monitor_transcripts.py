#!/usr/bin/env python3
"""Ingest Copilot Studio Monitor transcripts and export normalized artifacts.

This script focuses on the observed Monitor endpoints from HAR:
- /api/botmanagement/v1/transcript/sessionwindows
- /api/botmanagement/v1/transcript

It does not require Dataverse transcript table access and can be used when
`conversationtranscripts` is empty.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from dateutil import parser as date_parser

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dv_token import get_token  # noqa: E402


@dataclass
class AuthConfig:
    client_id: str
    scope: str
    tenant_id: str


@dataclass
class RuntimeConfig:
    dataverse_url: str
    gateway_base_url: str
    environment_id: str
    bot_id: str
    lookback_days: int
    max_windows_per_run: int
    include_raw_csv: bool


def _load_config(path: Path) -> tuple[AuthConfig, RuntimeConfig]:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    auth = AuthConfig(
        client_id=cfg["oauth"]["clientId"],
        scope=cfg["oauth"]["scope"],
        tenant_id=cfg["tenantId"],
    )
    runtime = RuntimeConfig(
        dataverse_url=cfg["dataverseUrl"],
        gateway_base_url=cfg["copilotStudioGatewayBaseUrl"],
        environment_id=cfg["environmentId"],
        bot_id=cfg["botId"],
        lookback_days=int(cfg["ingestion"].get("defaultLookbackDays", 2)),
        max_windows_per_run=int(cfg["ingestion"].get("maxWindowsPerRun", 30)),
        include_raw_csv=bool(cfg["ingestion"].get("includeRawCsv", True)),
    )
    return auth, runtime


def _acquire_token(auth: AuthConfig) -> str:
    return get_token(auth.tenant_id, auth.client_id, auth.scope)


def _monitor_headers(token: str, runtime: RuntimeConfig) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "text/csv, application/json, */*",
        "x-ms-bot-id": runtime.bot_id,
        "x-ms-environment-id": runtime.environment_id,
        "x-ms-client-request-id": f"pvci-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "Origin": "https://copilotstudio.microsoft.com",
        "Referer": "https://copilotstudio.microsoft.com/",
    }


def _get_session_windows(
    session: requests.Session,
    runtime: RuntimeConfig,
    headers: dict[str, str],
    start_utc: datetime,
    end_utc: datetime,
) -> list[dict[str, str]]:
    url = (
        f"{runtime.gateway_base_url}/api/botmanagement/v1/transcript/sessionwindows"
        f"?startTime={start_utc.isoformat().replace('+00:00', 'Z')}"
        f"&endTime={end_utc.isoformat().replace('+00:00', 'Z')}"
        "&isV2=true"
    )
    resp = session.get(url, headers=headers, timeout=120)
    resp.raise_for_status()
    windows = resp.json()
    return windows[: runtime.max_windows_per_run]


def _get_transcript_csv(
    session: requests.Session,
    runtime: RuntimeConfig,
    headers: dict[str, str],
    window_start: str,
    window_end: str,
) -> str:
    url = (
        f"{runtime.gateway_base_url}/api/botmanagement/v1/transcript"
        f"?startTime={window_start}"
        f"&endTime={window_end}"
        "&isV2=true"
    )
    resp = session.get(url, headers=headers, timeout=120)
    resp.raise_for_status()
    return resp.text


def _parse_chat_transcript(chat_transcript: str) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    if not chat_transcript:
        return turns

    # Pattern observed in HAR CSV: "User says: ...;Agent says: ...;"
    for idx, piece in enumerate(chat_transcript.split(";")):
        part = piece.strip()
        if not part:
            continue
        speaker = "system"
        text = part
        if part.lower().startswith("user says:"):
            speaker = "user"
            text = part[len("User says:") :].strip()
        elif part.lower().startswith("agent says:"):
            speaker = "agent"
            text = part[len("Agent says:") :].strip()

        turns.append(
            {
                "turn_index": idx,
                "speaker": speaker,
                "text": text,
            }
        )
    return turns


def _extract_possible_conversation_ids(raw_session_id: str) -> dict[str, str | None]:
    # SessionId contains an opaque composite value. Keep original and attempt heuristics.
    guid_match = re.search(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        raw_session_id or "",
    )
    return {
        "monitor_session_id": raw_session_id,
        "embedded_guid": guid_match.group(0) if guid_match else None,
    }


def _normalize_rows(csv_text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(csv_text))
    normalized: list[dict[str, Any]] = []

    for row in reader:
        raw_sid = row.get("SessionId", "")
        id_parts = _extract_possible_conversation_ids(raw_sid)
        turns = _parse_chat_transcript(row.get("ChatTranscript") or "")

        start_raw = row.get("StartDateTime(UTC)")
        start_iso = None
        if start_raw:
            try:
                start_iso = date_parser.parse(start_raw).astimezone(timezone.utc).isoformat()
            except Exception:
                start_iso = start_raw

        normalized.append(
            {
                "monitor_session_id": id_parts["monitor_session_id"],
                "embedded_guid": id_parts["embedded_guid"],
                "start_datetime_utc": start_iso,
                "session_outcome": row.get("SessionOutcome"),
                "outcome_reason": row.get("OutcomeReason"),
                "is_resolved_implied": row.get("IsResolvedImplied"),
                "turn_count": row.get("Turns"),
                "initial_user_message": row.get("InitialUserMessage"),
                "topic_name": row.get("TopicName"),
                "topic_id": row.get("TopicId"),
                "channel": row.get("Channel"),
                "csat": row.get("CSAT"),
                "comments": row.get("Comments"),
                "chat_transcript_raw": row.get("ChatTranscript"),
                "parsed_turns": turns,
            }
        )

    return normalized


def _write_outputs(
    output_dir: Path,
    normalized_rows: list[dict[str, Any]],
    include_raw_csv: bool,
    raw_csv_by_window: list[tuple[str, str, str]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "session_count": len(normalized_rows),
        "channels": sorted({r.get("channel") for r in normalized_rows if r.get("channel")}),
        "outcomes": sorted(
            {r.get("session_outcome") for r in normalized_rows if r.get("session_outcome")}
        ),
    }

    (output_dir / "normalized_sessions.json").write_text(
        json.dumps(normalized_rows, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    if include_raw_csv:
        raw_dir = output_dir / "raw_csv"
        raw_dir.mkdir(exist_ok=True)
        for idx, (ws, we, csv_payload) in enumerate(raw_csv_by_window, start=1):
            (raw_dir / f"window_{idx}_{ws}_{we}.csv".replace(":", "-")).write_text(
                csv_payload,
                encoding="utf-8",
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="config/transcript_solution_config.sample.json",
        help="Path to config JSON",
    )
    parser.add_argument(
        "--output-dir",
        default="output/transcript_insights",
        help="Output folder for normalized artifacts",
    )
    args = parser.parse_args()

    auth, runtime = _load_config(Path(args.config))
    token = _acquire_token(auth)
    headers = _monitor_headers(token, runtime)

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=runtime.lookback_days)

    with requests.Session() as session:
        windows = _get_session_windows(session, runtime, headers, start, now)
        normalized: list[dict[str, Any]] = []
        raw_by_window: list[tuple[str, str, str]] = []

        for w in windows:
            ws = w["startTime"]
            we = w["endTime"]
            csv_payload = _get_transcript_csv(session, runtime, headers, ws, we)
            rows = _normalize_rows(csv_payload)
            normalized.extend(rows)
            raw_by_window.append((ws, we, csv_payload))

    _write_outputs(Path(args.output_dir), normalized, runtime.include_raw_csv, raw_by_window)

    print(
        json.dumps(
            {
                "status": "ok",
                "output_dir": args.output_dir,
                "session_count": len(normalized),
                "window_count": len(raw_by_window),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
