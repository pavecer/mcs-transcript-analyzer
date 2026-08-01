# Contributing

Thanks for considering a contribution. This project touches a live Dataverse environment, so
a few of the rules below exist to stop a well-meaning change from corrupting someone's data.

## Ground rules

1. **Never commit environment-specific config or captured traffic.** `config/*.dev.json`,
   `config/*.sandbox.json`, `.env`, `.msal_token_cache.json`, `evidence/` and `*.har` are
   gitignored. HAR captures in particular contain conversation text and user identifiers.
2. **Keep the sync additive.** The default path must never rewrite an already-ingested
   transcript. Rewriting belongs behind `Reprocess` / `--reprocess`.
3. **Python and C# must stay in step.** `sync_transcripts.py` and
   `plugin/SyncConversationTranscripts.cs` implement the same parsing and correlation logic.
   Change one, change the other, and verify both produce identical counts.
4. **No broad exception swallowing.** A silent `except Exception: pass` once caused every flow
   correlation to return zero with no error. Catch specific exceptions and surface a warning.

## Development setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r scripts/transcript_insights/requirements.txt

az login --tenant <tenant-id>
pac auth create --environment <org-url>

cp config/transcript_solution_config.sample.json config/transcript_solution_config.dev.json
```

Build the other components:

```bash
cd plugin        && dotnet build -c Release && cd ..
cd pcf/JsonViewer && npm install && npm run build && cd ../..
cd codeapp       && npm install && npm run build && cd ..
```

## Before opening a pull request

Run the full validation:

```bash
source .venv/bin/activate
python3 -m py_compile scripts/transcript_insights/*.py
(cd plugin && dotnet build -c Release)          # must be warning-free
(cd pcf/JsonViewer && npm run build)
(cd codeapp && npm run build && npx eslint .)
```

If you changed sync or correlation logic, also prove parity against a real environment:

```bash
CFG=config/transcript_solution_config.dev.json
python3 scripts/transcript_insights/sync_transcripts.py --config $CFG --full --reprocess
# then the same via the plugin, and compare the resulting counts
```

State in the PR which environment you tested against and what the before/after row counts were.

## Schema changes

Dataverse schema is declarative in
[`solution/pvConversationInsights/solution-definition.json`](solution/pvConversationInsights/solution-definition.json).
Add columns there and re-run the provisioner — it is idempotent. Do not create columns by hand
in the maker portal, or the definition and the environment will drift.

Column deletion is destructive and is deliberately **not** automated.

## Commit messages

Short imperative subject, and explain *why* in the body when the reason is not obvious from the
diff. Reference the behaviour being fixed rather than the file changed.

```
Skip already-ingested transcripts by default

Transcripts are immutable once finalised, so re-parsing rewrote sessions and
churned every turn row on each run, invalidating turn GUIDs.
```

## Reporting bugs

Include the channel (`msteams` / `m365copilot` / `pva-studio`), whether the session was
test-mode, and the relevant `pvci_syncstate` row (`pvci_lastrunstatus`, `pvci_lasterror`).
Never paste transcript content or user identifiers into an issue.
