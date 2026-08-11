using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Security.Cryptography;
using System.ServiceModel;
using System.Text;
using Microsoft.Xrm.Sdk;
using Microsoft.Xrm.Sdk.Query;

namespace PvciTranscripts
{
    /// <summary>
    /// Custom API: pvci_ImportCreditUsageBatch.
    /// Validates and idempotently imports normalized Copilot credit reporting facts.
    /// </summary>
    public class ImportCreditUsageBatch : IPlugin
    {
        private const string AgentEntity = "pvci_agentinventory";
        private const string UsageEntity = "pvci_creditusage";
        private const string UserUsageEntity = "pvci_credituserusage";
        private const string PrivacySettingEntity = "pvci_creditprivacysetting";
        private const string CapacityEntity = "pvci_creditcapacitysnapshot";
        private const string SyncRunEntity = "pvci_creditsyncrun";
        private const int PayloadLimit = 900000;
        private const int TextLimit = 1000;
        private const int MemoLimit = 900000;
        private const int RecordLimit = 2000;

        public void Execute(IServiceProvider serviceProvider)
        {
            var context = (IPluginExecutionContext)serviceProvider.GetService(typeof(IPluginExecutionContext));
            var tracing = (ITracingService)serviceProvider.GetService(typeof(ITracingService));
            var factory = (IOrganizationServiceFactory)serviceProvider.GetService(typeof(IOrganizationServiceFactory));
            IOrganizationService service = factory.CreateOrganizationService(context.UserId);

            string payloadJson = GetInput<string>(context, "PayloadJson", null);
            string schemaVersion = GetInput(context, "SourceSchemaVersion", "1");
            bool dryRun = GetInput(context, "DryRun", false);
            if (string.IsNullOrWhiteSpace(payloadJson))
                throw new InvalidPluginExecutionException("PayloadJson is required.");
            if (payloadJson.Length > PayloadLimit)
                throw new InvalidPluginExecutionException("PayloadJson exceeds the 900,000 character limit.");

            object parsed = Json.Parse(payloadJson);
            Dictionary<string, object> root = Json.Obj(parsed);
            if (root == null) throw new InvalidPluginExecutionException("PayloadJson must contain a JSON object.");

            string tenantId = Json.Str(root, "tenantId");
            ValidateTenant(service, context.OrganizationId, tenantId);

            var errors = new List<string>();
            var result = new ImportResult();
            var agentIds = new Dictionary<string, Guid>(StringComparer.OrdinalIgnoreCase);

            var agents = Json.Arr(Json.Get(root, "agents")) ?? new List<object>();
            var usage = Json.Arr(Json.Get(root, "usage")) ?? new List<object>();
            var userUsage = Json.Arr(Json.Get(root, "userUsage")) ?? new List<object>();
            var capacity = Json.Arr(Json.Get(root, "capacity")) ?? new List<object>();
            NormalizePpac(root, tenantId, agents, usage, userUsage, capacity);

            ImportAgents(service, agents, tenantId, dryRun, agentIds, result, errors);
            ImportUsage(service, usage, tenantId, schemaVersion, dryRun, agentIds, result, errors);
            ImportUserUsage(service, userUsage, tenantId, schemaVersion, dryRun, result, errors);
            ImportCapacity(service, capacity, tenantId, dryRun, result, errors);

            object syncRun = Json.Get(root, "syncRun");
            if (syncRun != null && !dryRun)
                UpsertSyncRun(service, syncRun, schemaVersion, result, errors);

            string status = errors.Count == 0 ? "success" : (result.Created + result.Updated > 0 ? "partial" : "failed");
            tracing.Trace("credit import: created={0} updated={1} rejected={2} dryRun={3}",
                result.Created, result.Updated, result.Rejected, dryRun);
            SetOutput(context, "Created", result.Created);
            SetOutput(context, "Updated", result.Updated);
            SetOutput(context, "Skipped", result.Skipped);
            SetOutput(context, "Rejected", result.Rejected);
            SetOutput(context, "Status", status);
            SetOutput(context, "Errors", Trim(string.Join("\n", errors.ToArray()), 100000));
        }

        private sealed class ImportResult
        {
            public int Created;
            public int Updated;
            public int Skipped = 0;
            public int Rejected;
        }

