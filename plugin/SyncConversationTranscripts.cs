using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.ServiceModel;
using System.Text;
using Microsoft.Xrm.Sdk;
using Microsoft.Xrm.Sdk.Query;

namespace PvciTranscripts
{
    /// <summary>
    /// Custom API: pvci_SyncConversationTranscripts.
    /// Reads conversationtranscript rows, parses the Bot Framework activity stream and
    /// upserts pvci_transcriptsession / pvci_transcriptturn / pvci_transcriptidentitymap.
    /// </summary>
    public class SyncConversationTranscripts : IPlugin
    {
        private const string SessionEntity = "pvci_transcriptsession";
        private const string TurnEntity = "pvci_transcriptturn";
        private const string IdentityEntity = "pvci_transcriptidentitymap";
        private const string FlowRunDetailEntity = "pvci_flowrundetail";
        private const string SyncStateEntity = "pvci_syncstate";
        private const string SyncStateRow = "default";

        private const int MemoLimit = 900000;
        private const int TextLimit = 1000;
        private const int DefaultMaxRecords = 20;

        // Flow runs carry no conversation id, so correlation is by time overlap only.
        private const int FlowRunToleranceSeconds = 20;
        private const long PlanStepFallbackMs = 90000;

        private static readonly HashSet<string> NoiseTypes = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { "trace" };
        private static readonly HashSet<string> NoiseEvents = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { "DialogTracing" };

        public void Execute(IServiceProvider serviceProvider)
        {
            var context = (IPluginExecutionContext)serviceProvider.GetService(typeof(IPluginExecutionContext));
            var tracing = (ITracingService)serviceProvider.GetService(typeof(ITracingService));
            var factory = (IOrganizationServiceFactory)serviceProvider.GetService(typeof(IOrganizationServiceFactory));
            IOrganizationService service = factory.CreateOrganizationService(context.UserId);
            SourceEnvironment sourceEnvironment = ResolveSourceEnvironment(service, context);

            bool fullSync = GetInput(context, "FullSync", false);
            int maxRecords = GetInput(context, "MaxRecords", DefaultMaxRecords);
            bool includeTraces = GetInput(context, "IncludeTraces", false);
            bool reprocess = GetInput(context, "Reprocess", false);
            string sinceOverride = GetInput<string>(context, "SinceOverride", null);
            if (maxRecords <= 0) maxRecords = DefaultMaxRecords;

            int processed = 0, created = 0, updated = 0, skipped = 0, turns = 0, anomalies = 0;
            var errors = new List<string>();
            DateTime? watermark = null;
            bool watermarkFrozen = false;

            Entity syncState = GetSyncState(service);
            DateTime? since = null;
            if (!fullSync)
            {
                if (!string.IsNullOrWhiteSpace(sinceOverride))
                {
                    DateTime parsed;
                    if (DateTime.TryParse(sinceOverride, CultureInfo.InvariantCulture, DateTimeStyles.AdjustToUniversal, out parsed))
                        since = parsed;
                }
                else if (syncState != null && syncState.Contains("pvci_lastsyncedcreatedon"))
                {
                    since = syncState.GetAttributeValue<DateTime>("pvci_lastsyncedcreatedon");
                }
            }
            watermark = since;

            tracing.Trace("pvci sync: full={0} max={1} since={2}", fullSync, maxRecords,
                since.HasValue ? since.Value.ToString("o") : "(none)");

            var userCache = new Dictionary<string, Entity>(StringComparer.OrdinalIgnoreCase);
            var botNameCache = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            List<Entity> flowRuns = QueryFlowRuns(service, tracing);

            foreach (Entity transcript in QueryTranscripts(service, since, maxRecords))
            {
                Guid transcriptId = transcript.Id;
                try
                {
                    SyncResult r = SyncOne(service, tracing, transcript, userCache, botNameCache,
                                           includeTraces, reprocess, flowRuns, sourceEnvironment);
                    processed++;
                    turns += r.Turns;
                    if (r.Skipped) skipped++;
                    else if (r.Created) created++;
                    else updated++;
                    if (r.MultiUser) anomalies++;

                    if (!watermarkFrozen)
                        watermark = transcript.GetAttributeValue<DateTime>("createdon");
                }
                catch (Exception ex)
                {
                    // Freeze the watermark so this transcript is retried on the next run.
                    watermarkFrozen = true;
                    string msg = transcriptId.ToString().Substring(0, 8) + ": " + ex.Message;
                    errors.Add(msg);
                    tracing.Trace("FAILED {0}", msg);
                }
            }

            int users = UpsertIdentityMap(service, userCache);

            string status = errors.Count == 0 ? "success" : (processed > 0 ? "partial" : "failed");
            WriteSyncState(service, syncState, watermark, status, processed, errors);

            SetOutput(context, "TranscriptsProcessed", processed);
            SetOutput(context, "SessionsCreated", created);
            SetOutput(context, "SessionsUpdated", updated);
            SetOutput(context, "SessionsSkipped", skipped);
            SetOutput(context, "TurnsCreated", turns);
            SetOutput(context, "UsersResolved", users);
            SetOutput(context, "Anomalies", anomalies);
            SetOutput(context, "Status", status);
            SetOutput(context, "Watermark", watermark.HasValue ? watermark.Value.ToString("o") : string.Empty);
            SetOutput(context, "Errors", string.Join("\n", errors.ToArray()));
        }

        internal class SyncResult
        {
            public bool Created;
            public bool Skipped;
            public int Turns;
            public bool MultiUser;
        }

        internal class SourceEnvironment
        {
            public string TenantId;
            public string Id;
            public string Name;
            public string OrganizationName;
        }

        internal static SyncResult ImportCentralRow(
            IOrganizationService service,
            ITracingService tracing,
            Entity transcript,
            string tenantId,
            string environmentId,
            string environmentName,
            string organizationName,
            bool includeTraces,
            bool reprocess)
        {
            var source = new SourceEnvironment
            {
                TenantId = tenantId,
                Id = environmentId,
                Name = environmentName,
                OrganizationName = organizationName,
            };
            string compositeId = CompositeTranscriptId(tenantId, environmentId, transcript.Id.ToString());
            return new SyncConversationTranscripts().SyncOne(
                service,
                tracing,
                transcript,
                new Dictionary<string, Entity>(StringComparer.OrdinalIgnoreCase),
                new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase),
                includeTraces,
                reprocess,
                new List<Entity>(),
                source,
                compositeId);
        }

