import { useEffect, useMemo, useState } from "react";
import { Pvci_transcriptsessionsService } from "./generated/services/Pvci_transcriptsessionsService";
import { Pvci_transcriptturnsService } from "./generated/services/Pvci_transcriptturnsService";
import { JsonTree } from "./components/JsonTree";
import { Timeline } from "./components/Timeline";
import { ToolCalls } from "./components/ToolCalls";
import { FlowRuns } from "./components/FlowRuns";
import { Trends } from "./components/Trends";
import { fmtDuration, fmtMs, fmtTime, latencyBand, safeParse, type SessionRow, type TurnRow } from "./lib/model";
import "./App.css";

const SESSION_FIELDS = [
  "pvci_transcriptsessionid", "pvci_transcriptid", "pvci_name",
  "pvci_userdisplayname", "pvci_userupn", "pvci_useraadobjectid",
  "pvci_channel", "pvci_botname",
  "pvci_startdatetimeutc", "pvci_enddatetimeutc", "pvci_durationseconds",
  "pvci_messagecount", "pvci_activitycount", "pvci_eventcount",
  "pvci_userturncount", "pvci_agentturncount",
  "pvci_istestmode", "pvci_multiuseranomaly", "pvci_payloadtruncated",
  "pvci_correlationstatus", "pvci_initialusermessage",
  "pvci_firstresponsems", "pvci_avgresponsems", "pvci_maxresponsems",
  "pvci_toolcallcount", "pvci_toolerrorcount", "pvci_tooltotalms", "pvci_maxtoolms",
  "pvci_sessionoutcome", "pvci_outcomereason",
  "pvci_isresolvedimplied", "pvci_turncount",
  "pvci_flowruncount", "pvci_flowrunfailurecount", "pvci_flowrunmaxms",
];

// Fetched only for the selected row - these payloads reach ~140 KB each.
const SESSION_DETAIL_FIELDS = [
  "pvci_transcriptsessionid",
  "pvci_activitiesjson", "pvci_conversationjson", "pvci_planeventsjson",
  "pvci_metadatajson", "pvci_toolcallsjson", "pvci_flowrunsjson",
];

const TURN_FIELDS = [
  "pvci_transcriptturnid", "pvci_transcriptid", "pvci_turnindex",
  "pvci_activitytype", "pvci_speaker", "pvci_role", "pvci_eventname",
  "pvci_channelid", "pvci_timestamputc", "pvci_turntext", "pvci_valuejson", "pvci_latencyms",
];

type Tab = "replay" | "tools" | "flows" | "conversation" | "reasoning" | "raw";

const TAB_LABEL: Record<Tab, string> = {
  replay: "Replay",
  tools: "Tool Calls",
  flows: "Flow Runs",
  conversation: "Conversation JSON",
  reasoning: "Agent Reasoning",
  raw: "Full Transcript JSON",
};

