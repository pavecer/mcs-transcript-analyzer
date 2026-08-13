using System;
using System.Collections.Generic;
using System.Globalization;
using Microsoft.Xrm.Sdk;
using Microsoft.Xrm.Sdk.Query;

namespace PvciTranscripts
{
    public class ImportCentralTranscriptBatch : IPlugin
    {
        internal const int MaxBatchSize = 25;
        private const string EnvironmentEntity = "pvci_environmentinventory";

        public void Execute(IServiceProvider serviceProvider)
        {
            var context = (IPluginExecutionContext)serviceProvider.GetService(typeof(IPluginExecutionContext));
            var tracing = (ITracingService)serviceProvider.GetService(typeof(ITracingService));
            var factory = (IOrganizationServiceFactory)serviceProvider.GetService(typeof(IOrganizationServiceFactory));
            IOrganizationService service = factory.CreateOrganizationService(context.UserId);

            string payloadJson = GetInput<string>(context, "PayloadJson", null);
            string tenantId = Required(GetInput<string>(context, "SourceTenantId", null), "SourceTenantId");
            string environmentId = Required(GetInput<string>(context, "SourceEnvironmentId", null), "SourceEnvironmentId");
            string environmentName = Required(GetInput<string>(context, "SourceEnvironmentName", null), "SourceEnvironmentName");
            string dataverseUrl = Required(GetInput<string>(context, "SourceDataverseUrl", null), "SourceDataverseUrl");
            bool includeTraces = GetInput(context, "IncludeTraces", false);
            bool reprocess = GetInput(context, "Reprocess", false);
            bool dryRun = GetInput(context, "DryRun", false);

            object root = Json.Parse(Required(payloadJson, "PayloadJson"));
            List<object> rows = Json.Arr(Json.Get(root, "value")) ?? Json.Arr(root);
            if (rows == null)
                throw new InvalidPluginExecutionException("PayloadJson must be a Dataverse List rows response or JSON array.");
            if (rows.Count > MaxBatchSize)
                throw new InvalidPluginExecutionException("Central transcript batches are limited to 25 rows.");

            int created = 0, updated = 0, skipped = 0, turns = 0;
            var errors = new List<string>();
            DateTime? watermark = null;
            bool watermarkFrozen = false;

            foreach (object row in rows)
            {
                string sourceId = Json.Str(row, "conversationtranscriptid");
                try
                {
                    Guid transcriptId;
                    if (!Guid.TryParse(sourceId, out transcriptId))
                        throw new InvalidPluginExecutionException("A source row has no valid conversationtranscriptid.");
                    DateTime createdOn;
                    if (!DateTime.TryParse(
                        Json.Str(row, "createdon"),
                        CultureInfo.InvariantCulture,
                        DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal,
                        out createdOn))
                        throw new InvalidPluginExecutionException("A source row has no valid createdon value.");

                    if (!dryRun)
                    {
                        var transcript = new Entity("conversationtranscript", transcriptId);
                        transcript["metadata"] = Json.Str(row, "metadata");
                        transcript["content"] = Json.Str(row, "content");
                        transcript["createdon"] = createdOn;
                        SyncConversationTranscripts.SyncResult result = SyncConversationTranscripts.ImportCentralRow(
                            service,
                            tracing,
                            transcript,
                            tenantId,
                            environmentId,
                            environmentName,
                            new Uri(dataverseUrl).Host,
                            includeTraces,
                            reprocess);
                        if (result.Skipped) skipped++;
                        else if (result.Created) created++;
                        else updated++;
                        turns += result.Turns;
                    }

                    if (!watermarkFrozen && (!watermark.HasValue || createdOn > watermark.Value))
                        watermark = createdOn;
                }
                catch (Exception exception)
                {
                    watermarkFrozen = true;
                    errors.Add((sourceId ?? "unknown") + ": " + exception.Message);
                }
            }

            string status = errors.Count == 0 ? "success" : (created + updated + skipped > 0 ? "partial" : "failed");
            if (!dryRun)
                UpdateEnvironmentHealth(service, environmentId, status, watermark, rows.Count, errors);

            SetOutput(context, "Created", created);
            SetOutput(context, "Updated", updated);
            SetOutput(context, "Skipped", skipped);
            SetOutput(context, "TurnsCreated", turns);
            SetOutput(context, "Status", dryRun ? "validated" : status);
            SetOutput(context, "Watermark", watermark.HasValue ? watermark.Value.ToString("o") : string.Empty);
            SetOutput(context, "Errors", string.Join("\n", errors.ToArray()));
        }

        internal static string CompositeTranscriptId(string tenantId, string environmentId, string transcriptId)
        {
            return SyncConversationTranscripts.CompositeTranscriptId(tenantId, environmentId, transcriptId);
        }

        private static void UpdateEnvironmentHealth(
            IOrganizationService service,
            string environmentId,
            string status,
            DateTime? watermark,
            int rowCount,
            List<string> errors)
        {
            var query = new QueryExpression(EnvironmentEntity)
            {
                ColumnSet = new ColumnSet("pvci_environmentinventoryid"),
                TopCount = 1,
            };
            query.Criteria.AddCondition("pvci_environmentid", ConditionOperator.Equal, environmentId);
            EntityCollection found = service.RetrieveMultiple(query);
            if (found.Entities.Count == 0) return;

            var update = new Entity(EnvironmentEntity, found.Entities[0].Id);
            update["pvci_transcriptlastcollectionstatus"] = status;
            update["pvci_transcriptlastcollectionerror"] = string.Join("\n", errors.ToArray());
            update["pvci_transcriptlastbatchcount"] = rowCount;
            if (watermark.HasValue) update["pvci_transcriptlastcollectedon"] = watermark.Value;
            service.Update(update);
        }

        private static string Required(string value, string name)
        {
            if (string.IsNullOrWhiteSpace(value))
                throw new InvalidPluginExecutionException(name + " is required.");
            return value;
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