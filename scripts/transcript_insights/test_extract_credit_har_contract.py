from __future__ import annotations

import json
import unittest

from scripts.transcript_insights.extract_credit_har_contract import extract_contract


TENANT_ID = "11111111-2222-3333-4444-555555555555"
ENVIRONMENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
RESOURCE_ID = "99999999-8888-7777-6666-555555555555"


def entry(method: str, url: str, response_body: object, request_body: object | None = None) -> dict:
    request = {
        "method": method,
        "url": url,
        "headers": [{"name": "Authorization", "value": "Bearer secret-token"}],
        "cookies": [{"name": "session", "value": "secret-cookie"}],
    }
    if request_body is not None:
        request["postData"] = {"text": json.dumps(request_body)}
    return {
        "request": request,
        "response": {
            "status": 200,
            "content": {"mimeType": "application/json", "text": json.dumps(response_body)},
        },
    }


class ExtractCreditHarContractTests(unittest.TestCase):
    def test_extracts_schemas_without_copying_sensitive_values(self) -> None:
        resource_url = (
            f"https://licensing.powerplatform.microsoft.com/v2.0/tenants/{TENANT_ID}"
            "/entitlements/MCSMessages/resources"
            "?fromDate=2026-08-01&toDate=2026-08-10&pageSize=5&includeFields=users"
        )
        report_url = (
            f"https://licensing.powerplatform.microsoft.com/v1.0/tenants/{TENANT_ID}/Downloads"
        )
        document = {
            "log": {
                "entries": [
                    entry(
                        "GET",
                        resource_url,
                        {
                            "value": [
                                {
                                    "environmentId": ENVIRONMENT_ID,
                                    "resourceId": RESOURCE_ID,
                                    "consumed": 3.5,
                                    "metadata": {
                                        "ResourceName": "Sensitive agent name",
                                        "NonBillableQuantity": 2.0,
                                        "Users": 1,
                                    },
                                }
                            ]
                        },
                    ),
                    entry(
                        "POST",
                        report_url,
                        {"downloadType": "CapacityConsumptionTenantDetailsReport", "fileProcessingStatus": "NotStarted"},
                        {
                            "downloadType": "CapacityConsumptionTenantDetailsReport",
                            "filters": {"capacityTypes": "MCSMessages", "LookbackDays": "60"},
                        },
                    ),
                ]
            }
        }

        contract = extract_contract(document)
        serialized = json.dumps(contract)

        self.assertEqual(contract["entriesAnalyzed"], 2)
        self.assertEqual(contract["coverage"]["meters"], ["MCSMessages"])
        self.assertEqual(
            contract["coverage"]["reportTypes"],
            ["CapacityConsumptionTenantDetailsReport"],
        )
        self.assertEqual(contract["coverage"]["reportJobStatuses"], ["NotStarted"])
        self.assertNotIn(TENANT_ID, serialized)
        self.assertNotIn(ENVIRONMENT_ID, serialized)
        self.assertNotIn(RESOURCE_ID, serialized)
        self.assertNotIn("Sensitive agent name", serialized)
        self.assertNotIn("secret-token", serialized)
        self.assertNotIn("secret-cookie", serialized)

        resource_endpoint = next(
            endpoint for endpoint in contract["endpoints"] if "/resources?" in endpoint["endpoint"]
        )
        self.assertEqual(
            resource_endpoint["endpoint"],
            "/v2.0/tenants/{tenantId}/entitlements/MCSMessages/resources"
            "?fromDate&includeFields&pageSize&toDate",
        )
        response_properties = resource_endpoint["responseSchema"]["properties"]
        item_properties = response_properties["value"]["items"]["properties"]
        self.assertIn("environmentId", item_properties)
        self.assertIn("metadata", item_properties)

    def test_ignores_preflight_telemetry_and_other_hosts(self) -> None:
        document = {
            "log": {
                "entries": [
                    entry(
                        "OPTIONS",
                        f"https://licensing.powerplatform.microsoft.com/v2.0/tenants/{TENANT_ID}/entitlements/MCSMessages",
                        {},
                    ),
                    entry("POST", "https://eu-mobile.events.data.microsoft.com/OneCollector/1.0", {}),
                    entry("GET", "https://graph.microsoft.com/v1.0/users", {}),
                ]
            }
        }

        contract = extract_contract(document)

        self.assertEqual(contract["entriesAnalyzed"], 0)
        self.assertEqual(contract["endpoints"], [])

    def test_preserves_tenant_wide_environment_routes(self) -> None:
        base = f"https://licensing.powerplatform.microsoft.com/v2.0/tenants/{TENANT_ID}"
        document = {
            "log": {
                "entries": [
                    entry("GET", f"{base}/environments/entitlements/MCSMessages?searchRequest=", {}),
                    entry("GET", f"{base}/environments/entitlementConsumptions/MCSMessages", {}),
                    entry(
                        "GET",
                        f"{base}/environments/{ENVIRONMENT_ID}/entitlements/MCSMessages",
                        {},
                    ),
                ]
            }
        }

        endpoints = [item["endpoint"] for item in extract_contract(document)["endpoints"]]

        self.assertIn(
            "/v2.0/tenants/{tenantId}/environments/entitlements/MCSMessages?searchRequest",
            endpoints,
        )
        self.assertIn(
            "/v2.0/tenants/{tenantId}/environments/entitlementConsumptions/MCSMessages",
            endpoints,
        )
        self.assertIn(
            "/v2.0/tenants/{tenantId}/environments/{environmentId}/entitlements/MCSMessages",
            endpoints,
        )

    def test_rejects_non_array_entries(self) -> None:
        with self.assertRaisesRegex(ValueError, "log.entries must be an array"):
            extract_contract({"log": {"entries": {}}})


if __name__ == "__main__":
    unittest.main()