export default function App() {
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [selected, setSelected] = useState<SessionRow | null>(null);
  const [detail, setDetail] = useState<SessionRow | null>(null);
  const [turns, setTurns] = useState<TurnRow[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [loadingTurns, setLoadingTurns] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [hideTest, setHideTest] = useState(false);
  const [tab, setTab] = useState<Tab>("replay");
  const [jsonFilter, setJsonFilter] = useState("");
  const [view, setView] = useState<"sessions" | "trends">("sessions");

  useEffect(() => {
    void (async () => {
      try {
        const res = await Pvci_transcriptsessionsService.getAll({
          select: SESSION_FIELDS,
          orderBy: ["pvci_startdatetimeutc desc"],
          top: 200,
        });
        const rows = (res.data ?? []) as unknown as SessionRow[];
        setSessions(rows);
        if (rows.length) setSelected(rows[0]);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoadingSessions(false);
      }
    })();
  }, []);

  useEffect(() => {
    const transcriptId = selected?.pvci_transcriptid;
    const sessionId = selected?.pvci_transcriptsessionid;
    let cancelled = false;

    void (async () => {
      if (!transcriptId || !sessionId) {
        if (!cancelled) {
          setTurns([]);
          setDetail(null);
        }
        return;
      }
      setLoadingTurns(true);
      setDetail(null);
      try {
        const [turnRes, detailRes] = await Promise.all([
          Pvci_transcriptturnsService.getAll({
            select: TURN_FIELDS,
            filter: `pvci_transcriptid eq '${transcriptId}'`,
            orderBy: ["pvci_turnindex asc"],
            top: 500,
          }),
          Pvci_transcriptsessionsService.get(sessionId, { select: SESSION_DETAIL_FIELDS }),
        ]);
        if (!cancelled) {
          setTurns((turnRes.data ?? []) as unknown as TurnRow[]);
          setDetail((detailRes.data ?? null) as unknown as SessionRow | null);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoadingTurns(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [selected]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return sessions.filter((s) => {
      if (hideTest && s.pvci_istestmode) return false;
      if (!q) return true;
      return [s.pvci_userdisplayname, s.pvci_userupn, s.pvci_channel, s.pvci_initialusermessage, s.pvci_botname]
        .some((v) => (v ?? "").toLowerCase().includes(q));
    });
  }, [sessions, search, hideTest]);

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <h1>Conversation Insights</h1>
          <span className="muted small">{sessions.length} sessions</span>
        </div>
        <div className="viewswitch">
          <button className={view === "sessions" ? "on" : ""} onClick={() => setView("sessions")}>Sessions</button>
          <button className={view === "trends" ? "on" : ""} onClick={() => setView("trends")}>Trends</button>
        </div>
        <input
          className="search"
          placeholder="Search user, channel, first message…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <label className="checkline">
          <input type="checkbox" checked={hideTest} onChange={(e) => setHideTest(e.target.checked)} />
          Hide test-mode sessions
        </label>

        <div className="session-list">
          {loadingSessions && <div className="muted pad">Loading…</div>}
          {!loadingSessions && !filtered.length && <div className="muted pad">No sessions match.</div>}
          {filtered.map((s) => (
            <button
              key={s.pvci_transcriptsessionid}
              className={`session-item${selected?.pvci_transcriptsessionid === s.pvci_transcriptsessionid ? " active" : ""}`}
              onClick={() => { setSelected(s); setTab("replay"); }}
            >
              <div className="si-top">
                <span className="si-user">{s.pvci_userdisplayname ?? "Unknown user"}</span>
                <span className="chip">{s.pvci_channel ?? "—"}</span>
              </div>
              <div className="si-sub muted small">
                {fmtTime(s.pvci_startdatetimeutc)} · {s.pvci_messagecount ?? 0} msg · {fmtDuration(s.pvci_durationseconds)}
              </div>
              <div className="si-metrics">
                <span className={`lat ${latencyBand(s.pvci_maxresponsems)}`}>
                  slowest reply {fmtMs(s.pvci_maxresponsems)}
                </span>
                {(s.pvci_toolcallcount ?? 0) > 0 && (
                  <span className={`lat ${s.pvci_toolerrorcount ? "bad" : "none"}`}>
                    {s.pvci_toolcallcount} tools
                    {s.pvci_toolerrorcount ? ` · ${s.pvci_toolerrorcount} failed` : ""}
                  </span>
                )}
              </div>
              {s.pvci_initialusermessage && <div className="si-snippet">{s.pvci_initialusermessage.slice(0, 90)}</div>}
              <div className="si-flags">
                {s.pvci_istestmode && <span className="flag test">test</span>}
                {s.pvci_multiuseranomaly && <span className="flag warn">multi-user</span>}
                {s.pvci_payloadtruncated && <span className="flag warn">truncated</span>}
                {s.pvci_correlationstatus && s.pvci_correlationstatus !== "exact" && (
                  <span className="flag warn">{s.pvci_correlationstatus}</span>
                )}
              </div>
            </button>
          ))}
        </div>
      </aside>

      <main className="main">
        {error && <div className="error">{error}</div>}

        {view === "trends" && <Trends sessions={sessions} loading={loadingSessions} />}

        {view === "sessions" && !selected && !loadingSessions && <div className="muted pad">Select a session.</div>}

        {view === "sessions" && selected && (
          <>
            <header className="detail-head">
              <div>
                <h2>{selected.pvci_userdisplayname ?? "Unknown user"}</h2>
                <div className="muted small">{selected.pvci_userupn ?? selected.pvci_useraadobjectid ?? "—"}</div>
              </div>
              <dl className="facts">
                <Fact k="Channel" v={selected.pvci_channel} />
                <Fact k="Agent" v={selected.pvci_botname} />
                <Fact k="Started" v={fmtTime(selected.pvci_startdatetimeutc)} />
                <Fact k="Duration" v={fmtDuration(selected.pvci_durationseconds)} />
                <Fact k="Turns" v={`${selected.pvci_userturncount ?? 0} user / ${selected.pvci_agentturncount ?? 0} agent`} />
                <Fact k="Outcome" v={`${selected.pvci_sessionoutcome ?? "—"} / ${selected.pvci_outcomereason ?? "—"}`} />
                <Fact k="First reply" v={fmtMs(selected.pvci_firstresponsems)} />
                <Fact k="Slowest reply" v={fmtMs(selected.pvci_maxresponsems)} />
                <Fact k="Tool calls" v={`${selected.pvci_toolcallcount ?? 0}${selected.pvci_toolerrorcount ? ` (${selected.pvci_toolerrorcount} failed)` : ""}`} />
                <Fact k="Slowest tool" v={fmtMs(selected.pvci_maxtoolms)} />
                <Fact
                  k="Flow runs"
                  v={`${selected.pvci_flowruncount ?? 0}${selected.pvci_flowrunfailurecount ? ` (${selected.pvci_flowrunfailurecount} failed)` : ""}`}
                />
              </dl>
            </header>

            <nav className="tabs">
              {(Object.keys(TAB_LABEL) as Tab[]).map((t) => (
                <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>
                  {TAB_LABEL[t]}
                </button>
              ))}
            </nav>

            <section className="pane">
              {tab === "replay" ? (
                <Timeline turns={turns} loading={loadingTurns} />
              ) : tab === "tools" ? (
                <ToolCalls json={detail?.pvci_toolcallsjson} loading={loadingTurns} />
              ) : tab === "flows" ? (
                <FlowRuns json={detail?.pvci_flowrunsjson} loading={loadingTurns} />
              ) : (
                <>
                  <input
                    className="search json-filter"
                    placeholder="Filter JSON keys and values…"
                    value={jsonFilter}
                    onChange={(e) => setJsonFilter(e.target.value)}
                  />
                  <JsonPane
                    text={
                      tab === "conversation" ? detail?.pvci_conversationjson
                        : tab === "reasoning" ? detail?.pvci_planeventsjson
                        : detail?.pvci_activitiesjson
                    }
                    filter={jsonFilter}
                    depth={tab === "raw" ? 2 : 3}
                    extra={tab === "raw" ? detail?.pvci_metadatajson : undefined}
                    loading={loadingTurns}
                  />
                </>
              )}
            </section>
          </>
        )}
      </main>
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

function JsonPane({ text, filter, depth, extra, loading }:
  { text?: string; filter: string; depth: number; extra?: string; loading?: boolean }) {
  const parsed = safeParse(text);
  const parsedExtra = safeParse(extra);

  if (loading) return <div className="muted pad">Loading payload…</div>;
  if (parsed === undefined) return <div className="muted pad">No JSON stored for this session.</div>;

  return (
    <>
      <div className="muted small pad-sm">{(text ?? "").length.toLocaleString()} chars</div>
      <JsonTree value={parsed} initialCollapseDepth={depth} filter={filter} />
      {parsedExtra !== undefined && (
        <>
          <h3 className="sub">Transcript metadata</h3>
          <JsonTree value={parsedExtra} initialCollapseDepth={3} filter={filter} />
        </>
      )}
    </>
  );
}