        internal static string CompositeTranscriptId(string tenantId, string environmentId, string transcriptId)
        {
            return string.Join(":", new[] { tenantId, environmentId, transcriptId }).ToLowerInvariant();
        }

        // --- query -----------------------------------------------------------

        private static IEnumerable<Entity> QueryTranscripts(IOrganizationService service, DateTime? since, int maxRecords)
        {
            var query = new QueryExpression("conversationtranscript")
            {
                ColumnSet = new ColumnSet("conversationtranscriptid", "metadata", "content", "createdon"),
                TopCount = maxRecords,
            };
            query.AddOrder("createdon", OrderType.Ascending);
            if (since.HasValue)
            {
                // ge, not gt: same-second rows at the boundary would otherwise be skipped permanently.
                query.Criteria.AddCondition("createdon", ConditionOperator.OnOrAfter, since.Value);
            }
            return service.RetrieveMultiple(query).Entities;
        }

        // --- per transcript --------------------------------------------------

        internal SyncResult SyncOne(
            IOrganizationService service,
            ITracingService tracing,
            Entity transcript,
            Dictionary<string, Entity> userCache,
            Dictionary<string, string> botNameCache,
            bool includeTraces,
            bool reprocess,
            List<Entity> flowRuns,
            SourceEnvironment sourceEnvironment,
            string transcriptIdOverride = null)
        {
            string transcriptId = transcriptIdOverride ?? transcript.Id.ToString();

            // Transcripts are immutable once Copilot Studio writes them, so an already-ingested
            // one is skipped entirely: no re-parse, no rewrite, no turn churn.
            Entity existing = FindByString(
                service,
                SessionEntity,
                "pvci_transcriptid",
                transcriptId,
                "pvci_transcriptsessionid",
                "pvci_tenantid",
                "pvci_environmentid",
                "pvci_environmentname",
                "pvci_datasource");
            if (existing != null && !reprocess)
            {
                BackfillEnvironment(service, existing, sourceEnvironment);
                tracing.Trace("skip (already ingested) {0}", transcriptId);
                return new SyncResult { Skipped = true };
            }

            string metadataRaw = transcript.GetAttributeValue<string>("metadata");
            string contentRaw = transcript.GetAttributeValue<string>("content");
            DateTime createdOn = transcript.GetAttributeValue<DateTime>("createdon");

            object metadata = Json.Parse(metadataRaw);
            object content = Json.Parse(contentRaw);
            List<object> activities = Json.Arr(Json.Get(content, "activities")) ?? new List<object>();
            string botSchemaName = Json.Str(metadata, "BotName");
            string botDisplayName = ResolveBotName(service, botSchemaName, botNameCache);

            var userIds = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var channels = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var stamps = new List<long>();
            var messages = new List<object>();
            var planEvents = new List<object>();
            int eventCount = 0;
            bool testMode = false;
            object sessionInfo = null;

            foreach (object a in activities)
            {
                object from = Json.Get(a, "from");
                string aad = Json.Str(from, "aadObjectId");
                if (!string.IsNullOrEmpty(aad)) userIds.Add(aad);

                string channel = Json.Str(a, "channelId");
                if (!string.IsNullOrEmpty(channel)) channels.Add(channel);

                long? ts = Json.Long(a, "timestamp");
                if (ts.HasValue) stamps.Add(ts.Value);

                string type = Json.Str(a, "type");
                string name = Json.Str(a, "name");

                if (string.Equals(type, "message", StringComparison.OrdinalIgnoreCase)
                    && !string.IsNullOrWhiteSpace(Json.Str(a, "text")))
                {
                    messages.Add(a);
                }
                if (string.Equals(type, "event", StringComparison.OrdinalIgnoreCase))
                {
                    eventCount++;
                    if (!string.IsNullOrEmpty(name) && name.StartsWith("DynamicPlan", StringComparison.OrdinalIgnoreCase))
                    {
                        var pe = new Dictionary<string, object>(StringComparer.Ordinal)
                        {
                            { "name", name },
                            { "at", Json.Get(a, "timestamp") },
                            { "value", Json.Get(a, "value") },
                        };
                        planEvents.Add(pe);
                    }
                }

                object channelData = Json.Get(a, "channelData");
                if (channelData != null && Json.Get(channelData, "testMode") != null)
                {
                    object tm = Json.Get(channelData, "testMode");
                    if (tm is bool && (bool)tm) testMode = true;
                }

                // Authoritative test signal: maker-portal test chat sets isDesignMode.
                if (string.Equals(Json.Str(a, "valueType"), "ConversationInfo", StringComparison.OrdinalIgnoreCase))
                {
                    object dm = Json.Get(Json.Get(a, "value"), "isDesignMode");
                    if (dm is bool && (bool)dm) testMode = true;
                }
                if (string.Equals(Json.Str(a, "valueType"), "SessionInfo", StringComparison.OrdinalIgnoreCase))
                {
                    sessionInfo = Json.Get(a, "value");
                }
            }

            DateTime? start = stamps.Count > 0 ? EpochUtc(stamps.Min()) : (DateTime?)null;
            DateTime? end = stamps.Count > 0 ? EpochUtc(stamps.Max()) : (DateTime?)null;
            TranscriptDiagnostics diagnostics = TranscriptAnalysis.ExtractDiagnostics(activities);

            var userMessages = messages.Where(m => IsUser(m)).ToList();
            var agentMessages = messages.Where(m => !IsUser(m)).ToList();

            string userAad = userIds.FirstOrDefault();
            string channelName = channels.FirstOrDefault();
            Entity systemUser = ResolveUser(service, userAad, userCache);

            var conversation = new List<object>();
            for (int i = 0; i < messages.Count; i++)
            {
                object m = messages[i];
                var turnObj = new Dictionary<string, object>(StringComparer.Ordinal)
                {
                    { "n", (double)(i + 1) },
                    { "speaker", IsUser(m) ? "user" : "agent" },
                    { "at", FormatIso(EpochUtc(Json.Long(m, "timestamp") ?? 0)) },
                    { "text", Json.Str(m, "text") },
                };
                conversation.Add(turnObj);
            }

            bool truncated;
            string activitiesJson = WriteLimited(activities, out truncated);
            bool truncatedConv;
            string conversationJson = WriteLimited(conversation, out truncatedConv);
            bool ignore;
            string planJson = WriteLimited(planEvents, out ignore);
            string metadataJson = WriteLimited(metadata, out ignore);

            List<long> latencies = ResponseLatencies(messages);
            List<object> toolCalls = ExtractToolCalls(activities);
            string toolsJson = WriteLimited(toolCalls, out ignore);
            List<object> knowledgeCalls = TranscriptAnalysis.ExtractKnowledgeCalls(activities);
            string knowledgeJson = WriteLimited(knowledgeCalls, out ignore);
            int knowledgeSources = 0, knowledgeFailures = 0;
            foreach (object knowledgeCall in knowledgeCalls)
            {
                List<object> citedSources = Json.Arr(Json.Get(knowledgeCall, "cited_sources"));
                if (citedSources != null) knowledgeSources += citedSources.Count;
                object failed = Json.Get(knowledgeCall, "failed");
                if (failed is bool && (bool)failed) knowledgeFailures++;
            }

            List<object> flowCorrelation = CorrelateFlowRuns(activities, flowRuns);
            string flowsJson = WriteLimited(flowCorrelation, out ignore);
            int matchedRuns = 0, failedRuns = 0;
            long maxRunMs = 0;
            foreach (object fc in flowCorrelation)
            {
                List<object> rs = Json.Arr(Json.Get(fc, "runs"));
                if (rs == null) continue;
                foreach (object run in rs)
                {
                    matchedRuns++;
                    string st = Json.Str(run, "status") ?? string.Empty;
                    if (st.Length > 0 && !st.Equals("Succeeded", StringComparison.OrdinalIgnoreCase)
                        && !st.Equals("Running", StringComparison.OrdinalIgnoreCase)) failedRuns++;
                    object d = Json.Get(run, "duration_ms");
                    if (d is double && (double)d > maxRunMs) maxRunMs = (long)(double)d;
                }
            }

            var toolDurations = new List<long>();
            int toolErrors = 0;
            foreach (object c in toolCalls)
            {
                object dur = Json.Get(c, "duration_ms");
                if (dur is double) toolDurations.Add((long)(double)dur);
                object failed = Json.Get(c, "failed");
                if (failed is bool && (bool)failed) toolErrors++;
            }

            string display = systemUser != null
                ? systemUser.GetAttributeValue<string>("fullname")
                : (string.IsNullOrEmpty(userAad) ? "unknown" : userAad.Substring(0, 8));

            var session = new Entity(SessionEntity);
            session["pvci_name"] = Trim(display + " · " + (channelName ?? "?") + " · " + FormatIso(start ?? createdOn), TextLimit);
            session["pvci_transcriptid"] = Trim(transcriptId, TextLimit);
            session["pvci_botid"] = Trim(Json.Str(metadata, "BotId"), TextLimit);
            session["pvci_botname"] = Trim(botDisplayName, TextLimit);
            session["pvci_topicid"] = Trim(diagnostics.TopicId, TextLimit);
            session["pvci_topicname"] = Trim(diagnostics.TopicName, TextLimit);
            session["pvci_tenantid"] = Trim(sourceEnvironment.TenantId ?? Json.Str(metadata, "AADTenantId"), TextLimit);
            session["pvci_environmentid"] = Trim(sourceEnvironment.Id, TextLimit);
            session["pvci_environmentname"] = Trim(sourceEnvironment.Name, TextLimit);
            session["pvci_useraadobjectid"] = Trim(userAad, TextLimit);
            session["pvci_channel"] = Trim(channelName, TextLimit);
            if (start.HasValue) session["pvci_startdatetimeutc"] = start.Value;
            if (end.HasValue) session["pvci_enddatetimeutc"] = end.Value;
            if (start.HasValue && end.HasValue)
                session["pvci_durationseconds"] = (int)(end.Value - start.Value).TotalSeconds;
            session["pvci_activitycount"] = activities.Count;
            session["pvci_messagecount"] = messages.Count;
            session["pvci_eventcount"] = eventCount;
            session["pvci_userturncount"] = userMessages.Count;
            session["pvci_agentturncount"] = agentMessages.Count;
            session["pvci_initialusermessage"] = userMessages.Count > 0 ? Json.Str(userMessages[0], "text") : null;
            session["pvci_lastagentmessage"] = agentMessages.Count > 0 ? Json.Str(agentMessages[agentMessages.Count - 1], "text") : null;
            session["pvci_istestmode"] = testMode;
            session["pvci_multiuseranomaly"] = userIds.Count > 1;
            if (latencies.Count > 0)
            {
                session["pvci_firstresponsems"] = (int)latencies[0];
                session["pvci_avgresponsems"] = (int)latencies.Average();
                session["pvci_maxresponsems"] = (int)latencies.Max();
            }
            session["pvci_toolcallcount"] = toolCalls.Count;
            session["pvci_toolerrorcount"] = toolErrors;
            if (toolDurations.Count > 0)
            {
                session["pvci_tooltotalms"] = (int)toolDurations.Sum();
                session["pvci_maxtoolms"] = (int)toolDurations.Max();
            }
            session["pvci_toolcallsjson"] = toolsJson;
            session["pvci_knowledgecallcount"] = knowledgeCalls.Count;
            session["pvci_knowledgesourcecount"] = knowledgeSources;
            session["pvci_knowledgefailurecount"] = knowledgeFailures;
            session["pvci_knowledgecallsjson"] = knowledgeJson;
            session["pvci_flowrunsjson"] = flowsJson;
            session["pvci_flowruncount"] = matchedRuns;
            session["pvci_flowrunfailurecount"] = failedRuns;
            if (maxRunMs > 0) session["pvci_flowrunmaxms"] = (int)maxRunMs;
            session["pvci_sessionoutcome"] = Trim(Json.Str(sessionInfo, "outcome"), TextLimit);
            string userErrorReason = TranscriptAnalysis.ErrorReason(
                diagnostics.PrimaryErrorCode,
                diagnostics.PrimaryErrorMessage);
            session["pvci_outcomereason"] = Trim(userErrorReason ?? Json.Str(sessionInfo, "outcomeReason"), TextLimit);
            session["pvci_usererrorcount"] = diagnostics.UserErrorCount;
            session["pvci_primaryerrorcode"] = Trim(diagnostics.PrimaryErrorCode, TextLimit);
            session["pvci_primaryerrormessage"] = Trim(diagnostics.PrimaryErrorMessage, MemoLimit);
            session["pvci_primaryerrortopic"] = Trim(diagnostics.PrimaryErrorTopic, TextLimit);
            session["pvci_errorcategory"] = Trim(diagnostics.ErrorCategory, TextLimit);
            object implied = Json.Get(sessionInfo, "impliedSuccess");
            if (implied is bool) session["pvci_isresolvedimplied"] = ((bool)implied) ? "true" : "false";
            int? sessionTurns = Json.Int(sessionInfo, "turnCount");
            if (sessionTurns.HasValue) session["pvci_turncount"] = sessionTurns.Value;
            session["pvci_payloadtruncated"] = truncated || truncatedConv;
            session["pvci_activitiesjson"] = activitiesJson;
            session["pvci_conversationjson"] = conversationJson;
            session["pvci_planeventsjson"] = planJson;
            session["pvci_metadatajson"] = metadataJson;
            session["pvci_transcriptcreatedon"] = createdOn;
            session["pvci_ingestedon"] = DateTime.UtcNow;
            session["pvci_datasource"] = BuildSourceStamp(
                sourceEnvironment,
                sourceEnvironment.TenantId ?? Json.Str(metadata, "AADTenantId"));
            session["pvci_correlationstatus"] = systemUser != null ? "exact" : (string.IsNullOrEmpty(userAad) ? "unmatched" : "heuristic");
            if (systemUser != null)
                session["pvci_userid"] = new EntityReference("systemuser", systemUser.Id);
            if (systemUser != null)
                session["pvci_userupn"] = Trim(systemUser.GetAttributeValue<string>("domainname"), TextLimit);
            if (systemUser != null)
                session["pvci_userdisplayname"] = Trim(systemUser.GetAttributeValue<string>("fullname"), TextLimit);

            Guid sessionId;
            bool wasCreated;
            var staleTurns = new List<Guid>();

            if (existing != null)
            {
                session.Id = existing.Id;
                sessionId = existing.Id;
                service.Update(session);
                wasCreated = false;
                staleTurns = FindTurnIds(service, transcriptId);
            }
            else
            {
                sessionId = service.Create(session);
                wasCreated = true;
            }

            EnsureFlowRunPlaceholders(service, flowCorrelation, transcriptId);

            int turnCount = 0;
            int idx = 0;
            long? lastUserMs = null;
            foreach (object a in activities)
            {
                string type = Json.Str(a, "type");
                string name = Json.Str(a, "name");
                if (!includeTraces && !TranscriptAnalysis.IsUserErrorTrace(a)
                    && ((type != null && NoiseTypes.Contains(type)) || (name != null && NoiseEvents.Contains(name))))
                    continue;

                object from = Json.Get(a, "from");
                int? role = Json.Int(from, "role");
                string speaker = role.HasValue && role.Value == 1 ? "user" : "agent";

                long? thisMs = Ms(a);
                int? latencyMs = null;
                if (string.Equals(type, "message", StringComparison.OrdinalIgnoreCase)
                    && !string.IsNullOrWhiteSpace(Json.Str(a, "text")))
                {
                    if (role.HasValue && role.Value == 1) lastUserMs = thisMs;
                    else if (lastUserMs.HasValue && thisMs.HasValue)
                    {
                        latencyMs = (int)(thisMs.Value - lastUserMs.Value);
                        lastUserMs = null; // only the first reply carries the latency
                    }
                }

                var turn = new Entity(TurnEntity);
                turn["pvci_name"] = Trim(idx.ToString("0000", CultureInfo.InvariantCulture) + " " + speaker + " " + (type ?? "?"), TextLimit);
                turn["pvci_transcriptid"] = Trim(transcriptId, TextLimit);
                turn["pvci_turnindex"] = idx;
                turn["pvci_activitytype"] = Trim(type, TextLimit);
                turn["pvci_speaker"] = speaker;
                if (role.HasValue) turn["pvci_role"] = role.Value;
                turn["pvci_aadobjectid"] = Trim(Json.Str(from, "aadObjectId"), TextLimit);
                turn["pvci_eventname"] = Trim(name ?? Json.Str(a, "valueType"), TextLimit);
                turn["pvci_channelid"] = Trim(Json.Str(a, "channelId"), TextLimit);
                long? ts = Json.Long(a, "timestamp");
                if (ts.HasValue) turn["pvci_timestamputc"] = EpochUtc(ts.Value);
                turn["pvci_turntext"] = Json.Str(a, "text");
                if (latencyMs.HasValue) turn["pvci_latencyms"] = latencyMs.Value;
                object val = Json.Get(a, "value");
                if (val != null)
                {
                    bool t2;
                    turn["pvci_valuejson"] = WriteLimited(val, out t2, 100000);
                }
                turn["pvci_sessionid"] = new EntityReference(SessionEntity, sessionId);

                service.Create(turn);
                turnCount++;
                idx++;
            }

            // Only after the replacements exist, so a failure never leaves the session empty.
            foreach (Guid staleId in staleTurns)
            {
                try { service.Delete(TurnEntity, staleId); }
                catch (Exception ex) { tracing.Trace("stale turn delete failed {0}: {1}", staleId, ex.Message); }
            }

            return new SyncResult { Created = wasCreated, Turns = turnCount, MultiUser = userIds.Count > 1 };
        }