        private static void NormalizePpac(
            Dictionary<string, object> root,
            string tenantId,
            List<object> agents,
            List<object> usage,
            List<object> userUsage,
            List<object> capacity)
        {
            var resourceRows = new List<object>();
            CollectByProperty(Json.Get(root, "ppacResourcePages"), "resources", resourceRows);
            CollectByProperty(Json.Get(root, "ppacResources"), "resources", resourceRows);

            var capacityRows = new List<object>();
            CollectByProperty(Json.Get(root, "ppacCapacity"), "value", capacityRows);
            var userRows = new List<object>();
            CollectByProperty(Json.Get(root, "ppacUsers"), "users", userRows);
            if (resourceRows.Count == 0 && capacityRows.Count == 0 && userRows.Count == 0) return;

            string importedOn = DateTime.UtcNow.ToString("o", CultureInfo.InvariantCulture);
            var knownAgents = new HashSet<string>(
                agents.Select(item => Json.Str(item, "sourceKey")).Where(value => !string.IsNullOrWhiteSpace(value)),
                StringComparer.OrdinalIgnoreCase);

            foreach (object row in resourceRows)
            {
                string environmentId = Json.Str(row, "environmentId") ?? string.Empty;
                string resourceId = Json.Str(row, "resourceId") ?? string.Empty;
                object metadata = Json.Get(row, "metadata");
                string displayName = Json.Str(metadata, "ResourceName") ?? resourceId;
                if (string.IsNullOrWhiteSpace(displayName)) displayName = "Unknown resource";
                string agentSourceKey = StableKey(tenantId, environmentId, resourceId);
                string kind = IsGuid(resourceId) ? "agent_or_flow" : "service_or_group";

                if (knownAgents.Add(agentSourceKey))
                {
                    agents.Add(new Dictionary<string, object>
                    {
                        { "sourceKey", agentSourceKey },
                        { "tenantId", tenantId },
                        { "environmentId", environmentId },
                        { "resourceId", resourceId },
                        { "botId", IsGuid(resourceId) ? resourceId : null },
                        { "name", displayName },
                        { "displayName", displayName },
                        { "resourceType", kind },
                        { "harness", "unknown" },
                        { "classificationSource", "ppac_resource_aggregate" },
                        { "classificationConfidence", "unresolved" },
                        { "inventorySource", "PPAC MCSMessages resources" },
                        { "lastSyncedOn", importedOn },
                        { "evidence", new Dictionary<string, object>
                            {
                                { "users", Json.Get(metadata, "Users") },
                                { "asOfDate", Json.Get(row, "asOfDate") },
                            }
                        },
                    });
                }

                string usageDate = Json.Str(row, "asOfDate");
                string usageKey = StableKey(tenantId, environmentId, resourceId, usageDate,
                    "MCSMessages", "PPAC resource aggregate");
                usage.Add(new Dictionary<string, object>
                {
                    { "sourceKey", usageKey },
                    { "agentSourceKey", agentSourceKey },
                    { "tenantId", tenantId },
                    { "environmentId", environmentId },
                    { "resourceId", resourceId },
                    { "name", displayName + " - " + DatePart(usageDate) },
                    { "agentName", displayName },
                    { "usageDate", usageDate },
                    { "entitlementId", "MCSMessages" },
                    { "sourceUnit", Json.Get(row, "unit") ?? "Messages" },
                    { "billedCredits", Json.Get(row, "consumed") ?? 0 },
                    { "nonBilledCredits", Json.Get(metadata, "NonBillableQuantity") ?? 0 },
                    { "featureName", "PPAC resource aggregate" },
                    { "users", Json.Get(metadata, "Users") },
                    { "resourceType", kind },
                    { "harness", "unknown" },
                    { "resolutionStatus", "resource_id_only" },
                    { "sourceApi", "/v2.0/tenants/{tenantId}/entitlements/MCSMessages/resources" },
                    { "sourceSchemaVersion", "ppac-v2-resource-aggregate-v1" },
                    { "raw", row },
                    { "importedOn", importedOn },
                });
            }

            foreach (object row in capacityRows)
            {
                object entitlement = Json.Get(row, "entitlement");
                object values = Json.Get(entitlement, "capacity");
                object payGo = Json.Get(entitlement, "payGo");
                object consumed = Json.Get(values, "consumed");
                object allocated = Json.Get(values, "allocated");
                string environmentId = Json.Str(row, "environmentId") ?? string.Empty;
                string environmentName = Json.Str(row, "environmentName") ?? environmentId;
                string asOfDate = Json.Str(consumed, "lastUpdatedOn") ?? importedOn;
                object tenantPool = FindRule(Json.Arr(Json.Get(values, "enforcementRules")), "TenantPool");
                object alert = FindRule(Json.Arr(Json.Get(values, "enforcementRules")), "Alert");

                capacity.Add(new Dictionary<string, object>
                {
                    { "sourceKey", StableKey(tenantId, environmentId, "MCSMessages", asOfDate) },
                    { "tenantId", tenantId },
                    { "environmentId", environmentId },
                    { "environmentName", environmentName },
                    { "name", environmentName + " - " + DatePart(asOfDate) },
                    { "entitlementId", "MCSMessages" },
                    { "asOfDate", asOfDate },
                    { "entitled", Json.Get(allocated, "value") ?? 0 },
                    { "allocated", Json.Get(allocated, "value") ?? 0 },
                    { "autoAllocated", Json.Get(allocated, "autoAllocated") ?? 0 },
                    { "consumed", Json.Get(consumed, "value") ?? 0 },
                    { "available", Json.Get(values, "availableQuantity") ?? 0 },
                    { "payGoEntitled", Json.Get(Json.Get(payGo, "entitled"), "value") ?? 0 },
                    { "payGoConsumed", Json.Get(Json.Get(payGo, "consumed"), "value") ?? 0 },
                    { "status", Json.Str(values, "status") },
                    { "drawFromTenantPool", Json.Get(tenantPool, "enabled") ?? false },
                    { "alertEnabled", Json.Get(alert, "enabled") ?? false },
                    { "alertThreshold", Json.Get(Json.Get(alert, "ruleData"), "value") ?? 0 },
                    { "sourceApi", "/v2.0/tenants/{tenantId}/environments/entitlementConsumptions/MCSMessages" },
                    { "raw", row },
                    { "capturedOn", importedOn },
                });
            }

            foreach (object row in userRows)
            {
                string userId = Json.Str(row, "userId") ?? string.Empty;
                string usageDate = Json.Str(row, "asOfDate");
                object metadata = Json.Get(row, "metadata");
                userUsage.Add(new Dictionary<string, object>
                {
                    { "sourceKey", StableKey(tenantId, userId, usageDate, "MCSMessages", "PPAC user aggregate") },
                    { "tenantId", tenantId },
                    { "userId", userId },
                    { "name", userId },
                    { "usageDate", usageDate },
                    { "entitlementId", "MCSMessages" },
                    { "sourceUnit", Json.Get(row, "unit") ?? "Messages" },
                    { "billedCredits", Json.Get(row, "consumed") ?? 0 },
                    { "nonBilledCredits", Json.Get(metadata, "NonBillableQuantity") ?? 0 },
                    { "resources", Json.Get(metadata, "Resources") },
                    { "sourceApi", "/v2.0/tenants/{tenantId}/entitlements/MCSMessages/users" },
                    { "sourceSchemaVersion", "ppac-v2-user-aggregate-v1" },
                    { "importedOn", importedOn },
                });
            }

            var syncRun = Json.Obj(Json.Get(root, "syncRun"));
            if (syncRun != null && Json.Get(syncRun, "sourceCount") == null)
                syncRun["sourceCount"] = resourceRows.Count + capacityRows.Count + userRows.Count;
        }

