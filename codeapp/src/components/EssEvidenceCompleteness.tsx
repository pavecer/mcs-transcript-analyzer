import type { ChecklistItem, ExternalEvidenceItem } from "../lib/essEvidence";

const TONE: Record<string, string> = {
  present: "good",
  "observed-zero": "neutral",
  "not-applicable": "neutral",
  "not-stored": "warn",
  unavailable: "warn",
  missing: "warn",
};

export function EssEvidenceCompleteness({ checklist, external, loading }: {
  checklist: ChecklistItem[];
  external: ExternalEvidenceItem[];
  loading: boolean;
}) {
  return (
    <>
      <h3 className="sub ess-evidence-step"><span className="step-index">3</span>Evidence completeness</h3>
      {loading && <div className="muted small pad-sm">Loading session evidence…</div>}
      <div className="ess-evidence-checklist">
        {checklist.map((entry) => (
          <span key={entry.id} className={`ess-evidence-check ${TONE[entry.state] ?? "neutral"}`}>
            <strong>{entry.label}</strong>
            <span>{entry.state}</span>
          </span>
        ))}
      </div>

      <h3 className="sub">Missing or external evidence</h3>
      <table className="runtable">
        <thead>
          <tr>
            <th scope="col">artefact</th>
            <th scope="col">state</th>
            <th scope="col">how to supply it</th>
          </tr>
        </thead>
        <tbody>
          {external.map((entry) => (
            <tr key={entry.id}>
              <td>{entry.label}</td>
              <td><span className={`conf ${entry.state === "unverified" ? "risk-watch" : "risk-high"}`}>{entry.state}</span></td>
              <td className="muted">{entry.detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