        // --- helpers ---------------------------------------------------------

        private static void EnsureFlowRunPlaceholders(
            IOrganizationService service,
            List<object> flowCorrelation,
            string transcriptId)
        {
            foreach (object correlation in flowCorrelation)
            {
                List<object> runs = Json.Arr(Json.Get(correlation, "runs"));
                if (runs == null) continue;

                foreach (object run in runs)
                {
                    string runName = Json.Str(run, "run_name");
                    if (string.IsNullOrEmpty(runName)) continue;
                    if (FindByString(service, FlowRunDetailEntity, "pvci_runname", runName,
                                     "pvci_flowrundetailid") != null) continue;

                    var detail = new Entity(FlowRunDetailEntity);
                    detail["pvci_name"] = Trim("Pending · " + runName, TextLimit);
                    detail["pvci_runname"] = Trim(runName, TextLimit);
                    detail["pvci_workflowentityid"] = Trim(Json.Str(run, "workflow_id"), TextLimit);
                    detail["pvci_status"] = Trim(Json.Str(run, "status"), TextLimit);
                    detail["pvci_transcriptid"] = Trim(transcriptId, TextLimit);
                    service.Create(detail);
                }
            }
        }

        private static bool IsUser(object activity)
        {
            int? role = Json.Int(Json.Get(activity, "from"), "role");
            return role.HasValue && role.Value == 1;
        }