        private static void CollectByProperty(object node, string property, List<object> rows)
        {
            var list = Json.Arr(node);
            if (list != null)
            {
                foreach (object item in list) CollectByProperty(item, property, rows);
                return;
            }
            var obj = Json.Obj(node);
            if (obj == null) return;
            var matches = Json.Arr(Json.Get(obj, property));
            if (matches != null)
            {
                rows.AddRange(matches);
                return;
            }
            object value = Json.Get(obj, "value");
            if (value != null) CollectByProperty(value, property, rows);
        }

        private static object FindRule(List<object> rules, string ruleType)
        {
            return rules == null ? null : rules.FirstOrDefault(rule => Json.Str(rule, "ruleType") == ruleType);
        }

        private static bool IsGuid(string value)
        {
            Guid parsed;
            return Guid.TryParse(value, out parsed);
        }

        private static string DatePart(string value)
        {
            if (string.IsNullOrEmpty(value)) return "unknown date";
            return value.Length <= 10 ? value : value.Substring(0, 10);
        }

        private static string StableKey(params object[] parts)
        {
            string normalized = string.Join("|", parts.Select(part => part == null ? string.Empty : part.ToString().Trim()));
            using (SHA256 sha = SHA256.Create())
            {
                byte[] hash = sha.ComputeHash(Encoding.UTF8.GetBytes(normalized));
                return string.Concat(hash.Select(value => value.ToString("x2", CultureInfo.InvariantCulture)));
            }
        }

