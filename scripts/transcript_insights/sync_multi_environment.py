#!/usr/bin/env python3
"""Run transcript sync across multiple Power Platform environments.

This orchestrates the existing `sync_transcripts.py` logic for each config file and
produces one summary so tenant-wide ESS analysis can be populated from many envs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from dv_token import get_token_from_config
from sync_transcripts import Dv, SYNCSTATE, load_source_context, sync


def discover_configs(args_configs: list[str], include_sample: bool) -> list[Path]:
    files: list[Path] = []
    for item in args_configs:
        path = Path(item)
        if any(ch in item for ch in "*?[]"):
            files.extend(sorted(Path().glob(item)))
        elif path.is_dir():
            files.extend(sorted(path.glob("transcript_solution_config*.json")))
        else:
            files.append(path)

    seen: set[str] = set()
    out: list[Path] = []
    for file in files:
        key = str(file.resolve()) if file.exists() else str(file)
        if key in seen:
            continue
        seen.add(key)
        if not include_sample and file.name.endswith("sample.json"):
            continue
        out.append(file)
    return out


def looks_placeholder(cfg: dict[str, Any]) -> bool:
    bot = str(cfg.get("botId", ""))
    return (not bot) or ("REPLACE-" in bot)


def read_since(dv: Dv) -> str | None:
    rows = dv.get_all(
        f"{SYNCSTATE}?$select=pvci_lastsyncedcreatedon&$filter=pvci_name eq 'default'&$top=1"
    )
    if rows:
        return rows[0].get("pvci_lastsyncedcreatedon")
    return None


def run_one(config_path: Path, full: bool, include_traces: bool, limit: int | None, reprocess: bool,
            since_override: str | None) -> dict[str, Any]:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    token, dv_url = get_token_from_config(config_path)
    dv = Dv(f"{dv_url}/api/data/v9.1", token)
    source_ctx = load_source_context(str(config_path))

    since = since_override
    if since is None and not full:
        since = read_since(dv)

    stats = sync(
        dv,
        str(config_path),
        since,
        full,
        include_traces,
        limit,
        reprocess,
        source_ctx,
    )

    return {
        "config": str(config_path),
        "tenantId": cfg.get("tenantId"),
        "environmentId": cfg.get("environmentId"),
        "environmentName": cfg.get("environmentName"),
        "dataverseUrl": cfg.get("dataverseUrl"),
        "status": stats.get("status"),
        "watermark": stats.get("watermark"),
        "transcripts": stats.get("transcripts", 0),
        "sessions_created": stats.get("sessions_created", 0),
        "sessions_updated": stats.get("sessions_updated", 0),
        "sessions_skipped": stats.get("sessions_skipped", 0),
        "turns": stats.get("turns", 0),
        "errors": stats.get("errors", []),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--configs",
        nargs="+",
        default=["config/transcript_solution_config.dev.json", "config/transcript_solution_config.sandbox.json"],
        help="Config files, folders, or globs (default: dev + sandbox)",
    )
    ap.add_argument("--full", action="store_true", help="Ignore watermark and reprocess everything")
    ap.add_argument("--since", default=None, help="ISO timestamp override for all environments")
    ap.add_argument("--include-traces", action="store_true", help="Also store trace/DialogTracing activities")
    ap.add_argument("--reprocess", action="store_true", help="Rewrite transcripts already ingested")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--include-sample", action="store_true", help="Also include sample config files")
    args = ap.parse_args()

    configs = discover_configs(args.configs, include_sample=args.include_sample)
    if not configs:
        raise SystemExit("No config files found. Provide --configs with files or a glob.")

    results: list[dict[str, Any]] = []
    failures = 0

    for config_path in configs:
        if not config_path.exists():
            results.append({
                "config": str(config_path),
                "status": "failed",
                "errors": ["Config file does not exist"],
            })
            failures += 1
            continue

        cfg = json.loads(config_path.read_text(encoding="utf-8"))
        if looks_placeholder(cfg):
            results.append({
                "config": str(config_path),
                "status": "skipped",
                "errors": ["botId is missing or placeholder"],
            })
            continue

        print(f"\n=== syncing {config_path} ===", flush=True)
        try:
            summary = run_one(
                config_path,
                full=args.full,
                include_traces=args.include_traces,
                limit=args.limit,
                reprocess=args.reprocess,
                since_override=args.since,
            )
            results.append(summary)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            results.append({
                "config": str(config_path),
                "status": "failed",
                "errors": [f"{type(exc).__name__}: {exc}"],
            })

    aggregate = {
        "status": "failed" if failures else "ok",
        "environments": len(results),
        "failed_environments": failures,
        "total_transcripts": sum(int(r.get("transcripts", 0) or 0) for r in results),
        "total_turns": sum(int(r.get("turns", 0) or 0) for r in results),
        "results": results,
    }
    print("\n" + json.dumps(aggregate, indent=2))


if __name__ == "__main__":
    main()
