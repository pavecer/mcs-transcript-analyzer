#!/usr/bin/env bash
# Scheduled incremental sync. Wire into cron/launchd/CI.
#   */15 * * * * /path/to/run_sync.sh >> /var/log/pvci_sync.log 2>&1
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONFIG="${PVCI_CONFIG:-config/transcript_solution_config.dev.json}"

cd "$REPO_ROOT"
# shellcheck disable=SC1091
source .venv/bin/activate

echo "=== pvci sync $(date -u +%Y-%m-%dT%H:%M:%SZ) config=$CONFIG ==="
python3 scripts/transcript_insights/sync_transcripts.py --config "$CONFIG" "$@"