        private static void ImportAgents(
            IOrganizationService service,
            List<object> records,
            string tenantId,
            bool dryRun,
            Dictionary<string, Guid> agentIds,
            ImportResult result,
            List<string> errors)
        {
            records = records ?? new List<object>();
            ValidateRecordCount(records, "agents");
            foreach (object item in records)
            {
                try
                {
                    string sourceKey = Required(item, "sourceKey");
                    Entity existing = FindByString(service, AgentEntity, "pvci_sourcekey", sourceKey,
                        "pvci_agentinventoryid");
                    var record = new Entity(AgentEntity);
                    SetString(record, "pvci_name", Json.Str(item, "name") ?? Json.Str(item, "displayName") ?? sourceKey, 200);
                    SetString(record, "pvci_sourcekey", sourceKey, 200);
                    SetString(record, "pvci_tenantid", Json.Str(item, "tenantId") ?? tenantId);
                    SetString(record, "pvci_environmentid", Json.Str(item, "environmentId"));
                    SetString(record, "pvci_environmentname", Json.Str(item, "environmentName"));
                    SetString(record, "pvci_environmenturl", Json.Str(item, "environmentUrl"));
                    SetString(record, "pvci_resourceid", Json.Str(item, "resourceId"));
                    SetString(record, "pvci_botid", Json.Str(item, "botId"));
                    SetString(record, "pvci_displayname", Json.Str(item, "displayName"));
                    SetString(record, "pvci_schemaname", Json.Str(item, "schemaName"));
                    SetString(record, "pvci_resourcetype", Json.Str(item, "resourceType"));
                    SetString(record, "pvci_harness", Json.Str(item, "harness") ?? "unknown");
                    SetString(record, "pvci_classificationsource", Json.Str(item, "classificationSource"));
                    SetString(record, "pvci_classificationconfidence", Json.Str(item, "classificationConfidence"));
                    SetString(record, "pvci_orchestrationtype", Json.Str(item, "orchestrationType"));
                    SetString(record, "pvci_model", Json.Str(item, "model"));
                    SetString(record, "pvci_authoringorigin", Json.Str(item, "authoringOrigin"));
                    SetBoolean(record, "pvci_published", Json.Get(item, "published"));
                    SetString(record, "pvci_inventorysource", Json.Str(item, "inventorySource"));
                    SetMemo(record, "pvci_evidencejson", Json.Get(item, "evidence"));
                    SetDate(record, "pvci_lastsyncedon", Json.Get(item, "lastSyncedOn"), DateTime.UtcNow);
                    Guid id = Upsert(service, existing, record, dryRun, result);
                    if (id != Guid.Empty) agentIds[sourceKey] = id;
                }
                catch (Exception ex)
                {
                    Reject(result, errors, "agent", item, ex);
                }
            }
        }