        private static long? Ms(object activity)
        {
            return Json.Long(activity, "timestampMs");
        }

        private static string TrimOrNull(string value)
        {
            return string.IsNullOrWhiteSpace(value) ? null : value.Trim();
        }

        /// <summary>User utterance -> first agent reply, in milliseconds.</summary>
        private static List<long> ResponseLatencies(List<object> messages)
        {
            var ordered = messages.Where(m => Ms(m).HasValue).OrderBy(m => Ms(m).Value).ToList();
            var result = new List<long>();
            for (int i = 0; i < ordered.Count; i++)
            {
                if (!IsUser(ordered[i])) continue;
                // Nothing is yielded if the user spoke again first, so unanswered turns score nothing.
                object reply = ordered.Skip(i + 1).TakeWhile(m => !IsUser(m)).FirstOrDefault();
                if (reply != null) result.Add(Ms(reply).Value - Ms(ordered[i]).Value);
            }
            return result;
        }

        /// <summary>
        /// Pairs DialogTracing entries into invocation spans. Each invoked action is traced on
        /// entry and again on completion, so alternating occurrences bracket one execution.
        /// </summary>
        private static List<object> ExtractToolCalls(List<object> activities)
        {
            var byAction = new Dictionary<string, List<KeyValuePair<long, object>>>(StringComparer.Ordinal);

            foreach (object a in activities)
            {
                if (!string.Equals(Json.Str(a, "name"), "DialogTracing", StringComparison.OrdinalIgnoreCase)) continue;
                long? ts = Ms(a);
                if (!ts.HasValue) continue;

                List<object> actions = Json.Arr(Json.Get(Json.Get(a, "value"), "actions"));
                if (actions == null) continue;

                foreach (object act in actions)
                {
                    string actionType = Json.Str(act, "actionType") ?? string.Empty;
                    if (!actionType.StartsWith("Invoke", StringComparison.OrdinalIgnoreCase)) continue;
                    string actionId = Json.Str(act, "actionId") ?? "?";
                    if (!byAction.ContainsKey(actionId)) byAction[actionId] = new List<KeyValuePair<long, object>>();
                    byAction[actionId].Add(new KeyValuePair<long, object>(ts.Value, act));
                }
            }

            var calls = new List<object>();
            foreach (var kv in byAction)
            {
                var occ = kv.Value.OrderBy(x => x.Key).ToList();
                for (int i = 0; i + 1 < occ.Count; i += 2)
                {
                    object endAct = occ[i + 1].Value;
                    string exception = Json.Str(endAct, "exception") ?? string.Empty;
                    calls.Add(new Dictionary<string, object>(StringComparer.Ordinal)
                    {
                        { "action_id", kv.Key },
                        { "action_type", Json.Str(endAct, "actionType") },
                        { "topic", LastSegment(Json.Str(endAct, "topicId")) },
                        { "started_utc", FormatIso(EpochUtc(occ[i].Key / 1000)) },
                        { "duration_ms", (double)(occ[i + 1].Key - occ[i].Key) },
                        { "failed", exception.Length > 0 },
                        { "exception", exception },
                        { "output", Json.Get(Json.Get(endAct, "variableState"), "dialogState") },
                    });
                }
                if (occ.Count % 2 == 1)
                {
                    object act = occ[occ.Count - 1].Value;
                    calls.Add(new Dictionary<string, object>(StringComparer.Ordinal)
                    {
                        { "action_id", kv.Key },
                        { "action_type", Json.Str(act, "actionType") },
                        { "topic", LastSegment(Json.Str(act, "topicId")) },
                        { "started_utc", FormatIso(EpochUtc(occ[occ.Count - 1].Key / 1000)) },
                        { "duration_ms", null },
                        { "failed", true },
                        { "exception", "no completion trace - call did not finish" },
                        { "output", null },
                    });
                }
            }
            return calls;
        }

