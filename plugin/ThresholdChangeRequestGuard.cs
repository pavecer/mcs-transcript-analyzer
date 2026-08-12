using System;
using Microsoft.Xrm.Sdk;

namespace PvciTranscripts
{
    public class ThresholdChangeRequestGuard : IPlugin
    {
        private const string EntityName = "pvci_thresholdchangerequest";

        public void Execute(IServiceProvider serviceProvider)
        {
            var context = (IPluginExecutionContext)serviceProvider.GetService(typeof(IPluginExecutionContext));
            if (!string.Equals(context.MessageName, "Create", StringComparison.OrdinalIgnoreCase) || context.Stage != 20)
                return;
            if (!context.InputParameters.Contains("Target") || !(context.InputParameters["Target"] is Entity target) || target.LogicalName != EntityName)
                throw new InvalidPluginExecutionException("A threshold change request target is required.");

            RequireText(target, "pvci_environmentid", "Environment ID");
            RequireText(target, "pvci_resourceid", "Resource ID");
            string entitlement = RequireText(target, "pvci_entitlementid", "Entitlement ID");
            if (!string.Equals(entitlement, "MCSMessages", StringComparison.Ordinal))
                throw new InvalidPluginExecutionException("Only the MCSMessages entitlement is supported.");

            string justification = RequireText(target, "pvci_justification", "Justification");
            if (justification.Trim().Length < 10)
                throw new InvalidPluginExecutionException("Justification must contain at least 10 characters.");

            decimal requestedLimit = RequireDecimal(target, "pvci_requestedlimit", "Requested monthly limit");
            if (requestedLimit < 0 || decimal.Truncate(requestedLimit) != requestedLimit)
                throw new InvalidPluginExecutionException("Requested monthly limit must be a non-negative whole number.");

            int notificationThreshold = RequireInt(target, "pvci_requestednotificationthreshold", "Requested notification percent");
            if (notificationThreshold < 0 || notificationThreshold > 100)
                throw new InvalidPluginExecutionException("Requested notification percent must be between 0 and 100.");

            RequireDecimal(target, "pvci_expectedlimit", "Expected current limit");
            RequireInt(target, "pvci_expectednotificationthreshold", "Expected notification percent");
            RequireBool(target, "pvci_requestednotifyifovercapacity", "Requested notification setting");
            RequireBool(target, "pvci_requestedstopifovercapacity", "Requested stop-at-limit setting");
            RequireBool(target, "pvci_requestedstopresource", "Requested explicit-stop setting");
            RequireBool(target, "pvci_expectednotifyifovercapacity", "Expected notification setting");
            RequireBool(target, "pvci_expectedstopifovercapacity", "Expected stop-at-limit setting");
            RequireBool(target, "pvci_expectedstopresource", "Expected explicit-stop setting");

            target["pvci_status"] = "Pending";
            target["pvci_requestedon"] = DateTime.UtcNow;
            target.Attributes.Remove("pvci_processedon");
            target.Attributes.Remove("pvci_beforejson");
            target.Attributes.Remove("pvci_afterjson");
            target.Attributes.Remove("pvci_error");
        }

        private static string RequireText(Entity target, string logicalName, string displayName)
        {
            string value = target.GetAttributeValue<string>(logicalName);
            if (string.IsNullOrWhiteSpace(value))
                throw new InvalidPluginExecutionException(displayName + " is required.");
            return value;
        }

        private static decimal RequireDecimal(Entity target, string logicalName, string displayName)
        {
            if (!target.Attributes.Contains(logicalName) || !(target[logicalName] is decimal value))
                throw new InvalidPluginExecutionException(displayName + " is required.");
            return value;
        }

        private static int RequireInt(Entity target, string logicalName, string displayName)
        {
            if (!target.Attributes.Contains(logicalName) || !(target[logicalName] is int value))
                throw new InvalidPluginExecutionException(displayName + " is required.");
            return value;
        }

        private static void RequireBool(Entity target, string logicalName, string displayName)
        {
            if (!target.Attributes.Contains(logicalName) || !(target[logicalName] is bool))
                throw new InvalidPluginExecutionException(displayName + " is required.");
        }
    }
}