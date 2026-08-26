---
name: Canonical npm Dependencies
description: "Use for npm dependency, package-lock, Node build, and CI install changes in this repository."
applyTo: "{codeapp/**,pcf/JsonViewer/**,.github/workflows/**,scripts/validate_npm_lockfiles.py}"
---

# npm Dependency Policy

- Commit canonical `https://registry.npmjs.org/` tarball URLs in both package lockfiles. Never
  serialize a developer-machine proxy, Azure Artifacts `ms-feed-*` URL, or private registry into
  these public-package locks.
- A local npm proxy may replace canonical npmjs URLs at install time. Before committing a lockfile,
  run `python scripts/validate_npm_lockfiles.py` to prove the local registry did not leak into it.
- Use `npm ci` in automation. Use `npm install` only when intentionally changing dependencies and
  review package versions, integrity hashes, and registry hosts separately.
- Treat an HTTP 5xx failure during dependency download as external until the failed URL and step
  prove otherwise. Do not patch application code to address an install-stage outage. Validate the
  lockfiles, run the affected build locally, and retry only the failed job when GitHub permits it.