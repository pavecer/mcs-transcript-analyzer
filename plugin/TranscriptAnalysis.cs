using System;
using System.Collections.Generic;
using System.Globalization;

namespace PvciTranscripts
{
    internal class TranscriptDiagnostics
    {
        public string TopicId;
        public string TopicName;
        public int UserErrorCount;
        public string PrimaryErrorCode;
        public string PrimaryErrorMessage;
        public string PrimaryErrorTopic;
        public string ErrorCategory;
    }

    internal static class TranscriptAnalysis
    {
        internal static bool IsUserErrorTrace(object activity)
        {
            if (!string.Equals(Json.Str(activity, "valueType"), "ErrorTraceData", StringComparison.Ordinal))
                return false;
            object isUserError = Json.Get(Json.Get(activity, "value"), "isUserError");
            return isUserError is bool && (bool)isUserError;
        }

        internal static TranscriptDiagnostics ExtractDiagnostics(List<object> activities)
        {
            var diagnostics = new TranscriptDiagnostics();
            string currentTopic = null;
            foreach (object activity in activities)
            {
                if (string.Equals(
                    Json.Str(activity, "name"),
                    "DynamicPlanStepTriggered",
                    StringComparison.OrdinalIgnoreCase))
                {
                    object step = Json.Get(activity, "value");
                    string stepId = Json.Str(step, "taskDialogId");
                    if (!string.IsNullOrWhiteSpace(stepId))
                    {
                        currentTopic = LastSegment(stepId.Trim());
                        string stepType = Json.Str(step, "type");
                        if (string.Equals(stepType, "CustomTopic", StringComparison.OrdinalIgnoreCase)
                            || (string.IsNullOrWhiteSpace(stepType)
                                && !stepId.StartsWith("MCP:", StringComparison.OrdinalIgnoreCase)
                                && stepId.IndexOf("search", StringComparison.OrdinalIgnoreCase) < 0
                                && stepId.IndexOf("knowledge", StringComparison.OrdinalIgnoreCase) < 0))
                        {
                            if (string.IsNullOrEmpty(diagnostics.TopicId))
                                diagnostics.TopicId = stepId.Trim();
                            if (string.IsNullOrEmpty(diagnostics.TopicName))
                                diagnostics.TopicName = currentTopic;
                        }
                    }
                }

                if (!IsUserErrorTrace(activity))
                    continue;

                object value = Json.Get(activity, "value");
                diagnostics.UserErrorCount++;
                diagnostics.PrimaryErrorCode = TrimOrNull(Json.Str(value, "errorCode"));
                diagnostics.PrimaryErrorMessage = TrimOrNull(Json.Str(value, "errorMessage"));
                diagnostics.PrimaryErrorTopic = currentTopic;
                diagnostics.ErrorCategory = ErrorCategory(
                    diagnostics.PrimaryErrorCode,
                    diagnostics.PrimaryErrorMessage);
            }
            return diagnostics;
        }

        internal static string ErrorReason(string errorCode, string errorMessage)
        {
            if (!string.IsNullOrEmpty(errorCode) && !string.IsNullOrEmpty(errorMessage))
                return errorCode + ": " + errorMessage;
            return errorCode ?? errorMessage;
        }

