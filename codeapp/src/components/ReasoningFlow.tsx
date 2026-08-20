import { useMemo, useState } from "react";
import { JsonTree } from "./JsonTree";
import { fmtMs, safeParse, type Json, type KnowledgeCall } from "../lib/model";
import { buildReasoningPlans, type PlanEvent, type ReasoningStep } from "../lib/reasoning";

export function ReasoningFlow({ json, knowledgeJson, loading }: { json?: string; knowledgeJson?: string; loading?: boolean }) {
  const [showEvidence, setShowEvidence] = useState(false);
  const events = useMemo(() => (safeParse(json) as unknown as PlanEvent[] | undefined) ?? [], [json]);
  const knowledgeCalls = useMemo(() => (safeParse(knowledgeJson) as unknown as KnowledgeCall[] | undefined) ?? [], [knowledgeJson]);
  const plans = useMemo(() => buildReasoningPlans(events, knowledgeCalls), [events, knowledgeCalls]);

  if (loading) return <div className="muted pad">Loading orchestration evidence…</div>;
  if (!events.length) return <div className="muted pad">No DynamicPlan orchestration events were retained for this session.</div>;

  return (
    <div className="reasoning-flow">
      <div className="reasoning-intro">
        <div>
          <h3>Agent orchestration</h3>
          <p>Recorded routing decisions and observable step lifecycle. This is operational telemetry, not hidden chain-of-thought.</p>
        </div>
        <button className={showEvidence ? "on" : ""} onClick={() => setShowEvidence(!showEvidence)}>
          {showEvidence ? "Hide raw evidence" : "Show raw evidence"}
        </button>
      </div>

      <div className="reasoning-summary">
        <span><strong>{plans.length}</strong> plan{plans.length === 1 ? "" : "s"}</span>
        <span><strong>{plans.reduce((total, plan) => total + plan.steps.length, 0)}</strong> selected step{plans.reduce((total, plan) => total + plan.steps.length, 0) === 1 ? "" : "s"}</span>
        <span><strong>{plans.reduce((total, plan) => total + plan.steps.filter((step) => step.state === "completed").length, 0)}</strong> completion event{plans.reduce((total, plan) => total + plan.steps.filter((step) => step.state === "completed").length, 0) === 1 ? "" : "s"}</span>
      </div>

      <div className="reasoning-plans">
        {plans.map((plan, planIndex) => (
          <section className="reasoning-plan" key={`${plan.id}-${planIndex}`}>
            <div className="reasoning-plan-head">
              <span className="reasoning-index">{planIndex + 1}</span>
              <div>
                <strong>{plan.request || "Orchestrator created a plan"}</strong>
                <span>{plan.startedAt ?? "Time unavailable"} · {plan.isFinal ? "Final plan" : "Working plan"}</span>
              </div>
              <span className={`conf ${plan.finished ? "high" : "none"}`}>{plan.finished ? "plan ended" : "end not retained"}</span>
            </div>
            {plan.summary && <div className="reasoning-plan-summary">{plan.summary}</div>}

            <div className="reasoning-sequence">
              <ReasoningStage label="Request understood" detail={plan.request || "A plan event was recorded without debug request text."} />
              {plan.steps.map((step, stepIndex) => (
                <ReasoningStepCard step={step} key={`${step.id}-${stepIndex}`} />
              ))}
            </div>
          </section>
        ))}
      </div>

      {showEvidence && (
        <section className="reasoning-evidence">
          <h3>Raw DynamicPlan evidence</h3>
          <JsonTree value={events as unknown as Json} initialCollapseDepth={2} />
        </section>
      )}
    </div>
  );
}

function ReasoningStage({ label, detail }: { label: string; detail: string }) {
  return (
    <div className="reasoning-stage">
      <span className="reasoning-stage-dot" aria-hidden="true" />
      <div><strong>{label}</strong><span>{detail}</span></div>
    </div>
  );
}

function ReasoningStepCard({ step }: { step: ReasoningStep }) {
  const completed = step.state === "completed" || step.knowledge?.failed === false;
  const status = step.knowledge
    ? step.knowledge.failed ? "Knowledge failed" : `Knowledge ${step.knowledge.completion_state ?? "answered"}`
    : step.state === "completed" ? "Step completed" : step.planFinished ? "Plan ended; step finish not retained" : "Step finish not retained";

  return (
    <article className={`reasoning-step ${completed ? "completed" : "incomplete"}`}>
      <div className="reasoning-step-head">
        <span className={`reasoning-kind ${step.type === "KnowledgeSource" ? "knowledge" : "topic"}`}>
          {step.type === "KnowledgeSource" ? "Knowledge" : "Topic / action"}
        </span>
        <strong>{taskLabel(step.task)}</strong>
        <span className={`conf ${completed ? "high" : "none"}`}>{status}</span>
      </div>
      {step.rationale && (
        <div className="reasoning-rationale"><span>Recorded routing rationale</span>{step.rationale}</div>
      )}
      <div className="reasoning-step-grid">
        <div><span>Started</span><strong>{step.startedAt ?? "—"}</strong></div>
        <div><span>Step elapsed</span><strong>{step.knowledge ? fmtMs(step.knowledge.duration_ms) : fmtMs(step.executionMs)}</strong></div>
        <div><span>Inputs prepared</span><strong>{step.argumentNames.length}</strong></div>
        <div><span>Observed outputs</span><strong>{step.observationKeys.length || step.knowledge?.cited_sources.length || 0}</strong></div>
      </div>
      {step.argumentNames.length > 0 && (
        <div className="reasoning-tags">
          <span>Input names</span>
          {step.argumentNames.map((name) => <code key={name}>{name}{step.autoFilledArguments.includes(name) ? " · auto" : ""}</code>)}
        </div>
      )}
      {(step.observationKeys.length > 0 || step.knowledge?.cited_sources.length) ? (
        <div className="reasoning-tags">
          <span>Observable result</span>
          {step.observationKeys.map((name) => <code key={name}>{name}</code>)}
          {step.knowledge?.cited_sources.map((source) => <code key={source}>{sourceLabel(source)}</code>)}
        </div>
      ) : null}
    </article>
  );
}

function taskLabel(value?: string): string {
  const last = value?.split(".").pop()?.replace(/^P:/, "") ?? "Unknown step";
  return last.replace(/([a-z])([A-Z])/g, "$1 $2").replace(/[-_]+/g, " ");
}

function sourceLabel(value: string): string {
  return (value.split(".").pop() ?? value).replace(/_[A-Za-z0-9]+$/, "").replace(/([a-z])([A-Z])/g, "$1 $2");
}
