import { useEffect, useMemo, useRef, useState } from "react";
import { Pvci_transcriptsessionsService } from "../generated/services/Pvci_transcriptsessionsService";
import { Pvci_transcriptturnsService } from "../generated/services/Pvci_transcriptturnsService";
import { EssEvidenceCompleteness } from "./EssEvidenceCompleteness";
import { EssEvidenceForm } from "./EssEvidenceForm";
import { EssEvidencePicker } from "./EssEvidencePicker";
import type { SessionRow, TurnRow } from "../lib/model";
import {
  EMPTY_ESS_EVIDENCE_CONTEXT,
  EMPTY_ESS_EVIDENCE_FILTERS,
  buildEssEvidencePackage,
  describeEssEvidenceCandidate,
  essEvidenceFilename,
  filterEssEvidenceCandidates,
  missingNarrativeFields,
  selectEssEvidenceSession,
  type EssEvidenceContext,
  type EssEvidenceFilters,
  type NarrativeFieldKey,
} from "../lib/essEvidence";

const DETAIL_FIELDS = [
  "pvci_transcriptsessionid",
  "pvci_activitiesjson", "pvci_conversationjson", "pvci_planeventsjson",
  "pvci_metadatajson", "pvci_toolcallsjson", "pvci_knowledgecallsjson", "pvci_flowrunsjson",
  "pvci_primaryerrormessage",
];

const TURN_FIELDS = [
  "pvci_transcriptturnid", "pvci_transcriptid", "pvci_turnindex",
  "pvci_activitytype", "pvci_speaker", "pvci_role", "pvci_eventname",
  "pvci_channelid", "pvci_timestamputc", "pvci_turntext", "pvci_valuejson", "pvci_latencyms",
];

// Only used to render the readiness checklist; the download rebuilds with the real timestamp.
const PREVIEW_TIMESTAMP = "1970-01-01T00:00:00.000Z";

const TRUNCATION_WARNING_PREFIX = "The stored transcript payload is truncated";

interface SessionEvidence {
  detail: SessionRow | null;
  turns: TurnRow[];
  loading: boolean;
  error: string | null;
}

const EMPTY_EVIDENCE: SessionEvidence = { detail: null, turns: [], loading: false, error: null };

function useSessionEvidence(sessionId: string | null, transcriptId: string | undefined): SessionEvidence {
  const [state, setState] = useState<SessionEvidence>(EMPTY_EVIDENCE);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      if (!sessionId) {
        setState(EMPTY_EVIDENCE);
        return;
      }
      setState({ ...EMPTY_EVIDENCE, loading: true });
      try {
        const [detailRes, turnRes] = await Promise.all([
          Pvci_transcriptsessionsService.get(sessionId, { select: DETAIL_FIELDS }),
          transcriptId
            ? Pvci_transcriptturnsService.getAll({
                select: TURN_FIELDS,
                filter: `pvci_transcriptid eq '${transcriptId}'`,
                orderBy: ["pvci_turnindex asc"],
                top: 500,
              })
            : Promise.resolve({ data: [] as unknown[] }),
        ]);
        if (cancelled) return;
        setState({
          detail: (detailRes.data ?? null) as unknown as SessionRow | null,
          turns: (turnRes.data ?? []) as unknown as TurnRow[],
          loading: false,
          error: null,
        });
      } catch (reason) {
        if (!cancelled) {
          setState({ ...EMPTY_EVIDENCE, error: reason instanceof Error ? reason.message : String(reason) });
        }
      }
    })();

    return () => { cancelled = true; };
  }, [sessionId, transcriptId]);

  return state;
}

