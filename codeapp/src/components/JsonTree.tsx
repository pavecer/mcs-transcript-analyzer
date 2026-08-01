import { useMemo, useState } from "react";
import type { Json } from "../lib/model";

interface Props {
  value: Json;
  initialCollapseDepth?: number;
  filter?: string;
}

export function JsonTree({ value, initialCollapseDepth = 2, filter = "" }: Props) {
  return (
    <div className="jsontree">
      <Node value={value} name={null} depth={0} collapseDepth={initialCollapseDepth} filter={filter.toLowerCase()} />
    </div>
  );
}

interface NodeProps {
  value: Json;
  name: string | null;
  depth: number;
  collapseDepth: number;
  filter: string;
}

function Node({ value, name, depth, collapseDepth, filter }: NodeProps) {
  const container = value !== null && typeof value === "object";
  const [open, setOpen] = useState(depth < collapseDepth);

  const entries = useMemo<[string, Json][]>(() => {
    if (Array.isArray(value)) return value.map((v, i) => [String(i), v]);
    if (value !== null && typeof value === "object") return Object.entries(value);
    return [];
  }, [value]);

  const selfMatch = filter
    ? `${name ?? ""} ${container ? "" : String(value)}`.toLowerCase().includes(filter)
    : false;

  const subtreeMatch = useMemo(() => {
    if (!filter) return true;
    if (selfMatch) return true;
    const probe = (v: Json, k: string | null): boolean => {
      if (`${k ?? ""}`.toLowerCase().includes(filter)) return true;
      if (v === null || typeof v !== "object") return String(v).toLowerCase().includes(filter);
      if (Array.isArray(v)) return v.some((c) => probe(c, null));
      return Object.entries(v).some(([ck, cv]) => probe(cv, ck));
    };
    return probe(value, name);
  }, [filter, selfMatch, value, name]);

  if (filter && !subtreeMatch) return null;

  const label = name === null ? null : <span className="jt-key">{JSON.stringify(name)}</span>;

  if (!container) {
    return (
      <div className={`jt-row${selfMatch ? " jt-hit" : ""}`} style={{ paddingLeft: depth * 14 }}>
        <span className="jt-bullet">·</span>
        {label}
        {label && <span className="jt-punct">: </span>}
        <Scalar value={value} />
      </div>
    );
  }

  const brackets = Array.isArray(value) ? ["[", "]"] : ["{", "}"];

  return (
    <>
      <div className={`jt-row${selfMatch ? " jt-hit" : ""}`} style={{ paddingLeft: depth * 14 }}>
        <span className="jt-toggle" onClick={() => setOpen(!open)} role="button" tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && setOpen(!open)}>
          {open ? "▼" : "▶"}
        </span>
        {label}
        {label && <span className="jt-punct">: </span>}
        <span className="jt-punct">{brackets[0]}</span>
        {!open && entries.length > 0 && <span className="jt-meta"> {entries.length} </span>}
        {(!open || entries.length === 0) && <span className="jt-punct">{brackets[1]}</span>}
      </div>
      {open &&
        entries.map(([k, v]) => (
          <Node key={k} value={v} name={k} depth={depth + 1} collapseDepth={collapseDepth} filter={filter} />
        ))}
      {open && entries.length > 0 && (
        <div className="jt-row" style={{ paddingLeft: depth * 14 + 13 }}>
          <span className="jt-punct">{brackets[1]}</span>
        </div>
      )}
    </>
  );
}

const MAX_INLINE = 320;

function Scalar({ value }: { value: Json }) {
  if (value === null) return <span className="jt-null">null</span>;
  if (typeof value === "boolean") return <span className="jt-bool">{String(value)}</span>;
  if (typeof value === "number") return <span className="jt-num">{value}</span>;
  const text = String(value);
  if (text.length > MAX_INLINE) {
    return (
      <span className="jt-str" title={text.slice(0, 4000)}>
        {JSON.stringify(text.slice(0, MAX_INLINE))} <span className="jt-meta">… {text.length.toLocaleString()} chars</span>
      </span>
    );
  }
  return <span className="jt-str">{JSON.stringify(text)}</span>;
}