        private static List<Entity> QueryFlowRuns(IOrganizationService service, ITracingService tracing)
        {
            var results = new List<Entity>();
            try
            {
                var query = new QueryExpression("flowrun")
                {
                    ColumnSet = new ColumnSet("flowrunid", "name", "status", "starttime", "endtime",
                                             "duration", "workflowid", "workflowname", "errorcode",
                                             "errormessage", "parentrunid", "callingproductrunid",
                                             "isprimary", "conversationid"),
                    PageInfo = new PagingInfo { Count = 500, PageNumber = 1 },
                };
                query.AddOrder("starttime", OrderType.Descending);

                while (true)
                {
                    EntityCollection page = service.RetrieveMultiple(query);
                    results.AddRange(page.Entities);
                    if (!page.MoreRecords || results.Count >= 2000) break;
                    query.PageInfo.PageNumber++;
                    query.PageInfo.PagingCookie = page.PagingCookie;
                }
            }
            catch (Exception ex)
            {
                // Flow run visibility depends on privileges; correlation is best-effort.
                tracing.Trace("flowrun query failed: {0}", ex.Message);
            }
            tracing.Trace("flow runs available: {0}", results.Count);
            return results;
        }

        private class FlowSpan
        {
            public string ActionId;
            public string Topic;
            public long StartMs;
            public long? EndMs;
            public string Exception = string.Empty;
            public string Source;
            public string Thought;
        }