        private static void ImportUsage(
            IOrganizationService service,
            List<object> records,
            string tenantId,
            string schemaVersion,
            bool dryRun,
            Dictionary<string, Guid> agentIds,
            ImportResult result,
            List<string> errors)
        {
            records = records ?? new List<object>();
            ValidateRecordCount(records, "usage");
            foreach (object item in records)
            {
                try
                {
                    string sourceKey = Required(item, "sourceKey");
                    Entity existing = FindByString(service, UsageEntity, "pvci_sourcekey", sourceKey,
                        "pvci_creditusageid");
                    var record = new Entity(UsageEntity);
                    SetString(record, "pvci_name", Json.Str(item, "name") ?? Json.Str(item, "agentName") ?? sourceKey, 200);
                    SetString(record, "pvci_sourcekey", sourceKey, 200);
                    SetString(record, "pvci_tenantid", Json.Str(item, "tenantId") ?? tenantId);
                    SetString(record, "pvci_environmentid", Json.Str(item, "environmentId"));
                    SetString(record, "pvci_resourceid", Json.Str(item, "resourceId"));
                    SetString(record, "pvci_agentname", Json.Str(item, "agentName"));
                    SetDate(record, "pvci_usagedate", Json.Get(item, "usageDate"), null);
                    SetDate(record, "pvci_fromdate", Json.Get(item, "fromDate"), null);
                    SetDate(record, "pvci_todate", Json.Get(item, "toDate"), null);
                    SetString(record, "pvci_entitlementid", Json.Str(item, "entitlementId"));
                    SetString(record, "pvci_sourceunit", Json.Str(item, "sourceUnit"));
                    SetDecimal(record, "pvci_billedcredits", Json.Get(item, "billedCredits"));
                    SetDecimal(record, "pvci_nonbilledcredits", Json.Get(item, "nonBilledCredits"));
                    SetString(record, "pvci_featurename", Json.Str(item, "featureName"));
                    SetString(record, "pvci_channelid", Json.Str(item, "channelId"));
                    SetMemo(record, "pvci_toolinvoked", Json.Get(item, "toolInvoked"));
                    SetMemo(record, "pvci_knowledgesources", Json.Get(item, "knowledgeSources"));
                    SetString(record, "pvci_llmmodel", Json.Str(item, "llmModel"));
                    SetMemo(record, "pvci_users", Json.Get(item, "users"));
                    SetString(record, "pvci_resourcetype", Json.Str(item, "resourceType"));
                    SetString(record, "pvci_harness", Json.Str(item, "harness") ?? "unknown");
                    SetString(record, "pvci_resolutionstatus", Json.Str(item, "resolutionStatus") ?? "unresolved");
                    SetString(record, "pvci_sourceapi", Json.Str(item, "sourceApi"));
                    SetString(record, "pvci_sourceschemaversion", Json.Str(item, "sourceSchemaVersion") ?? schemaVersion);
                    SetMemo(record, "pvci_rawjson", Json.Get(item, "raw"));
                    SetDate(record, "pvci_importedon", Json.Get(item, "importedOn"), DateTime.UtcNow);

                    string agentSourceKey = Json.Str(item, "agentSourceKey");
                    Guid agentId = Guid.Empty;
                    if (!string.IsNullOrWhiteSpace(agentSourceKey)
                        && !agentIds.TryGetValue(agentSourceKey, out agentId))
                    {
                        Entity agent = FindByString(service, AgentEntity, "pvci_sourcekey", agentSourceKey,
                            "pvci_agentinventoryid");
                        agentId = agent != null ? agent.Id : Guid.Empty;
                    }
                    if (agentId != Guid.Empty)
                        record["pvci_agentid"] = new EntityReference(AgentEntity, agentId);

                    Upsert(service, existing, record, dryRun, result);
                }
                catch (Exception ex)
                {
                    Reject(result, errors, "usage", item, ex);
                }
            }
        }

        private static void ImportCapacity(
            IOrganizationService service,
            List<object> records,
            string tenantId,
            bool dryRun,
            ImportResult result,
            List<string> errors)
        {
            records = records ?? new List<object>();
            ValidateRecordCount(records, "capacity");
            foreach (object item in records)
            {
                try
                {
                    string sourceKey = Required(item, "sourceKey");
                    Entity existing = FindByString(service, CapacityEntity, "pvci_sourcekey", sourceKey,
                        "pvci_creditcapacitysnapshotid");
                    var record = new Entity(CapacityEntity);
                    SetString(record, "pvci_name", Json.Str(item, "name") ?? Json.Str(item, "environmentName") ?? sourceKey, 200);
                    SetString(record, "pvci_sourcekey", sourceKey, 200);
                    SetString(record, "pvci_tenantid", Json.Str(item, "tenantId") ?? tenantId);
                    SetString(record, "pvci_environmentid", Json.Str(item, "environmentId"));
                    SetString(record, "pvci_environmentname", Json.Str(item, "environmentName"));
                    SetString(record, "pvci_entitlementid", Json.Str(item, "entitlementId"));
                    SetDate(record, "pvci_asofdate", Json.Get(item, "asOfDate"), DateTime.UtcNow);
                    SetDecimal(record, "pvci_entitled", Json.Get(item, "entitled"));
                    SetDecimal(record, "pvci_allocated", Json.Get(item, "allocated"));
                    SetDecimal(record, "pvci_autoallocated", Json.Get(item, "autoAllocated"));
                    SetDecimal(record, "pvci_consumed", Json.Get(item, "consumed"));
                    SetDecimal(record, "pvci_available", Json.Get(item, "available"));
                    SetDecimal(record, "pvci_paygoentitled", Json.Get(item, "payGoEntitled"));
                    SetDecimal(record, "pvci_paygoconsumed", Json.Get(item, "payGoConsumed"));
                    SetString(record, "pvci_status", Json.Str(item, "status"));
                    SetBoolean(record, "pvci_drawfromtenantpool", Json.Get(item, "drawFromTenantPool"));
                    SetBoolean(record, "pvci_alertenabled", Json.Get(item, "alertEnabled"));
                    SetDecimal(record, "pvci_alertthreshold", Json.Get(item, "alertThreshold"));
                    SetString(record, "pvci_sourceapi", Json.Str(item, "sourceApi"));
                    SetMemo(record, "pvci_rawjson", Json.Get(item, "raw"));
                    SetDate(record, "pvci_capturedon", Json.Get(item, "capturedOn"), DateTime.UtcNow);
                    Upsert(service, existing, record, dryRun, result);
                }
                catch (Exception ex)
                {
                    Reject(result, errors, "capacity", item, ex);
                }
            }
        }

