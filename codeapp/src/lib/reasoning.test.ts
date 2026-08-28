import { describe, expect, it } from "vitest";
import { buildReasoningPlans, formatPlannedToolLabel, getPlannedToolSteps, type PlanEvent } from "./reasoning";
import type { KnowledgeCall } from "./model";

describe("buildReasoningPlans", () => {
  it("groups a completed topic lifecycle and exposes names instead of argument values", () => {
    const events: PlanEvent[] = [
      { name: "DynamicPlanReceived", at: 100, value: { planIdentifier: "plan-1", isFinalPlan: false, steps: ["topic"] } },
      { name: "DynamicPlanReceivedDebug", at: 100, value: { planIdentifier: "plan-1", ask: "List my tickets", summary: "" } },
      { name: "DynamicPlanStepTriggered", at: 101, value: { planIdentifier: "plan-1", stepId: "step-1", taskDialogId: "agent.topic.GetTickets", type: "CustomTopic", thought: "Retrieve the user's tickets." } },
      { name: "DynamicPlanStepBindUpdate", at: 102, value: { planIdentifier: "plan-1", stepId: "step-1", arguments: { TicketState: "open" }, autoFilledArguments: ["TicketState"] } },
      { name: "DynamicPlanStepFinished", at: 104, value: { planIdentifier: "plan-1", stepId: "step-1", state: "completed", executionTime: "00:00:02.5000000", observation: { ServiceNowData: [] } } },
      { name: "DynamicPlanFinished", at: 105, value: { planId: "plan-1" } },
    ];

    const plans = buildReasoningPlans(events, []);

    expect(plans).toHaveLength(1);
    expect(plans[0].request).toBe("List my tickets");
    expect(plans[0].finished).toBe(true);
    expect(plans[0].steps[0]).toMatchObject({
      task: "agent.topic.GetTickets",
      state: "completed",
      executionMs: 2500,
      argumentNames: ["TicketState"],
      autoFilledArguments: ["TicketState"],
      observationKeys: ["ServiceNowData"],
    });
  });

  it("links an answered knowledge outcome when no step-finished event was retained", () => {
    const events: PlanEvent[] = [
      { name: "DynamicPlanReceived", at: 100, value: { planIdentifier: "plan-k", isFinalPlan: false, steps: ["search"] } },
      { name: "DynamicPlanReceivedDebug", at: 100, value: { planIdentifier: "plan-k", ask: "How do I reset my password?" } },
      { name: "DynamicPlanStepTriggered", at: 101, value: { planIdentifier: "plan-k", stepId: "step-k", taskDialogId: "P:UniversalSearchTool", type: "KnowledgeSource", thought: "Retrieve approved guidance." } },
      { name: "DynamicPlanStepBindUpdate", at: 102, value: { planIdentifier: "plan-k", stepId: "step-k", arguments: { search_query: "hidden", search_keywords: "hidden" }, autoFilledArguments: ["search_query", "search_keywords"] } },
      { name: "DynamicPlanFinished", at: 115, value: { planId: "plan-k" } },
    ];
    const knowledge: KnowledgeCall[] = [{
      step_id: "step-k",
      task: "P:UniversalSearchTool",
      correlation: "nearest_prior_knowledge_step",
      duration_ms: 13299,
      completion_state: "Answered",
      searched: true,
      cited_sources: ["agent.topic.ServiceNowKB_source"],
      failed_source_types: [],
      failed: false,
    }];

    const plans = buildReasoningPlans(events, knowledge);

    expect(plans[0].steps[0].state).toBeUndefined();
    expect(plans[0].steps[0].planFinished).toBe(true);
    expect(plans[0].steps[0].knowledge?.completion_state).toBe("Answered");
    expect(plans[0].steps[0].argumentNames).toEqual(["search_query", "search_keywords"]);
  });

  it("retains MCP LlmSkill identity separately from topics", () => {
    const events: PlanEvent[] = [
      { name: "DynamicPlanStepTriggered", at: 100, value: { planIdentifier: "plan-mcp", stepId: "step-mcp", taskDialogId: "MCP:agent.action.Jira-JiraMCPServer:ListIssues", type: "LlmSkill" } },
    ];

    const plans = buildReasoningPlans(events, []);

    expect(plans[0].steps[0]).toMatchObject({
      type: "LlmSkill",
      task: "MCP:agent.action.Jira-JiraMCPServer:ListIssues",
    });
  });

  it("exposes planned MCP details without creating an exact invocation", () => {
    const events: PlanEvent[] = [
      { name: "DynamicPlanStepTriggered", at: 100, value: { planIdentifier: "plan-mcp", stepId: "step-mcp", taskDialogId: "MCP:agent.action.Jira-JiraMCPServer:ListIssues", type: "LlmSkill" } },
      { name: "DynamicPlanStepBindUpdate", at: 101, value: { planIdentifier: "plan-mcp", stepId: "step-mcp", arguments: { project: "hidden" } } },
      { name: "DynamicPlanStepFinished", at: 102, value: { planIdentifier: "plan-mcp", stepId: "step-mcp", state: "completed", executionTime: "00:00:01.2500000" } },
    ];

    expect(getPlannedToolSteps(events)).toEqual([
      expect.objectContaining({
        task: "MCP:agent.action.Jira-JiraMCPServer:ListIssues",
        state: "completed",
        executionMs: 1250,
        argumentNames: ["project"],
      }),
    ]);
  });

  it("formats an MCP action without repeated provider names", () => {
    expect(formatPlannedToolLabel("MCP:agent.action.Jira-JiraMCPServer:ListIssues"))
      .toBe("Jira MCP Server · List Issues");
  });
});