export function EssEvidence({ sessions, loading, hostEnvironmentId, focusSessionId }: {
  sessions: SessionRow[];
  loading: boolean;
  hostEnvironmentId?: string;
  focusSessionId?: string | null;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(focusSessionId ?? null);
  const [filters, setFilters] = useState<EssEvidenceFilters>(EMPTY_ESS_EVIDENCE_FILTERS);
  const [context, setContext] = useState<EssEvidenceContext>(EMPTY_ESS_EVIDENCE_CONTEXT);
  const [showFieldErrors, setShowFieldErrors] = useState(false);
  const fieldRefs = useRef<Partial<Record<NarrativeFieldKey, HTMLInputElement | HTMLTextAreaElement | null>>>({});

  const candidates = useMemo(() => sessions.map(describeEssEvidenceCandidate), [sessions]);
  const visibleCandidates = useMemo(() => filterEssEvidenceCandidates(candidates, filters), [candidates, filters]);

  const selected = useMemo(() => {
    const allowed = new Set(visibleCandidates.map((row) => row.sessionId));
    const visibleSessions = sessions.filter((session) => allowed.has(session.pvci_transcriptsessionid));
    return selectEssEvidenceSession(visibleSessions, selectedId) ?? visibleSessions[0] ?? null;
  }, [sessions, visibleCandidates, selectedId]);

  const evidence = useSessionEvidence(selected?.pvci_transcriptsessionid ?? null, selected?.pvci_transcriptid);

  const preview = useMemo(() => {
    if (!selected) return null;
    return buildEssEvidencePackage({
      session: selected,
      detail: evidence.detail,
      turns: evidence.turns,
      context,
      generatedUtc: PREVIEW_TIMESTAMP,
      hostEnvironmentId,
    });
  }, [selected, evidence.detail, evidence.turns, context, hostEnvironmentId]);

  const candidate = selected ? describeEssEvidenceCandidate(selected) : null;
  const missingRequired = missingNarrativeFields(context);
  const unavailableWarnings = (preview?.integrity.warnings ?? [])
    .filter((warning) => !warning.startsWith(TRUNCATION_WARNING_PREFIX));

  const updateContext = <K extends keyof EssEvidenceContext>(key: K, value: EssEvidenceContext[K]) =>
    setContext((current) => ({ ...current, [key]: value }));

  const download = () => {
    if (!selected) return;
    if (missingRequired.length > 0) {
      setShowFieldErrors(true);
      fieldRefs.current[missingRequired[0].key]?.focus();
      return;
    }
    const generatedUtc = new Date().toISOString();
    const evidencePackage = buildEssEvidencePackage({
      session: selected,
      detail: evidence.detail,
      turns: evidence.turns,
      context,
      generatedUtc,
      hostEnvironmentId,
    });
    const blob = new Blob([JSON.stringify(evidencePackage, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = essEvidenceFilename(selected.pvci_transcriptsessionid, context.issueTitle, generatedUtc);
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="ess-evidence">
      <header className="ess-evidence-head">
        <div>
          <h2>ESS Evidence</h2>
          <p className="muted small">
            Standardized support packages built only from collected Employee Self-Service transcript sessions.
            Every export is masked, independently of any on-screen reveal.
          </p>
        </div>
        <div className="ess-evidence-scope">
          <strong>{sessions.length}</strong>
          <span>qualifying ESS session{sessions.length === 1 ? "" : "s"} in scope</span>
        </div>
      </header>

      {evidence.error && <div className="error">{evidence.error}</div>}

      <div className="ess-evidence-warnings" aria-label="Evidence warnings">
        {candidate?.payloadTruncated && (
          <div className="ess-hint bad">
            <strong>Stored payload is truncated</strong>
            <span>This transcript was clipped at capture, so tool, knowledge, and reasoning evidence may be incomplete.</span>
            <small>The package records truncation so the reader does not treat missing evidence as absent behavior.</small>
          </div>
        )}
        {unavailableWarnings.map((warning) => (
          <div key={warning} className="ess-hint warn">
            <strong>Evidence unavailable</strong>
            <span>{warning}</span>
            <small>The package keeps this as an explicit unavailable state instead of omitting it.</small>
          </div>
        ))}
        {candidate?.workdayHrPolicyApplies && (
          <div className="ess-hint warn">
            <strong>Workday HR session</strong>
            <span>Workday HR field and pattern detectors apply to this export, which always remains masked.</span>
            <small>This is the Workday HR detector policy, not a general ESS policy.</small>
          </div>
        )}
      </div>

      <div className="ess-evidence-action">
        <button type="button" className="privacy-action" onClick={download} disabled={!selected || evidence.loading}>
          Download evidence package (JSON)
        </button>
        <span className={`ess-evidence-ready ${missingRequired.length ? "warn" : "good"}`}>
          {missingRequired.length
            ? `Needs ${missingRequired.length} more detail${missingRequired.length === 1 ? "" : "s"}: ${missingRequired.map((field) => field.label.toLowerCase()).join(", ")}`
            : "Ready to download"}
        </span>
        <span className="muted small">
          {evidence.loading
            ? "Loading session evidence…"
            : preview
              ? `Schema version 1 · masked · ${preview.privacy.replacementCount} sensitive value${preview.privacy.replacementCount === 1 ? "" : "s"} replaced`
              : "Schema version 1 · masked"}
        </span>
      </div>

      <div className="ess-evidence-body">
        <EssEvidencePicker
          candidates={candidates}
          visible={visibleCandidates}
          selectedId={selected?.pvci_transcriptsessionid ?? null}
          filters={filters}
          loading={loading}
          onSelect={setSelectedId}
          onFiltersChange={setFilters}
        />
        <EssEvidenceForm
          context={context}
          showFieldErrors={showFieldErrors}
          registerField={(key, element) => { fieldRefs.current[key] = element; }}
          onChange={updateContext}
        />
      </div>

      <EssEvidenceCompleteness
        checklist={preview?.completeness.checklist ?? []}
        external={preview?.completeness.missingExternalEvidence ?? []}
        loading={evidence.loading}
      />

      <details className="technical-details">
        <summary>Package provenance and privacy metadata</summary>
        <dl className="technical-grid">
          <Fact k="Schema version" v="1" />
          <Fact k="Evidence family" v="ess" />
          <Fact k="Session ID" v={candidate?.sessionId} />
          <Fact k="Native transcript ID" v={selected?.pvci_transcriptid ?? "unavailable"} />
          <Fact k="Debug conversation ID" v="unverified — not proven equal to the native transcript ID" />
          <Fact k="Identity correlation" v={selected?.pvci_correlationstatus ?? "unknown"} />
          <Fact k="Channel" v={candidate?.channel} />
          <Fact k="Masking" v="Always applied, independent of on-screen reveal" />
        </dl>
      </details>
    </div>
  );
}

function Fact({ k, v }: { k: string; v?: string | number | null }) {
  return (
    <div className="fact">
      <dt>{k}</dt>
      <dd>{v === undefined || v === null || v === "" ? "—" : String(v)}</dd>
    </div>
  );
}
