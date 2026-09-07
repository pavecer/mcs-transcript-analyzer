import { fmtTime } from "../lib/model";
import {
  EMPTY_ESS_EVIDENCE_FILTERS,
  isEssEvidenceFilterActive,
  type EssEvidenceCandidate,
  type EssEvidenceFilters,
} from "../lib/essEvidence";

export function EssEvidencePicker({
  candidates, visible, selectedId, filters, loading, onSelect, onFiltersChange,
}: {
  candidates: EssEvidenceCandidate[];
  visible: EssEvidenceCandidate[];
  selectedId: string | null;
  filters: EssEvidenceFilters;
  loading: boolean;
  onSelect: (sessionId: string) => void;
  onFiltersChange: (filters: EssEvidenceFilters) => void;
}) {
  const agents = [...new Set(candidates.map((row) => row.agentName))].sort((a, b) => a.localeCompare(b));
  const environments = [...new Set(candidates.map((row) => row.environmentLabel))].sort((a, b) => a.localeCompare(b));
  const set = <K extends keyof EssEvidenceFilters>(key: K, value: EssEvidenceFilters[K]) =>
    onFiltersChange({ ...filters, [key]: value });

  return (
    <section className="ess-evidence-picker" aria-labelledby="ess-evidence-picker-heading">
      <h3 id="ess-evidence-picker-heading" className="sub ess-evidence-step">
        <span className="step-index">1</span>Choose the ESS example
      </h3>

      <div className="ess-evidence-filters" role="search">
        <input
          className="search"
          placeholder="Search agent, environment, channel, outcome, date…"
          value={filters.search}
          onChange={(event) => set("search", event.target.value)}
          aria-label="Search ESS sessions"
        />
        <select className="search" value={filters.agent} onChange={(event) => set("agent", event.target.value)} aria-label="Filter by agent">
          <option value="*">All agents</option>
          {agents.map((agent) => <option key={agent} value={agent}>{agent}</option>)}
        </select>
        <select className="search" value={filters.environment} onChange={(event) => set("environment", event.target.value)} aria-label="Filter by environment">
          <option value="*">All environments</option>
          {environments.map((environment) => <option key={environment} value={environment}>{environment}</option>)}
        </select>
        <select className="search" value={filters.mode} onChange={(event) => set("mode", event.target.value as EssEvidenceFilters["mode"])} aria-label="Filter by mode">
          <option value="*">Test and production</option>
          <option value="test">Test chat only</option>
          <option value="production">Production only</option>
        </select>
        <label className="checkline">
          <input type="checkbox" checked={filters.errorsOnly} onChange={(event) => set("errorsOnly", event.target.checked)} />
          With user errors only
        </label>
        {isEssEvidenceFilterActive(filters) && (
          <button type="button" className="linkish" onClick={() => onFiltersChange(EMPTY_ESS_EVIDENCE_FILTERS)}>Clear filters</button>
        )}
      </div>

      <div className="muted small pad-sm">
        {visible.length} of {candidates.length} qualifying session{candidates.length === 1 ? "" : "s"} shown
      </div>

      {loading ? (
        <div className="muted pad">Loading ESS sessions…</div>
      ) : !visible.length ? (
        <div className="muted pad">No qualifying ESS session matches these filters.</div>
      ) : (
        <div className="ess-evidence-table-scroll">
          <table className="runtable">
            <thead>
              <tr>
                <th scope="col"><span className="visually-hidden">Select</span></th>
                <th scope="col">agent</th>
                <th scope="col">environment</th>
                <th scope="col">started (UTC)</th>
                <th scope="col">mode</th>
                <th scope="col">outcome</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => {
                const isActive = row.sessionId === selectedId;
                return (
                  <tr key={row.sessionId} className={isActive ? "best" : undefined}>
                    <td>
                      <input
                        type="radio"
                        name="ess-evidence-session"
                        checked={isActive}
                        onChange={() => onSelect(row.sessionId)}
                        aria-label={`Select ${row.agentName} session started ${fmtTime(row.startedUtc)}`}
                      />
                    </td>
                    <td>{row.agentName}</td>
                    <td>{row.environmentLabel}</td>
                    <td className="mono">{fmtTime(row.startedUtc)}</td>
                    <td>{row.testMode ? <span className="flag test">test</span> : "production"}</td>
                    <td>
                      {row.outcome}
                      {row.userErrors.state === "unavailable" ? (
                        <span className="muted small"> · user errors unavailable</span>
                      ) : row.userErrors.count! > 0 ? (
                        <span className="ess-error-code"> · {row.userErrors.count} user error{row.userErrors.count === 1 ? "" : "s"}</span>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
