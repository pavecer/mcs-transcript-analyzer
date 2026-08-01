interface Bucket {
  label: string;
  count: number;
  p50: number | null;
  p95: number | null;
  failures: number;
}

const PAD = { top: 14, right: 52, bottom: 30, left: 44 };

/** Bars = session count (left axis), line = latency percentile (right axis). */
export function ComboChart({ buckets, height = 220 }: { buckets: Bucket[]; height?: number }) {
  if (!buckets.length) return <div className="muted pad">No data in range.</div>;

  const width = Math.max(360, buckets.length * 68 + PAD.left + PAD.right);
  const plotW = width - PAD.left - PAD.right;
  const plotH = height - PAD.top - PAD.bottom;

  const maxCount = Math.max(1, ...buckets.map((b) => b.count));
  const latValues = buckets.flatMap((b) => [b.p50, b.p95]).filter((v): v is number => v !== null);
  const maxLat = latValues.length ? Math.max(...latValues) : 0;

  const bandW = plotW / buckets.length;
  const barW = Math.min(38, bandW * 0.55);

  const yCount = (v: number) => PAD.top + plotH - (v / maxCount) * plotH;
  const yLat = (v: number) => PAD.top + plotH - (maxLat ? (v / maxLat) * plotH : 0);
  const xMid = (i: number) => PAD.left + bandW * i + bandW / 2;

  const linePoints = buckets
    .map((b, i) => (b.p95 === null ? null : `${xMid(i)},${yLat(b.p95)}`))
    .filter((p): p is string => p !== null)
    .join(" ");

  const countTicks = [0, Math.ceil(maxCount / 2), maxCount].filter((v, i, a) => a.indexOf(v) === i);
  const latTicks = maxLat ? [0, maxLat / 2, maxLat] : [];

  return (
    <div className="chart-scroll">
      <svg width={width} height={height} className="chart">
        {countTicks.map((t) => (
          <g key={`g${t}`}>
            <line x1={PAD.left} x2={width - PAD.right} y1={yCount(t)} y2={yCount(t)} className="grid" />
            <text x={PAD.left - 7} y={yCount(t) + 4} className="axis" textAnchor="end">{t}</text>
          </g>
        ))}

        {latTicks.map((t) => (
          <text key={`l${t}`} x={width - PAD.right + 7} y={yLat(t) + 4} className="axis lat-axis">
            {fmtShort(t)}
          </text>
        ))}

        {buckets.map((b, i) => {
          const h = plotH - (yCount(b.count) - PAD.top);
          return (
            <g key={b.label}>
              <rect
                x={xMid(i) - barW / 2}
                y={yCount(b.count)}
                width={barW}
                height={Math.max(1, h)}
                className={b.failures ? "bar bar-fail" : "bar"}
              >
                <title>{`${b.label}\n${b.count} sessions${b.failures ? `\n${b.failures} with tool failures` : ""}`}</title>
              </rect>
              <text x={xMid(i)} y={height - 10} className="axis" textAnchor="middle">{b.label}</text>
            </g>
          );
        })}

        {linePoints && <polyline points={linePoints} className="line" />}

        {buckets.map((b, i) =>
          b.p95 === null ? null : (
            <circle key={`d${b.label}`} cx={xMid(i)} cy={yLat(b.p95)} r={3.5} className="dot">
              <title>{`${b.label}\np95 ${fmtShort(b.p95)}\np50 ${b.p50 === null ? "—" : fmtShort(b.p50)}`}</title>
            </circle>
          )
        )}
      </svg>
    </div>
  );
}

export function HBar({ rows, unit = "" }: { rows: { label: string; value: number; bad?: boolean }[]; unit?: string }) {
  if (!rows.length) return <div className="muted small">No data.</div>;
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <div className="hbar">
      {rows.map((r) => (
        <div key={r.label} className="hbar-row">
          <span className="hbar-label" title={r.label}>{r.label}</span>
          <span className="hbar-track">
            <span className={`hbar-fill${r.bad ? " bad" : ""}`} style={{ width: `${(r.value / max) * 100}%` }} />
          </span>
          <span className="hbar-value">{unit === "ms" ? fmtShort(r.value) : r.value}</span>
        </div>
      ))}
    </div>
  );
}

function fmtShort(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)}s`;
}

export type { Bucket };
