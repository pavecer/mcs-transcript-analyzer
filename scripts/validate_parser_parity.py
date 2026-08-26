#!/usr/bin/env python3
"""Prove the Python worker and C# plugin emit identical diagnostic projections."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPT_SCRIPTS = ROOT / "scripts" / "transcript_insights"
FIXTURE = ROOT / "tests" / "fixtures" / "transcript-analysis.json"
HARNESS = ROOT / "plugin.tests" / "TranscriptParityHarness.csproj"
sys.path.insert(0, str(TRANSCRIPT_SCRIPTS))

from sync_transcripts import knowledge_calls, transcript_diagnostics  # noqa: E402


def main() -> None:
    activities = json.loads(FIXTURE.read_text(encoding="utf-8"))["activities"]
    expected = {
        "diagnostics": transcript_diagnostics(activities),
        "knowledge_calls": knowledge_calls(activities),
    }
    result = subprocess.run(
        ["dotnet", "run", "--project", str(HARNESS), "--", str(FIXTURE)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    actual = json.loads(result.stdout)
    if actual != expected:
        print("ERROR: Python and C# transcript analysis projections differ", file=sys.stderr)
        print(json.dumps({"python": expected, "csharp": actual}, indent=2), file=sys.stderr)
        raise SystemExit(1)
    print("PASS: Python and C# transcript diagnostics and knowledge projections are identical")


if __name__ == "__main__":
    main()
