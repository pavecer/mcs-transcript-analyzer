#!/usr/bin/env python3
"""Extract transcript endpoint contract from a Copilot Studio HAR file."""

from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path


TRANSCRIPT_PATH = "/api/botmanagement/v1/transcript"
SESSION_WINDOWS_PATH = "/api/botmanagement/v1/transcript/sessionwindows"


def _safe_preview(value: str, limit: int = 220) -> str:
    text = value.replace("\n", "\\n")
    return text if len(text) <= limit else text[:limit] + "..."


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("har_file", help="Path to HAR file")
    args = parser.parse_args()

    har_path = Path(args.har_file)
    doc = json.loads(har_path.read_text(encoding="utf-8"))

    summary = {
        "session_windows": [],
        "transcript": [],
    }

    for entry in doc.get("log", {}).get("entries", []):
        request = entry.get("request", {})
        response = entry.get("response", {})
        url = request.get("url", "")
        method = request.get("method", "")
        status = response.get("status")
        body = (response.get("content") or {}).get("text") or ""

        if SESSION_WINDOWS_PATH in url:
            summary["session_windows"].append(
                {
                    "method": method,
                    "status": status,
                    "url": url,
                    "response_preview": _safe_preview(body),
                }
            )

        if TRANSCRIPT_PATH in url and "sessionwindows" not in url:
            row_count = None
            headers = None
            if method == "GET" and status == 200 and body:
                reader = csv.DictReader(io.StringIO(body))
                rows = list(reader)
                row_count = len(rows)
                headers = reader.fieldnames

            summary["transcript"].append(
                {
                    "method": method,
                    "status": status,
                    "url": url,
                    "response_preview": _safe_preview(body),
                    "csv_headers": headers,
                    "csv_row_count": row_count,
                }
            )

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