        private static void ImportUserUsage(
            IOrganizationService service,
            List<object> records,
            string tenantId,
            string schemaVersion,
            bool dryRun,
            ImportResult result,
            List<string> errors)
        {
            records = records ?? new List<object>();
            ValidateRecordCount(records, "userUsage");
            bool revealNames = IsUserNameDisclosureApproved(service);
            var identities = new Dictionary<string, Entity>(StringComparer.OrdinalIgnoreCase);
            foreach (object item in records)
            {
                try
                {
                    string sourceKey = Required(item, "sourceKey");
                    string userId = Required(item, "userId");
                    Entity existing = FindByString(service, UserUsageEntity, "pvci_sourcekey", sourceKey,
                        "pvci_credituserusageid");
                    var record = new Entity(UserUsageEntity);
                    SetString(record, "pvci_name", userId, 200);
                    SetString(record, "pvci_sourcekey", sourceKey, 200);
                    SetString(record, "pvci_tenantid", Json.Str(item, "tenantId") ?? tenantId);
                    SetString(record, "pvci_userid", userId);
                    SetDate(record, "pvci_usagedate", Json.Get(item, "usageDate"), null);
                    SetDate(record, "pvci_fromdate", Json.Get(item, "fromDate"), null);
                    SetDate(record, "pvci_todate", Json.Get(item, "toDate"), null);
                    SetString(record, "pvci_entitlementid", Json.Str(item, "entitlementId"));
                    SetString(record, "pvci_sourceunit", Json.Str(item, "sourceUnit"));
                    SetDecimal(record, "pvci_billedcredits", Json.Get(item, "billedCredits"));
                    SetDecimal(record, "pvci_nonbilledcredits", Json.Get(item, "nonBilledCredits"));
                    SetMemo(record, "pvci_resources", Json.Get(item, "resources"));
                    SetString(record, "pvci_sourceapi", Json.Str(item, "sourceApi"));
                    SetString(record, "pvci_sourceschemaversion", Json.Str(item, "sourceSchemaVersion") ?? schemaVersion);
                    SetDate(record, "pvci_importedon", Json.Get(item, "importedOn"), DateTime.UtcNow);
                    ClearResolvedIdentity(record);
                    if (revealNames) ApplyResolvedIdentity(service, record, userId, identities);
                    else SetString(record, "pvci_nameresolutionstatus", "hidden_pending_approval");
                    Upsert(service, existing, record, dryRun, result);
                }
                catch (Exception ex)
                {
                    Reject(result, errors, "userUsage", item, ex);
                }
            }
        }

        private static bool IsUserNameDisclosureApproved(IOrganizationService service)
        {
            Entity setting = FindByString(service, PrivacySettingEntity, "pvci_settingkey", "credit-user-disclosure",
                "pvci_creditprivacysettingid", "pvci_revealusernames");
            return setting != null && setting.GetAttributeValue<bool>("pvci_revealusernames");
        }

        private static void ClearResolvedIdentity(Entity record)
        {
            record["pvci_userdisplayname"] = null;
            record["pvci_userprincipalname"] = null;
            record["pvci_systemuserid"] = null;
        }