        /// <summary>
        /// Windows in which a backend flow may have run. DialogTracing InvokeFlowAction is exact
        /// but only emitted in design/test mode, so production channels fall back to DynamicPlan
        /// step windows - the only signal those transcripts carry.
        /// </summary>
        private static List<FlowSpan> BuildFlowSpans(List<object> activities)
        {
            var byAction = new Dictionary<string, List<KeyValuePair<long, object>>>(StringComparer.Ordinal);
            foreach (object a in activities)
            {
                if (!string.Equals(Json.Str(a, "name"), "DialogTracing", StringComparison.OrdinalIgnoreCase)) continue;
                long? ts = Ms(a);
                if (!ts.HasValue) continue;
                List<object> actions = Json.Arr(Json.Get(Json.Get(a, "value"), "actions"));
                if (actions == null) continue;
                foreach (object act in actions)
                {
                    if (!string.Equals(Json.Str(act, "actionType"), "InvokeFlowAction", StringComparison.OrdinalIgnoreCase))
                        continue;
                    string id = Json.Str(act, "actionId") ?? "?";
                    if (!byAction.ContainsKey(id)) byAction[id] = new List<KeyValuePair<long, object>>();
                    byAction[id].Add(new KeyValuePair<long, object>(ts.Value, act));
                }
            }

            var spans = new List<FlowSpan>();
            foreach (var kv in byAction)
            {
                var occ = kv.Value.OrderBy(x => x.Key).ToList();
                for (int i = 0; i < occ.Count; i += 2)
                {
                    object endAct = (i + 1 < occ.Count) ? occ[i + 1].Value : occ[i].Value;
                    spans.Add(new FlowSpan
                    {
                        ActionId = kv.Key,
                        Topic = LastSegment(Json.Str(endAct, "topicId")),
                        StartMs = occ[i].Key,
                        EndMs = (i + 1 < occ.Count) ? occ[i + 1].Key : (long?)null,
                        Exception = (i + 1 < occ.Count)
                            ? (Json.Str(endAct, "exception") ?? string.Empty)
                            : "no completion trace - call did not finish",
                        Source = "flow_action",
                    });
                }
            }

            if (spans.Count > 0) return spans;
            return PlanStepSpans(activities);
        }

        private static List<FlowSpan> PlanStepSpans(List<object> activities)
        {
            var steps = new Dictionary<string, FlowSpan>(StringComparer.Ordinal);
            var ends = new Dictionary<string, long>(StringComparer.Ordinal);

            foreach (object a in activities)
            {
                string name = Json.Str(a, "name") ?? string.Empty;
                if (!name.StartsWith("DynamicPlanStep", StringComparison.OrdinalIgnoreCase)) continue;
                object value = Json.Get(a, "value");
                string stepId = Json.Str(value, "stepId");
                long? ts = Ms(a);
                if (string.IsNullOrEmpty(stepId) || !ts.HasValue) continue;

                if (name.Equals("DynamicPlanStepTriggered", StringComparison.OrdinalIgnoreCase))
                {
                    string taskDialogId = Json.Str(value, "taskDialogId");
                    if (!IsFlowCandidateTask(taskDialogId)) continue;
                    steps[stepId] = new FlowSpan
                    {
                        ActionId = stepId,
                        Topic = LastSegment(taskDialogId),
                        StartMs = ts.Value,
                        Source = "plan_step",
                        Thought = Json.Str(value, "thought"),
                    };
                }
                else if (name.Equals("DynamicPlanStepFinished", StringComparison.OrdinalIgnoreCase))
                {
                    ends[stepId] = ts.Value;
                }
            }

            var ordered = steps.Values.OrderBy(s => s.StartMs).ToList();
            for (int i = 0; i < ordered.Count; i++)
            {
                FlowSpan s = ordered[i];
                long end;
                if (ends.TryGetValue(s.ActionId, out end))
                {
                    s.EndMs = end;
                }
                else
                {
                    long capped = s.StartMs + PlanStepFallbackMs;
                    s.EndMs = (i + 1 < ordered.Count) ? Math.Min(ordered[i + 1].StartMs, capped) : capped;
                }
            }
            return ordered;
        }

        private static bool IsFlowCandidateTask(string taskDialogId)
        {
            if (string.IsNullOrWhiteSpace(taskDialogId)) return false;
            return taskDialogId.IndexOf("search", StringComparison.OrdinalIgnoreCase) < 0
                && taskDialogId.IndexOf("knowledge", StringComparison.OrdinalIgnoreCase) < 0;
        }

