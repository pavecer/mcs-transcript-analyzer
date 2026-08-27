---
name: Human Analyst Interface Design
description: "Use when creating or changing code-app UI, dashboards, operational tables, warnings, metrics, navigation, drill-downs, or analyst workflows. Enforces decision-first information hierarchy and PVE validation."
applyTo: "codeapp/src/**"
---

# Human Analyst Interface Design

- Design for the decision a human analyst must make, not for the number of fields available.
- Order information as: state and scope; warnings and exceptions; recommended action; supporting
  evidence; technical metadata and raw detail.
- Never place remediation below a long table or require scanning detail to discover the conclusion.
- Put errors, unavailable evidence, stale data, and material risk in the first useful viewport.
  Explain impact and identify the next drill-down or action; do not rely on color alone.
- Preserve observed zero, unavailable, unknown, candidate correlation, and exact attribution as
  distinct evidence states.
- Prefer purposeful density: KPI groups for state, tables for comparison, timelines for sequence,
  and disclosures for metadata. Do not make every section a card.
- Keep duplicate resources distinguishable by environment or source, and keep result/error columns
  visible before lower-value metadata.
- Treat desktop analyst workflows as primary while preventing responsive overlap and clipping.
- Before handing analyst-facing work back to the user, independently validate the deployed build in
  PVE Dev with the shared VS Code browser. Do not delegate this check to the user or treat a user
  screenshot as a substitute for agent-run interaction, assertions, and screenshots.
- Exercise every changed view or workflow plus representative healthy, warning/failure,
  unavailable/unknown, loading, and empty states when the data supports them. Verify semantic claims
  against the selected record, including observed zero versus unavailable and planned/correlated
  evidence versus exact execution.
- Run the visual matrix at a desktop viewport of 1440 x 1000 and a narrow viewport of 390 x 844.
  At both widths, check document and key-container `scrollWidth`/`clientWidth`, text clipping,
  incoherent overlap, fixed-header or tab obstruction, and whether the primary workflow remains
  reachable. Horizontal scrolling is acceptable only inside an intentional local container such as
  a dense table or tab strip.
- Capture screenshots of the changed state at desktop and narrow widths. In the final handoff, name
  the PVE scenarios exercised, viewport sizes, assertion outcomes, and any evidence gap.
- Power Platform and code-app changes are not ready for commit, PR inclusion, or user handoff until
  the latest build is deployed and this visual matrix passes in PVE Dev. If authentication, host
  rendering, or representative data blocks the matrix, report the work as visually unvalidated and
  keep it open; ask the user only for access or sign-in needed for the agent to continue.
- For substantial analyst-facing creation or review, use the `Analyst Experience Advocate` agent.