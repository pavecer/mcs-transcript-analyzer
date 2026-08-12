import unittest

from scripts.transcript_insights.create_security_roles import (
    privilege_name,
    required_privilege_names,
    table_schema_names,
)


class SecurityRoleProvisioningTests(unittest.TestCase):
    def test_privilege_name_preserves_table_schema_casing(self) -> None:
        self.assertEqual("prvReadpvci_CreditUsage", privilege_name("Read", "pvci_CreditUsage"))

    def test_system_user_uses_platform_schema_name(self) -> None:
        role = {"tablePrivileges": {"systemuser": ["Read"]}}
        self.assertEqual({"prvReadUser"}, required_privilege_names(role, {}))

    def test_role_privileges_resolve_from_solution_tables(self) -> None:
        definition = {
            "tables": [{"schemaName": "pvci_CreditUsage"}],
        }
        schemas = table_schema_names(definition)
        role = {"tablePrivileges": {"pvci_creditusage": ["Read", "Write"]}}
        self.assertEqual(
            {"prvReadpvci_CreditUsage", "prvWritepvci_CreditUsage"},
            required_privilege_names(role, schemas),
        )


if __name__ == "__main__":
    unittest.main()