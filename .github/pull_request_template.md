## What and why

<!-- What changes, and the behaviour it fixes or enables. -->

## Validation

```
python3 -m py_compile scripts/transcript_insights/*.py
(cd plugin && dotnet build -c Release)
(cd pcf/JsonViewer && npm run build)
(cd codeapp && npm run build)
```

- [ ] All four build clean (plugin warning-free)
- [ ] Tested against a real Dataverse environment

Environment tested: <!-- e.g. dev / sandbox --> 
Row counts before → after: <!-- sessions / turns -->

## Checklist

- [ ] Python and C# sync logic kept in step (if either changed)
- [ ] Sync remains additive by default; rewrites stay behind `Reprocess` / `--reprocess`
- [ ] Schema changes made in `solution-definition.json`, not by hand in the maker portal
- [ ] No environment config, HAR captures, transcript content or user identifiers committed
- [ ] No broad `except Exception` that could hide a failure
- [ ] Docs updated if behaviour or limitations changed
