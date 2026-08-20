import type { KnowledgeCall } from "./model";

export interface PlanEvent {
  name?: string;
  at?: string | number;
  value?: Record<string, unknown>;
}

export interface ReasoningStep {
  id: string;
  task?: string;
  type?: string;
  rationale?: string;
  startedAt?: string;
  argumentNames: string[];
  autoFilledArguments: string[];
  state?: string;
  executionMs?: number | null;
  observationKeys: string[];
  planFinished: boolean;
  knowledge?: KnowledgeCall;
}

export interface ReasoningPlan {
  id: string;
  request?: string;
  summary?: string;
  isFinal: boolean;
  startedAt?: string;
  steps: ReasoningStep[];
  finished: boolean;
}

export function buildReasoningPlans(events: PlanEvent[], knowledgeCalls: KnowledgeCall[]): ReasoningPlan[] {
  const plans = new Map<string, ReasoningPlan>();
  const order: string[] = [];
  const stepToPlan = new Map<string, string>();
  let latestPlanId: string | undefined;

  const ensurePlan = (id: string): ReasoningPlan => {
    const existing = plans.get(id);
    if (existing) return existing;
    const created: ReasoningPlan = { id, isFinal: false, steps: [], finished: false };
    plans.set(id, created);
    order.push(id);
    return created;
  };

  for (const event of events) {
    const value = event.value ?? {};
    const eventPlanId = stringValue(value.planIdentifier) ?? stringValue(value.planId) ?? latestPlanId ?? `plan-${order.length + 1}`;
    const plan = ensurePlan(eventPlanId);
    latestPlanId = eventPlanId;

    if (event.name === "DynamicPlanReceived") {
      plan.isFinal = value.isFinalPlan === true;
      plan.startedAt = eventTime(event.at);
    }
    if (event.name === "DynamicPlanReceivedDebug") {
      plan.request = stringValue(value.ask) || plan.request;
      plan.summary = stringValue(value.summary) || plan.summary;
    }
    if (event.name === "DynamicPlanStepTriggered") {
      const stepId = stringValue(value.stepId) ?? `step-${plan.steps.length + 1}`;
      if (!plan.steps.some((step) => step.id === stepId)) {
        plan.steps.push({
          id: stepId,
          task: stringValue(value.taskDialogId),
          type: stringValue(value.type),
          rationale: stringValue(value.thought),
          startedAt: eventTime(event.at),
          argumentNames: [],
          autoFilledArguments: [],
          observationKeys: [],
          planFinished: false,
          knowledge: knowledgeCalls.find((call) => call.step_id === stepId),
        });
      }
      stepToPlan.set(stepId, eventPlanId);
    }
    if (event.name === "DynamicPlanStepBindUpdate") {
      const stepId = stringValue(value.stepId);
      const targetPlan = stepId ? ensurePlan(stepToPlan.get(stepId) ?? eventPlanId) : plan;
      const step = stepId ? targetPlan.steps.find((candidate) => candidate.id === stepId) : undefined;
      if (step) {
        step.argumentNames = objectKeys(value.arguments);
        step.autoFilledArguments = stringArray(value.autoFilledArguments);
      }
    }
    if (event.name === "DynamicPlanStepFinished") {
      const stepId = stringValue(value.stepId);
      const targetPlan = stepId ? ensurePlan(stepToPlan.get(stepId) ?? eventPlanId) : plan;
      const step = stepId ? targetPlan.steps.find((candidate) => candidate.id === stepId) : undefined;
      if (step) {
        step.state = stringValue(value.state)?.toLowerCase();
        step.executionMs = durationTextMs(stringValue(value.executionTime));
        step.observationKeys = objectKeys(value.observation);
      }
    }
    if (event.name === "DynamicPlanFinished") {
      plan.finished = true;
      plan.steps.forEach((step) => { step.planFinished = true; });
    }
  }

  return order.map((id) => plans.get(id)!).filter((plan) => plan.steps.length || plan.request || plan.startedAt);
}

function eventTime(value?: string | number): string | undefined {
  if (typeof value === "number" || (typeof value === "string" && /^\d+$/.test(value))) {
    const numeric = Number(value);
    const date = new Date(numeric > 10_000_000_000 ? numeric : numeric * 1000);
    return Number.isNaN(date.getTime()) ? undefined : date.toISOString().slice(11, 19);
  }
  if (typeof value === "string") {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toISOString().slice(11, 19);
  }
  return undefined;
}

function durationTextMs(value?: string): number | null {
  if (!value) return null;
  const match = /^(\d+):(\d+):(\d+)(?:\.(\d+))?$/.exec(value);
  if (!match) return null;
  const fraction = Number(`0.${match[4] ?? "0"}`) * 1000;
  return Number(match[1]) * 3_600_000 + Number(match[2]) * 60_000 + Number(match[3]) * 1000 + Math.round(fraction);
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function objectKeys(value: unknown): string[] {
  return value && typeof value === "object" && !Array.isArray(value) ? Object.keys(value) : [];
}
