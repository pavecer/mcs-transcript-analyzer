using System;
using Microsoft.Xrm.Sdk;
using Microsoft.Xrm.Sdk.Query;

namespace PvciTranscripts
{
    /// <summary>
    /// Applies the shared user-name disclosure approval to all stored credit user facts.
    /// Registered synchronously after pvci_creditprivacysetting.pvci_revealusernames changes.
    /// </summary>
    public class CreditUserDisclosure : IPlugin
    {
        private const string UserUsageEntity = "pvci_credituserusage";
        private const string SettingEntity = "pvci_creditprivacysetting";

        public void Execute(IServiceProvider serviceProvider)
        {
            var context = (IPluginExecutionContext)serviceProvider.GetService(typeof(IPluginExecutionContext));
            var factory = (IOrganizationServiceFactory)serviceProvider.GetService(typeof(IOrganizationServiceFactory));
            var service = factory.CreateOrganizationService(context.UserId);
            Entity target = context.InputParameters.Contains("Target") ? context.InputParameters["Target"] as Entity : null;
            if (target == null || target.LogicalName != SettingEntity || !target.Contains("pvci_revealusernames")) return;

            bool reveal = target.GetAttributeValue<bool>("pvci_revealusernames");
            Entity approver = service.Retrieve("systemuser", context.InitiatingUserId, new ColumnSet("fullname"));
            var audit = new Entity(SettingEntity, target.Id);
            audit["pvci_approvedbyid"] = context.InitiatingUserId.ToString();
            audit["pvci_approvedbyname"] = approver.GetAttributeValue<string>("fullname") ?? context.InitiatingUserId.ToString();
            if (reveal)
            {
                audit["pvci_approvedon"] = DateTime.UtcNow;
                audit["pvci_revokedon"] = null;
            }
            else
            {
                audit["pvci_revokedon"] = DateTime.UtcNow;
            }
            service.Update(audit);

            var query = new QueryExpression(UserUsageEntity)
            {
                ColumnSet = new ColumnSet("pvci_credituserusageid", "pvci_userid"),
                PageInfo = new PagingInfo { Count = 500, PageNumber = 1 },
            };
            while (true)
            {
                EntityCollection page = service.RetrieveMultiple(query);
                foreach (Entity row in page.Entities) Apply(service, row, reveal);
                if (!page.MoreRecords) break;
                query.PageInfo.PageNumber++;
                query.PageInfo.PagingCookie = page.PagingCookie;
            }
        }

        private static void Apply(IOrganizationService service, Entity source, bool reveal)
        {
            string userId = source.GetAttributeValue<string>("pvci_userid") ?? string.Empty;
            var update = new Entity(UserUsageEntity, source.Id);
            update["pvci_name"] = userId;
            update["pvci_userdisplayname"] = null;
            update["pvci_userprincipalname"] = null;
            update["pvci_systemuserid"] = null;
            update["pvci_nameresolutionstatus"] = "hidden_pending_approval";
            if (reveal && string.Equals(userId, Guid.Empty.ToString(), StringComparison.OrdinalIgnoreCase))
            {
                update["pvci_name"] = "Background activity";
                update["pvci_userdisplayname"] = "Background activity";
                update["pvci_nameresolutionstatus"] = "background";
            }
            else if (reveal)
            {
                Guid aadId;
                Entity user = null;
                if (Guid.TryParse(userId, out aadId))
                {
                    var users = new QueryExpression("systemuser")
                    {
                        ColumnSet = new ColumnSet("systemuserid", "fullname", "domainname"),
                        TopCount = 1,
                    };
                    users.Criteria.AddCondition("azureactivedirectoryobjectid", ConditionOperator.Equal, aadId);
                    EntityCollection matches = service.RetrieveMultiple(users);
                    user = matches.Entities.Count > 0 ? matches.Entities[0] : null;
                }
                if (user != null)
                {
                    string displayName = user.GetAttributeValue<string>("fullname") ?? userId;
                    update["pvci_name"] = Truncate(displayName, 200);
                    update["pvci_userdisplayname"] = Truncate(displayName, 1000);
                    update["pvci_userprincipalname"] = Truncate(user.GetAttributeValue<string>("domainname"), 1000);
                    update["pvci_systemuserid"] = user.Id.ToString();
                    update["pvci_nameresolutionstatus"] = "exact";
                }
                else update["pvci_nameresolutionstatus"] = "unresolved";
            }
            service.Update(update);
        }

        private static string Truncate(string value, int max)
        {
            return string.IsNullOrEmpty(value) || value.Length <= max ? value : value.Substring(0, max);
        }
    }
}