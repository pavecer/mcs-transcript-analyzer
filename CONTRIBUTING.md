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
# macOS / Linux
python3 -m venv .venv && source .venv/bin/activate

# Windows PowerShell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1

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
python3 scripts/validate_documentation.py
python3 scripts/validate_site.py
python3 scripts/validate_browser_policy.py
```

If you changed sync or correlation logic, also prove parity against a real environment:

```bash
CFG=config/transcript_solution_config.dev.json
python3 scripts/transcript_insights/sync_transcripts.py --config $CFG --full --reprocess
# then the same via the plugin, and compare the resulting counts
```

State in the PR which environment you tested against and what the before/after row counts were.

Browser and UI validation must reuse an already shared VS Code built-in browser page. Workspace
instructions and a PreToolUse hook block external Playwright, Chrome, and Chromium launches. Run
`python3 scripts/validate_browser_policy.py` after changing `.github/hooks/` or
`.github/instructions/browser-use.instructions.md`.

## Schema changes

Dataverse schema is declarative in
[`solution/pvConversationInsights/solution-definition.json`](solution/pvConversationInsights/solution-definition.json).
Add columns there and re-run the provisioner — it is idempotent. Do not create columns by hand
in the maker portal, or the definition and the environment will drift.

Column deletion is destructive and is deliberately **not** automated.

## GitHub Pages and release package

Every user-visible feature must update the public presentation in [`site/`](site/). This is part
of the feature, not a later documentation task. Update the capability copy and limitations,
refresh the anonymized product preview when the UI changes, bump the four-part solution version,
and export a new managed solution ZIP.

Follow [`site/README.md`](site/README.md) for the full release checklist. Before opening the PR,
use the repo-scoped `.github/skills/release-documentation/SKILL.md` workflow and run:

```bash
python3 scripts/validate_documentation.py
python3 scripts/validate_site.py
```

`config/documentation-contract.json` inventories the affected surfaces and product inputs. If a
listed product input changed, review every indexed surface before replacing `productSourceDigest`
with `python3 scripts/validate_documentation.py --print-digest`. CI rejects stale documentation,
unindexed credit/release surfaces, missing component coverage, and incomplete code-app setup.

Release tracking is part of the same change. Add shipped behavior to [`CHANGELOG.md`](CHANGELOG.md),
update status and exit criteria in [`ROADMAP.md`](ROADMAP.md), and keep the public release-history
and roadmap sections synchronized in `site/index.html`. Use the repo-scoped
.github/skills/release-tracking/SKILL.md workflow or the `Release Maintainer` agent for this
work. Do not move a roadmap item to completed without package, build, API, or tenant evidence.
The ZIP must be imported into a clean sandbox before release. Confirm that all custom components,
including the JSON Viewer PCF, are embedded in the solution rather than left as dependencies on
the source environment.

## Commit messages

Short imperative subject, and explain *why* in the body when the reason is not obvious from the
diff. Reference the behaviour being fixed rather than the file changed.

```text
Skip already-ingested transcripts by default

Transcripts are immutable once finalised, so re-parsing rewrote sessions and
churned every turn row on each run, invalidating turn GUIDs.
```

## Reporting bugs

Include the channel (`msteams` / `m365copilot` / `pva-studio`), whether the session was
test-mode, and the relevant `pvci_syncstate` row (`pvci_lastrunstatus`, `pvci_lasterror`).
Never paste transcript content or user identifiers into an issue.
