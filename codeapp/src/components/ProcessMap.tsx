import { useEffect, useMemo, useRef, useState } from "react";
import { JsonTree } from "./JsonTree";
import { fmtMs } from "../lib/model";

export interface FlowActionEntry {
  name?: string;
  status?: string;
  start?: string;
  end?: string;
  code?: string;
  error?: unknown;
  inputs?: unknown;
  outputs?: unknown;
  repetitions?: FlowActionEntry[];
  type?: string;
  operation?: string;
  run_after?: Record<string, string[]>;
  parent?: string;
  branch?: string;
}

type StatusKind = "success" | "failed" | "skipped" | "running" | "unknown";

const NODE_WIDTH = 216;
const NODE_HEIGHT = 76;
const COLUMN_GAP = 54;
const ROW_GAP = 22;
const MAP_PADDING = 24;

function statusKind(status?: string): StatusKind {
  const normalized = (status ?? "").toLowerCase();
  if (normalized === "succeeded") return "success";
  if (normalized === "skipped") return "skipped";
  if (normalized === "running" || normalized === "waiting") return "running";
  if (normalized === "failed" || normalized === "timedout" || normalized === "cancelled") return "failed";
  return "unknown";
}

function humanize(value?: string): string {
  return (value ?? "Unnamed action")
    .replace(/_+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function durationMs(action: FlowActionEntry): number | null {
  const start = action.start ? Date.parse(action.start) : Number.NaN;
  const end = action.end ? Date.parse(action.end) : Number.NaN;
  return Number.isFinite(start) && Number.isFinite(end) ? Math.max(0, end - start) : null;
}

function errorText(error: unknown): string | null {
  if (!error) return null;
  if (typeof error === "string") return error;
  if (typeof error === "object") {
    const record = error as Record<string, unknown>;
    const code = typeof record.code === "string" ? record.code : null;
    const message = typeof record.message === "string" ? record.message : null;
    if (code || message) return [code, message].filter(Boolean).join(": ");
  }
  try {
    return JSON.stringify(error);
  } catch {
    return String(error);
  }
}

function directDependencies(
  action: FlowActionEntry,
  fallbackPrevious?: string,
): string[] {
  const explicit = Object.keys(action.run_after ?? {});
  if (explicit.length) return explicit;
  if (action.parent) return [action.parent];
  return fallbackPrevious ? [fallbackPrevious] : [];
}

function isRootFailure(action: FlowActionEntry, byName: Map<string, FlowActionEntry>): boolean {
  if (statusKind(action.status) !== "failed") return false;
  return Object.keys(action.run_after ?? {}).every((dependency) => {
    const dependencyStatus = statusKind(byName.get(dependency)?.status);
    return dependencyStatus !== "failed";
  });
}

interface LayoutNode {
  action: FlowActionEntry;
  index: number;
  x: number;
  y: number;
  dependencies: string[];
  rootFailure: boolean;
}

interface GraphLayout {
  nodes: LayoutNode[];
  width: number;
  height: number;
  inferredChronology: boolean;
}

function compareByStart(
  left: { action: FlowActionEntry; index: number },
  right: { action: FlowActionEntry; index: number },
): number {
  const leftMs = Date.parse(left.action.start ?? "");
  const rightMs = Date.parse(right.action.start ?? "");
  const leftValid = Number.isFinite(leftMs);
  const rightValid = Number.isFinite(rightMs);
  if (leftValid && rightValid && leftMs !== rightMs) return leftMs - rightMs;
  if (leftValid !== rightValid) return leftValid ? -1 : 1;
  return left.index - right.index;
}

function buildLayout(actions: FlowActionEntry[], showSkipped: boolean): GraphLayout {
  const indexed = actions.map((action, index) => ({ action, index }));
  const byName = new Map(indexed.flatMap(({ action }) => action.name ? [[action.name, action] as const] : []));
  const hasDefinitionGraph = actions.some((action) => Object.keys(action.run_after ?? {}).length || action.parent);
  const chronological = [...indexed].sort(compareByStart);
  const previousByName = new Map<string, string>();
  if (!hasDefinitionGraph) {
    chronological.forEach(({ action }, index) => {
      if (action.name && index > 0 && chronological[index - 1].action.name) {
        previousByName.set(action.name, chronological[index - 1].action.name!);
      }
    });
  }

  const visible = indexed.filter(({ action }) => showSkipped || statusKind(action.status) !== "skipped");
  const visibleNames = new Set(visible.flatMap(({ action }) => action.name ? [action.name] : []));

  const resolveVisibleDependencies = (name: string, seen = new Set<string>()): string[] => {
    if (seen.has(name)) return [];
    seen.add(name);
    const action = byName.get(name);
    if (!action) return [];
    const dependencies = directDependencies(action, previousByName.get(name));
    const resolved = dependencies.flatMap((dependency) =>
      visibleNames.has(dependency) ? [dependency] : resolveVisibleDependencies(dependency, seen));
    return [...new Set(resolved)];
  };

  const depthMemo = new Map<string, number>();
  const depth = (name: string, visiting = new Set<string>()): number => {
    if (depthMemo.has(name)) return depthMemo.get(name)!;
    if (visiting.has(name)) return 0;
    visiting.add(name);
    const dependencies = resolveVisibleDependencies(name);
    const value = dependencies.length
      ? Math.max(...dependencies.map((dependency) => depth(dependency, new Set(visiting)))) + 1
      : 0;
    depthMemo.set(name, value);
    return value;
  };

  const layers = new Map<number, typeof visible>();
  visible.forEach((item) => {
    const layer = item.action.name ? depth(item.action.name) : 0;
    const entries = layers.get(layer) ?? [];
    entries.push(item);
    layers.set(layer, entries);
  });
  layers.forEach((entries) => entries.sort(compareByStart));

  const nodes: LayoutNode[] = [];
  layers.forEach((entries, layer) => {
    entries.forEach((item, row) => {
      nodes.push({
        ...item,
        x: MAP_PADDING + layer * (NODE_WIDTH + COLUMN_GAP),
        y: MAP_PADDING + row * (NODE_HEIGHT + ROW_GAP),
        dependencies: item.action.name ? resolveVisibleDependencies(item.action.name) : [],
        rootFailure: isRootFailure(item.action, byName),
      });
    });
  });

  const maxLayer = Math.max(0, ...layers.keys());
  const maxRows = Math.max(1, ...[...layers.values()].map((entries) => entries.length));
  return {
    nodes,
    width: MAP_PADDING * 2 + (maxLayer + 1) * NODE_WIDTH + maxLayer * COLUMN_GAP,
    height: MAP_PADDING * 2 + maxRows * NODE_HEIGHT + (maxRows - 1) * ROW_GAP,
    inferredChronology: !hasDefinitionGraph && actions.length > 1,
  };
}

export function ProcessMap({ actions }: { actions: FlowActionEntry[] }) {
  const [showSkipped, setShowSkipped] = useState(false);
  const byName = useMemo(() => new Map(actions.flatMap((action) =>
    action.name ? [[action.name, action] as const] : [])), [actions]);
  const initialSelection = useMemo(() => {
    const root = actions.find((action) => isRootFailure(action, byName));
    const failed = actions.find((action) => statusKind(action.status) === "failed");
    return (root ?? failed)?.name ?? null;
  }, [actions, byName]);
  const [selectedName, setSelectedName] = useState<string | null>(initialSelection);
  const layout = useMemo(() => buildLayout(actions, showSkipped), [actions, showSkipped]);
  const effectiveSelectedName = selectedName && byName.has(selectedName) ? selectedName : initialSelection;
  const selected = effectiveSelectedName ? byName.get(effectiveSelectedName) : undefined;
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const selectedNode = layout.nodes.find((node) => node.action.name === effectiveSelectedName);
    const scroller = scrollRef.current;
    if (!selectedNode || !scroller) return;
    const frame = requestAnimationFrame(() => {
      scroller.scrollTo({
        left: Math.max(0, selectedNode.x - scroller.clientWidth / 2 + NODE_WIDTH / 2),
        top: Math.max(0, selectedNode.y - 32),
        behavior: "smooth",
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [effectiveSelectedName, layout]);

  const failed = actions.filter((action) => statusKind(action.status) === "failed");
  const skipped = actions.filter((action) => statusKind(action.status) === "skipped");
  const rootFailures = failed.filter((action) => isRootFailure(action, byName));
  const positions = new Map(layout.nodes.flatMap((node) =>
    node.action.name ? [[node.action.name, node] as const] : []));

  return (
    <div className="process-map">
      <div className={`process-summary ${rootFailures.length ? "failed" : failed.length ? "warning" : "success"}`}>
        <div>
          <strong>
            {!actions.length
              ? "Action history is unavailable"
              : rootFailures.length
              ? `First likely failure: ${humanize(rootFailures[0].name)}`
              : failed.length
                ? `${failed.length} action${failed.length === 1 ? "" : "s"} failed`
                : "Run completed successfully"}
          </strong>
          <span>
            {!actions.length
              ? "No action entries were retained, so run success cannot be evaluated here."
              : rootFailures.length
              ? errorText(rootFailures[0].error) ?? "Select the highlighted node for technical details."
              : `${actions.length - skipped.length} actions executed; ${skipped.length} branches were skipped.`}
          </span>
        </div>
        <div className="process-legend" aria-label="Process map legend">
          <span><i className="legend-dot success" />Succeeded</span>
          <span><i className="legend-dot failed" />Failed</span>
          <span><i className="legend-dot skipped" />Skipped</span>
          <span><i className="legend-dot unknown" />Unknown</span>
        </div>
      </div>

      <div className="process-toolbar">
        <span className="muted small">
          {layout.inferredChronology
            ? "Connections show chronological order because dependency metadata was unavailable. Select an action to inspect its data."
            : "Connections follow recorded dependency metadata. Select an action to inspect its data."}
        </span>
        <label className="checkline">
          <input type="checkbox" checked={showSkipped} onChange={(event) => setShowSkipped(event.target.checked)} />
          Show skipped branches ({skipped.length})
        </label>
      </div>

      <div className={`process-layout${selected ? " with-inspector" : ""}`}>
        <div className="process-canvas-scroll" ref={scrollRef}>
          <div className="process-canvas" style={{ width: layout.width, height: layout.height }}>
            <svg className="process-edges" width={layout.width} height={layout.height} aria-hidden="true">
              <defs>
                <marker id="process-arrow" className="process-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" />
                </marker>
              </defs>
              {layout.nodes.flatMap((node) => node.dependencies.map((dependency) => {
                const source = positions.get(dependency);
                if (!source) return null;
                const startX = source.x + NODE_WIDTH;
                const startY = source.y + NODE_HEIGHT / 2;
                const endX = node.x;
                const endY = node.y + NODE_HEIGHT / 2;
                const bend = Math.max(24, (endX - startX) / 2);
                return (
                  <path
                    key={`${dependency}-${node.action.name}`}
                    className={`process-edge ${statusKind(node.action.status)}`}
                    d={`M ${startX} ${startY} C ${startX + bend} ${startY}, ${endX - bend} ${endY}, ${endX} ${endY}`}
                    markerEnd="url(#process-arrow)"
                  />
                );
              }))}
            </svg>

            {layout.nodes.map((node) => {
              const kind = statusKind(node.action.status);
              return (
                <button
                  key={`${node.action.name}-${node.index}`}
                  className={`process-node ${kind}${node.rootFailure ? " root-failure" : ""}${effectiveSelectedName === node.action.name ? " selected" : ""}`}
                  style={{ left: node.x, top: node.y, width: NODE_WIDTH, height: NODE_HEIGHT }}
                  type="button"
                  title={node.action.name}
                  onClick={() => setSelectedName(node.action.name ?? null)}
                >
                  <span className="process-node-status" aria-hidden="true">
                    {kind === "success" ? "✓" : kind === "failed" ? "!" : kind === "running" ? "…" : kind === "unknown" ? "?" : "−"}
                  </span>
                  <span className="process-node-copy">
                    <strong>{humanize(node.action.name)}</strong>
                    <small>{node.action.operation ?? node.action.type ?? "Action"} · {fmtMs(durationMs(node.action))}</small>
                  </span>
                  {node.rootFailure && <span className="root-badge">likely first failure</span>}
                </button>
              );
            })}
          </div>
        </div>

        {selected && <ActionInspector action={selected} onClose={() => setSelectedName(null)} />}
      </div>
    </div>
  );
}

function ActionInspector({ action, onClose }: { action: FlowActionEntry; onClose: () => void }) {
  const kind = statusKind(action.status);
  const dependencies = Object.entries(action.run_after ?? {});
  const actionError = errorText(action.error);

  return (
    <aside className="action-inspector">
      <div className="inspector-head">
        <div className="inspector-headline">
          <span className={`inspector-status ${kind}`}>{action.status ?? "Unknown"}</span>
          <button className="inspector-close" type="button" title="Close action details" aria-label="Close action details" onClick={onClose}>×</button>
        </div>
        <h3>{humanize(action.name)}</h3>
        <code>{action.name}</code>
      </div>

      <dl className="inspector-facts">
        <div><dt>Type</dt><dd>{action.type ?? "—"}</dd></div>
        <div><dt>Operation</dt><dd>{action.operation ?? "—"}</dd></div>
        <div><dt>Duration</dt><dd>{fmtMs(durationMs(action))}</dd></div>
        <div><dt>Branch</dt><dd>{action.branch ?? "main"}</dd></div>
      </dl>

      {actionError && <div className="inspector-error"><strong>What went wrong</strong>{actionError}</div>}

      {dependencies.length > 0 && (
        <div className="inspector-section">
          <h4>Runs after</h4>
          {dependencies.map(([name, statuses]) => (
            <div className="dependency-row" key={name}>
              <span>{humanize(name)}</span>
              <small>{statuses.join(" or ")}</small>
            </div>
          ))}
        </div>
      )}

      {action.repetitions?.length ? (
        <div className="inspector-section">
          <h4>Loop iterations</h4>
          <div className="iteration-strip">
            {action.repetitions.map((iteration, index) => (
              <span className={`iteration ${statusKind(iteration.status)}`} key={`${iteration.name}-${index}`} title={iteration.status}>
                {index + 1}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      <details className="inspector-json">
        <summary>Inputs</summary>
        {action.inputs == null ? <div className="muted small">No inputs recorded.</div> : <JsonTree value={action.inputs as never} initialCollapseDepth={2} />}
      </details>
      <details className="inspector-json">
        <summary>Outputs</summary>
        {action.outputs == null ? <div className="muted small">No outputs recorded.</div> : <JsonTree value={action.outputs as never} initialCollapseDepth={2} />}
      </details>
      {action.repetitions?.length ? (
        <details className="inspector-json">
          <summary>Iteration details</summary>
          <JsonTree value={action.repetitions as never} initialCollapseDepth={2} />
        </details>
      ) : null}
    </aside>
  );
}