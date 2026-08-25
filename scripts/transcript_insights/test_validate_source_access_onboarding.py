import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_source_access_onboarding import (
    AUTHORIZED_TENANT_ID,
    BASELINE_ROLE,
    COLLECTOR_ROLE,
    parse_service_principal,
    parse_service_principal_ids,
)


class SourceAccessOnboardingTests(unittest.TestCase):
    def test_authorized_tenant_is_fixed(self) -> None:
        self.assertEqual("1938ee32-a258-454c-b8db-3a928341bd69", AUTHORIZED_TENANT_ID)

    def test_test_roles_are_not_system_administrator(self) -> None:
        self.assertNotEqual("System Administrator", BASELINE_ROLE)
        self.assertNotEqual("System Administrator", COLLECTOR_ROLE)

    def test_parses_pac_service_principal_output(self) -> None:
        output = """
        Application ID: 11111111-2222-3333-4444-555555555555
        Client Secret: top-secret-value
        """
        app_id, secret = parse_service_principal(output)
        self.assertEqual("11111111-2222-3333-4444-555555555555", app_id)
        self.assertEqual("top-secret-value", secret)

    def test_parses_pac_aligned_output(self) -> None:
        output = """
        Application Name         PVCI Collector E2E
        Tenant Id                aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee
        Application Id           11111111-2222-3333-4444-555555555555
        Service Principal Id     66666666-7777-8888-9999-aaaaaaaaaaaa
        Client Secret            top-secret-value
        """
        app_id, secret = parse_service_principal(output)
        self.assertEqual("11111111-2222-3333-4444-555555555555", app_id)
        self.assertEqual("top-secret-value", secret)

    def test_rejects_output_without_credentials(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "expected application credentials"):
            parse_service_principal("Application creation failed")

    def test_parses_service_principal_listing_ids(self) -> None:
        output = """
        App Id                               Secret Expiry        Name
        A0BD5706-681D-4902-8E3F-04E725EABDBF 2027-08-21           PVCI Collector E2E
        """
        self.assertEqual(
            {"a0bd5706-681d-4902-8e3f-04e725eabdbf"},
            parse_service_principal_ids(output),
        )


if __name__ == "__main__":
    unittest.main()