        private static void ApplyResolvedIdentity(
            IOrganizationService service,
            Entity record,
            string userId,
            Dictionary<string, Entity> identities)
        {
            if (string.Equals(userId, Guid.Empty.ToString(), StringComparison.OrdinalIgnoreCase))
            {
                record["pvci_name"] = "Background activity";
                record["pvci_userdisplayname"] = "Background activity";
                record["pvci_nameresolutionstatus"] = "background";
                return;
            }
            Entity user;
            if (!identities.TryGetValue(userId, out user))
            {
                Guid aadId;
                if (Guid.TryParse(userId, out aadId))
                {
                    var query = new QueryExpression("systemuser")
                    {
                        ColumnSet = new ColumnSet("systemuserid", "fullname", "domainname"),
                        TopCount = 1,
                    };
                    query.Criteria.AddCondition("azureactivedirectoryobjectid", ConditionOperator.Equal, aadId);
                    user = service.RetrieveMultiple(query).Entities.FirstOrDefault();
                }
                identities[userId] = user;
            }
            if (user == null)
            {
                record["pvci_nameresolutionstatus"] = "unresolved";
                return;
            }
            string displayName = user.GetAttributeValue<string>("fullname") ?? userId;
            record["pvci_name"] = Trim(displayName, 200);
            record["pvci_userdisplayname"] = Trim(displayName, TextLimit);
            record["pvci_userprincipalname"] = Trim(user.GetAttributeValue<string>("domainname"), TextLimit);
            record["pvci_systemuserid"] = user.Id.ToString();
            record["pvci_nameresolutionstatus"] = "exact";
        }

        private static void UpsertSyncRun(
            IOrganizationService service,
            object item,
            string schemaVersion,
            ImportResult result,
            List<string> errors)
        {
            try
            {
                string runKey = Required(item, "runKey");
                Entity existing = FindByString(service, SyncRunEntity, "pvci_runkey", runKey,
                    "pvci_creditsyncrunid");
                var record = new Entity(SyncRunEntity);
                SetString(record, "pvci_name", Json.Str(item, "name") ?? runKey, 200);
                SetString(record, "pvci_runkey", runKey, 200);
                SetString(record, "pvci_source", Json.Str(item, "source"));
                SetDate(record, "pvci_startedon", Json.Get(item, "startedOn"), null);
                SetDate(record, "pvci_completedon", Json.Get(item, "completedOn"), DateTime.UtcNow);
                int priorCreated = Integer(item, "priorCreatedCount");
                int priorUpdated = Integer(item, "priorUpdatedCount");
                int priorRejected = Integer(item, "priorRejectedCount");
                int priorFailedChunks = Integer(item, "priorFailedChunkCount");
                SetString(record, "pvci_status",
                    errors.Count == 0 && priorRejected == 0 && priorFailedChunks == 0 ? "success" : "partial");
                SetDate(record, "pvci_fromdate", Json.Get(item, "fromDate"), null);
                SetDate(record, "pvci_todate", Json.Get(item, "toDate"), null);
                SetInteger(record, "pvci_pagecount", Json.Get(item, "pageCount"));
                SetInteger(record, "pvci_sourcecount", Json.Get(item, "sourceCount"));
                record["pvci_createdcount"] = checked(priorCreated + result.Created);
                record["pvci_updatedcount"] = checked(priorUpdated + result.Updated);
                record["pvci_skippedcount"] = result.Skipped;
                record["pvci_rejectedcount"] = checked(priorRejected + result.Rejected);
                SetString(record, "pvci_schemaversion", Json.Str(item, "schemaVersion") ?? schemaVersion);
                var syncErrors = new List<string>();
                if (priorFailedChunks > 0)
                    syncErrors.Add(priorFailedChunks + " user chunk import(s) failed before returning row outcomes.");
                if (priorRejected > 0) syncErrors.Add("User chunk imports rejected " + priorRejected + " row(s).");
                syncErrors.AddRange(errors);
                SetMemo(record, "pvci_error", syncErrors.Count > 0 ? string.Join("\n", syncErrors.ToArray()) : string.Empty);
                if (existing != null)
                {
                    record.Id = existing.Id;
                    service.Update(record);
                }
                else service.Create(record);
            }
            catch (Exception ex)
            {
                result.Rejected++;
                errors.Add("syncRun: " + ex.Message);
            }
        }

        private static Guid Upsert(
            IOrganizationService service,
            Entity existing,
            Entity record,
            bool dryRun,
            ImportResult result)
        {
            if (existing != null)
            {
                result.Updated++;
                if (!dryRun)
                {
                    record.Id = existing.Id;
                    service.Update(record);
                }
                return existing.Id;
            }
            result.Created++;
            return dryRun ? Guid.Empty : service.Create(record);
        }

        private static Entity FindByString(
            IOrganizationService service,
            string entity,
            string field,
            string value,
            params string[] fields)
        {
            var query = new QueryExpression(entity) { ColumnSet = new ColumnSet(fields), TopCount = 1 };
            query.Criteria.AddCondition(field, ConditionOperator.Equal, value);
            EntityCollection result = service.RetrieveMultiple(query);
            return result.Entities.Count > 0 ? result.Entities[0] : null;
        }