        private static List<object> CorrelateFlowRuns(List<object> activities, List<Entity> flowRuns)
        {
            var output = new List<object>();
            foreach (FlowSpan span in BuildFlowSpans(activities))
            {
                double lo = span.StartMs / 1000.0 - FlowRunToleranceSeconds;
                double hi = (span.EndMs ?? span.StartMs) / 1000.0 + FlowRunToleranceSeconds;

                var matches = new List<Dictionary<string, object>>();
                foreach (Entity run in flowRuns)
                {
                    if (!run.Contains("starttime")) continue;
                    DateTime st = run.GetAttributeValue<DateTime>("starttime").ToUniversalTime();
                    double epoch = (st - new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc)).TotalSeconds;
                    if (epoch < lo || epoch > hi) continue;

                    OptionSetValue isPrimary = run.GetAttributeValue<OptionSetValue>("isprimary");

                    matches.Add(new Dictionary<string, object>(StringComparer.Ordinal)
                    {
                        { "flow_run_id", run.Id.ToString() },
                        { "run_name", run.GetAttributeValue<string>("name") },
                        { "workflow_id", run.GetAttributeValue<string>("workflowid") },
                        { "status", run.GetAttributeValue<string>("status") },
                        { "started_utc", FormatIso(st) },
                        { "ended_utc", run.Contains("endtime") ? FormatIso(run.GetAttributeValue<DateTime>("endtime").ToUniversalTime()) : null },
                        { "duration_ms", run.Contains("duration") ? (double?)run.GetAttributeValue<long>("duration") : null },
                        { "error_code", run.GetAttributeValue<string>("errorcode") },
                        { "error_message", run.GetAttributeValue<string>("errormessage") },
                        { "parent_run_id", run.GetAttributeValue<string>("parentrunid") },
                        { "calling_product_run_id", run.GetAttributeValue<string>("callingproductrunid") },
                        { "is_primary", isPrimary != null ? (int?)isPrimary.Value : null },
                        { "workflow_name", run.GetAttributeValue<string>("workflowname") },
                        { "conversation_id", run.GetAttributeValue<string>("conversationid") },
                        { "offset_ms", (double)(epoch * 1000 - span.StartMs) },
                    });
                }

                var ranked = matches.OrderBy(m => Math.Abs(Convert.ToDouble(m["offset_ms"]))).ToList();
                for (int r = 0; r < ranked.Count; r++)
                {
                    ranked[r]["rank"] = (double)r;
                    ranked[r]["best"] = r == 0;
                }

                output.Add(new Dictionary<string, object>(StringComparer.Ordinal)
                {
                    { "action_id", span.ActionId },
                    { "topic", span.Topic },
                    { "source", span.Source },
                    { "thought", span.Thought },
                    { "started_utc", FormatIso(EpochUtc(span.StartMs / 1000)) },
                    { "span_ms", span.EndMs.HasValue ? (double?)(span.EndMs.Value - span.StartMs) : null },
                    { "exception", span.Exception ?? string.Empty },
                    { "confidence", ranked.Count == 0 ? "none" : (ranked.Count == 1 ? "high" : "multiple") },
                    { "runs", ranked.Cast<object>().ToList() },
                });
            }
            return output;
        }

        private static string LastSegment(string value)
        {
            if (string.IsNullOrEmpty(value)) return value;
            int i = value.LastIndexOf('.');
            return i >= 0 ? value.Substring(i + 1) : value;
        }

        private static DateTime EpochUtc(long seconds)
        {
            if (seconds > 10000000000L) seconds /= 1000; // milliseconds
            return new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc).AddSeconds(seconds);
        }

        private static string FormatIso(DateTime? dt)
        {
            return dt.HasValue ? dt.Value.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture) : null;
        }

        private static string Trim(string value, int max)
        {
            if (string.IsNullOrEmpty(value)) return value;
            return value.Length <= max ? value : value.Substring(0, max);
        }

        private static string WriteLimited(object value, out bool truncated, int limit = MemoLimit)
        {
            truncated = false;
            string text = Json.Write(value);
            if (text.Length <= limit) return text;
            truncated = true;
            return text.Substring(0, limit) + "\n/* TRUNCATED */";
        }

        private static Entity ResolveUser(IOrganizationService service, string aadObjectId, Dictionary<string, Entity> cache)
        {
            if (string.IsNullOrEmpty(aadObjectId)) return null;
            Entity cached;
            if (cache.TryGetValue(aadObjectId, out cached)) return cached;

            var query = new QueryExpression("systemuser")
            {
                ColumnSet = new ColumnSet("systemuserid", "fullname", "domainname"),
                TopCount = 1,
            };
            query.Criteria.AddCondition("azureactivedirectoryobjectid", ConditionOperator.Equal, aadObjectId);
            EntityCollection found = service.RetrieveMultiple(query);
            Entity user = found.Entities.Count > 0 ? found.Entities[0] : null;
            cache[aadObjectId] = user;
            return user;
        }

        private static string ResolveBotName(
            IOrganizationService service,
            string schemaName,
            Dictionary<string, string> cache)
        {
            if (string.IsNullOrEmpty(schemaName)) return schemaName;
            string cached;
            if (cache.TryGetValue(schemaName, out cached)) return cached;

            string displayName = schemaName;
            try
            {
                var query = new QueryExpression("bot")
                {
                    ColumnSet = new ColumnSet("name"),
                    TopCount = 1,
                };
                query.Criteria.AddCondition("schemaname", ConditionOperator.Equal, schemaName);
                query.Criteria.AddCondition("componentstate", ConditionOperator.Equal, 0);
                EntityCollection found = service.RetrieveMultiple(query);
                if (found.Entities.Count > 0)
                    displayName = found.Entities[0].GetAttributeValue<string>("name") ?? schemaName;
            }
            catch (FaultException<OrganizationServiceFault>)
            {
                // Bot metadata is optional enrichment; preserve transcript ingestion on access errors.
            }
            cache[schemaName] = displayName;
            return displayName;
        }

        private static SourceEnvironment ResolveSourceEnvironment(
            IOrganizationService service,
            IPluginExecutionContext context)
        {
            var context6 = context as IPluginExecutionContext6;
            if (context6 == null || string.IsNullOrWhiteSpace(context6.EnvironmentId))
                throw new InvalidPluginExecutionException(
                    "The plugin execution context did not provide a Power Platform environment ID.");

            string friendlyName = null;
            string organizationName = context.OrganizationName;
            try
            {
                Entity organization = service.Retrieve(
                    "organization",
                    context.OrganizationId,
                    new ColumnSet("friendlyname", "name"));
                friendlyName = organization.GetAttributeValue<string>("friendlyname");
                organizationName = organization.GetAttributeValue<string>("name") ?? organizationName;
            }
            catch (FaultException<OrganizationServiceFault>)
            {
                // Friendly-name enrichment is optional; environment ID remains authoritative.
            }
            string inventoryName = ResolveInventoryEnvironmentName(service, context6.EnvironmentId);
            return new SourceEnvironment
            {
                Id = context6.EnvironmentId,
                Name = inventoryName ?? friendlyName,
                OrganizationName = organizationName,
            };
        }

        private static string ResolveInventoryEnvironmentName(IOrganizationService service, string environmentId)
        {
            try
            {
                var query = new QueryExpression("pvci_environmentinventory")
                {
                    ColumnSet = new ColumnSet("pvci_displayname"),
                    TopCount = 1,
                };
                query.Criteria.AddCondition("pvci_environmentid", ConditionOperator.Equal, environmentId);
                EntityCollection rows = service.RetrieveMultiple(query);
                return rows.Entities.Count > 0
                    ? TrimOrNull(rows.Entities[0].GetAttributeValue<string>("pvci_displayname"))
                    : null;
            }
            catch (FaultException<OrganizationServiceFault>)
            {
                return null;
            }
        }

        private static string BuildSourceStamp(SourceEnvironment source, string tenantId)
        {
            var parts = new List<string> { "plugin_v9.x_conversationtranscripts" };
            if (!string.IsNullOrWhiteSpace(tenantId)) parts.Add("tenant:" + StampValue(tenantId));
            if (!string.IsNullOrWhiteSpace(source.Id)) parts.Add("env:" + StampValue(source.Id));
            if (!string.IsNullOrWhiteSpace(source.Name)) parts.Add("envName:" + StampValue(source.Name));
            if (!string.IsNullOrWhiteSpace(source.OrganizationName)) parts.Add("org:" + StampValue(source.OrganizationName));
            return string.Join("|", parts.ToArray());
        }

        private static string StampValue(string value)
        {
            return value.Replace("|", "/").Trim();
        }

        private static void BackfillEnvironment(
            IOrganizationService service,
            Entity existing,
            SourceEnvironment source)
        {
            string stamp = BuildSourceStamp(source, existing.GetAttributeValue<string>("pvci_tenantid"));
            bool changed = existing.GetAttributeValue<string>("pvci_environmentid") != source.Id
                || existing.GetAttributeValue<string>("pvci_environmentname") != source.Name
                || string.IsNullOrWhiteSpace(existing.GetAttributeValue<string>("pvci_datasource"));
            if (!changed) return;

            var update = new Entity(SessionEntity, existing.Id);
            update["pvci_environmentid"] = Trim(source.Id, TextLimit);
            update["pvci_environmentname"] = Trim(source.Name, TextLimit);
            if (string.IsNullOrWhiteSpace(existing.GetAttributeValue<string>("pvci_datasource")))
                update["pvci_datasource"] = stamp;
            service.Update(update);
        }

        private static Entity FindByString(
            IOrganizationService service,
            string entity,
            string field,
            string value,
            string idField,
            params string[] additionalColumns)
        {
            var columns = new List<string> { idField };
            columns.AddRange(additionalColumns);
            var query = new QueryExpression(entity) { ColumnSet = new ColumnSet(columns.ToArray()), TopCount = 1 };
            query.Criteria.AddCondition(field, ConditionOperator.Equal, value);
            EntityCollection result = service.RetrieveMultiple(query);
            return result.Entities.Count > 0 ? result.Entities[0] : null;
        }

        private static List<Guid> FindTurnIds(IOrganizationService service, string transcriptId)
        {
            var ids = new List<Guid>();
            var query = new QueryExpression(TurnEntity)
            {
                ColumnSet = new ColumnSet("pvci_transcriptturnid"),
                PageInfo = new PagingInfo { Count = 500, PageNumber = 1 },
            };
            query.Criteria.AddCondition("pvci_transcriptid", ConditionOperator.Equal, transcriptId);

            while (true)
            {
                EntityCollection page = service.RetrieveMultiple(query);
                foreach (Entity e in page.Entities) ids.Add(e.Id);
                if (!page.MoreRecords) break;
                query.PageInfo.PageNumber++;
                query.PageInfo.PagingCookie = page.PagingCookie;
            }
            return ids;
        }

        private static int UpsertIdentityMap(IOrganizationService service, Dictionary<string, Entity> userCache)
        {
            int count = 0;
            foreach (var kv in userCache)
            {
                string aad = kv.Key;
                Entity user = kv.Value;
                if (string.IsNullOrEmpty(aad)) continue;

                var record = new Entity(IdentityEntity);
                record["pvci_name"] = Trim(user != null ? user.GetAttributeValue<string>("fullname") : aad, TextLimit);
                record["pvci_aadobjectid"] = Trim(aad, TextLimit);
                record["pvci_userprincipalname"] = user != null ? Trim(user.GetAttributeValue<string>("domainname"), TextLimit) : null;
                record["pvci_displayname"] = user != null ? Trim(user.GetAttributeValue<string>("fullname"), TextLimit) : null;
                record["pvci_systemuserid"] = user != null ? user.Id.ToString() : null;
                record["pvci_correlationsource"] = "conversationtranscript.from.aadObjectId";
                record["pvci_correlationconfidence"] = user != null ? "exact" : "unresolved";
                record["pvci_lastseenon"] = DateTime.UtcNow;

                Entity existing = FindByString(service, IdentityEntity, "pvci_aadobjectid", aad, "pvci_transcriptidentitymapid");
                if (existing != null)
                {
                    record.Id = existing.Id;
                    service.Update(record);
                }
                else
                {
                    service.Create(record);
                }
                count++;
            }
            return count;
        }

        private static Entity GetSyncState(IOrganizationService service)
        {
            var query = new QueryExpression(SyncStateEntity)
            {
                ColumnSet = new ColumnSet("pvci_syncstateid", "pvci_lastsyncedcreatedon"),
                TopCount = 1,
            };
            query.Criteria.AddCondition("pvci_name", ConditionOperator.Equal, SyncStateRow);
            EntityCollection result = service.RetrieveMultiple(query);
            return result.Entities.Count > 0 ? result.Entities[0] : null;
        }

        private static void WriteSyncState(
            IOrganizationService service, Entity existing, DateTime? watermark,
            string status, int processed, List<string> errors)
        {
            var state = new Entity(SyncStateEntity);
            state["pvci_name"] = SyncStateRow;
            state["pvci_lastrunon"] = DateTime.UtcNow;
            state["pvci_lastrunstatus"] = status;
            state["pvci_recordsprocessed"] = processed;
            state["pvci_lasterror"] = errors.Count > 0
                ? Trim(string.Join("\n", errors.ToArray()), 100000)
                : string.Empty;
            if (watermark.HasValue) state["pvci_lastsyncedcreatedon"] = watermark.Value;

            if (existing != null)
            {
                state.Id = existing.Id;
                service.Update(state);
            }
            else
            {
                service.Create(state);
            }
        }

        private static T GetInput<T>(IPluginExecutionContext context, string name, T fallback)
        {
            object value;
            if (context.InputParameters.TryGetValue(name, out value) && value is T) return (T)value;
            return fallback;
        }

        private static void SetOutput(IPluginExecutionContext context, string name, object value)
        {
            context.OutputParameters[name] = value ?? string.Empty;
        }
    }
}