        internal static List<object> ExtractKnowledgeCalls(List<object> activities)
        {
            var calls = new List<object>();
            string stepId = null;
            string task = null;
            string startedUtc = null;
            long? startedMs = null;

            foreach (object activity in activities)
            {
                string name = Json.Str(activity, "name") ?? string.Empty;
                object value = Json.Get(activity, "value");
                if (name.Equals("DynamicPlanStepTriggered", StringComparison.OrdinalIgnoreCase))
                {
                    string candidateTask = Json.Str(value, "taskDialogId");
                    bool isKnowledge = string.Equals(
                        Json.Str(value, "type"),
                        "KnowledgeSource",
                        StringComparison.OrdinalIgnoreCase)
                        || (!string.IsNullOrEmpty(candidateTask)
                            && candidateTask.IndexOf("search", StringComparison.OrdinalIgnoreCase) >= 0);
                    if (isKnowledge && !string.IsNullOrEmpty(candidateTask))
                    {
                        stepId = Json.Str(value, "stepId");
                        task = candidateTask;
                        startedMs = Json.Long(activity, "timestampMs");
                        long? startedSeconds = Json.Long(activity, "timestamp");
                        startedUtc = startedSeconds.HasValue
                            ? FormatIso(EpochUtc(startedSeconds.Value))
                            : null;
                    }
                    continue;
                }

                if (!string.Equals(
                    Json.Str(activity, "valueType"),
                    "KnowledgeTraceData",
                    StringComparison.Ordinal))
                    continue;

                List<object> cited =
                    Json.Arr(Json.Get(value, "citedKnowledgeSources")) ?? new List<object>();
                List<object> failedSources =
                    Json.Arr(Json.Get(value, "failedKnowledgeSourcesTypes")) ?? new List<object>();
                string completion = Json.Str(value, "completionState");
                bool completionFailed =
                    !string.Equals(completion, "Answered", StringComparison.OrdinalIgnoreCase)
                    && !string.Equals(completion, "Completed", StringComparison.OrdinalIgnoreCase)
                    && !string.Equals(completion, "Complete", StringComparison.OrdinalIgnoreCase)
                    && !string.Equals(completion, "Succeeded", StringComparison.OrdinalIgnoreCase);
                long? finishedMs = Json.Long(activity, "timestampMs");
                object searchedValue = Json.Get(value, "isKnowledgeSearched");

                calls.Add(new Dictionary<string, object>(StringComparer.Ordinal)
                {
                    { "step_id", stepId },
                    { "task", task ?? "Knowledge search" },
                    { "correlation", "nearest_prior_knowledge_step" },
                    { "started_utc", startedUtc },
                    {
                        "duration_ms",
                        startedMs.HasValue && finishedMs.HasValue
                            ? (object)(double)(finishedMs.Value - startedMs.Value)
                            : null
                    },
                    { "completion_state", completion },
                    { "searched", searchedValue is bool && (bool)searchedValue },
                    { "cited_sources", cited },
                    { "failed_source_types", failedSources },
                    { "failed", failedSources.Count > 0 || completionFailed },
                });
            }
            return calls;
        }

        private static string ErrorCategory(string errorCode, string errorMessage)
        {
            string text =
                ((errorCode ?? string.Empty) + " " + (errorMessage ?? string.Empty))
                .ToLowerInvariant();
            if (text.Contains("authentication")
                || text.Contains("unauthorized")
                || text.Contains("forbidden")
                || text.Contains("consent"))
                return "Authentication";
            if (text.Contains("connector")
                || text.Contains("connection")
                || text.Contains("reference id"))
                return "Connector";
            if (text.Contains("expression") || text.Contains("contentvalidation"))
                return "Topic expression";
            return "Topic runtime";
        }

        private static string TrimOrNull(string value)
        {
            return string.IsNullOrWhiteSpace(value) ? null : value.Trim();
        }

        private static string LastSegment(string value)
        {
            if (string.IsNullOrEmpty(value))
                return value;
            int index = value.LastIndexOf('.');
            return index >= 0 ? value.Substring(index + 1) : value;
        }

        private static DateTime EpochUtc(long seconds)
        {
            if (seconds > 10000000000L)
                seconds /= 1000;
            return new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc).AddSeconds(seconds);
        }

        private static string FormatIso(DateTime? value)
        {
            return value.HasValue
                ? value.Value.ToUniversalTime().ToString(
                    "yyyy-MM-ddTHH:mm:ssZ",
                    CultureInfo.InvariantCulture)
                : null;
        }
    }
}