        private static void ValidateTenant(IOrganizationService service, Guid organizationId, string payloadTenantId)
        {
            if (string.IsNullOrWhiteSpace(payloadTenantId))
                throw new InvalidPluginExecutionException("tenantId is required.");
            try
            {
                Entity organization = service.Retrieve(
                    "organization", organizationId, new ColumnSet("azureactivedirectorytenantid"));
                object tenantValue = organization.GetAttributeValue<object>("azureactivedirectorytenantid");
                string actualTenantId = tenantValue != null ? tenantValue.ToString() : null;
                if (!string.IsNullOrWhiteSpace(actualTenantId)
                    && !string.Equals(actualTenantId, payloadTenantId, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidPluginExecutionException("Payload tenantId does not match the Dataverse tenant.");
            }
            catch (FaultException<OrganizationServiceFault>)
            {
                // The import API still requires a tenant ID even if this environment doesn't expose the comparison field.
            }
        }

        private static void ValidateRecordCount(List<object> records, string name)
        {
            if (records.Count > RecordLimit)
                throw new InvalidPluginExecutionException(name + " exceeds the 2,000 record batch limit.");
        }

        private static string Required(object item, string key)
        {
            string value = Json.Str(item, key);
            if (string.IsNullOrWhiteSpace(value)) throw new InvalidPluginExecutionException(key + " is required.");
            return value;
        }

        private static void SetString(Entity record, string field, string value, int max = TextLimit)
        {
            if (value != null) record[field] = Trim(value, max);
        }

        private static void SetMemo(Entity record, string field, object value)
        {
            if (value == null) return;
            string text = value as string ?? Json.Write(value);
            record[field] = Trim(text, MemoLimit);
        }

        private static void SetDate(Entity record, string field, object value, DateTime? fallback)
        {
            DateTime parsed;
            if (value is string && DateTime.TryParse((string)value, CultureInfo.InvariantCulture,
                    DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal, out parsed))
                record[field] = parsed.ToUniversalTime();
            else if (fallback.HasValue) record[field] = fallback.Value;
        }

        private static void SetDecimal(Entity record, string field, object value)
        {
            if (value is double) record[field] = Convert.ToDecimal((double)value, CultureInfo.InvariantCulture);
            else if (value is string)
            {
                decimal parsed;
                if (decimal.TryParse((string)value, NumberStyles.Float, CultureInfo.InvariantCulture, out parsed))
                    record[field] = parsed;
            }
        }

        private static void SetInteger(Entity record, string field, object value)
        {
            if (value is int) record[field] = (int)value;
            else if (value is long) record[field] = checked((int)(long)value);
            else if (value is double) record[field] = Convert.ToInt32((double)value, CultureInfo.InvariantCulture);
            else if (value is string)
            {
                int parsed;
                if (int.TryParse((string)value, NumberStyles.Integer, CultureInfo.InvariantCulture, out parsed))
                    record[field] = parsed;
            }
        }

        private static int Integer(object item, string key)
        {
            object value = Json.Get(item, key);
            if (value is int) return (int)value;
            if (value is long) return checked((int)(long)value);
            if (value is double) return Convert.ToInt32((double)value, CultureInfo.InvariantCulture);
            int parsed;
            return value is string
                && int.TryParse((string)value, NumberStyles.Integer, CultureInfo.InvariantCulture, out parsed)
                ? parsed
                : 0;
        }

        private static void SetBoolean(Entity record, string field, object value)
        {
            if (value is bool) record[field] = (bool)value;
            else if (value is string)
            {
                bool parsed;
                if (bool.TryParse((string)value, out parsed)) record[field] = parsed;
            }
        }

        private static void Reject(ImportResult result, List<string> errors, string kind, object item, Exception ex)
        {
            result.Rejected++;
            string key = Json.Str(item, "sourceKey") ?? Json.Str(item, "runKey") ?? "unknown";
            if (errors.Count < 100) errors.Add(kind + " " + Trim(key, 80) + ": " + ex.Message);
        }

        private static string Trim(string value, int max)
        {
            if (string.IsNullOrEmpty(value)) return value;
            return value.Length <= max ? value : value.Substring(0, max);
        }

        private static T GetInput<T>(IPluginExecutionContext context, string name, T fallback)
        {
            object value;
            return context.InputParameters.TryGetValue(name, out value) && value is T ? (T)value : fallback;
        }

        private static void SetOutput(IPluginExecutionContext context, string name, object value)
        {
            context.OutputParameters[name] = value ?? string.Empty;
        }
    }
}