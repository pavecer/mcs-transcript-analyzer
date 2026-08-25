import unittest
from unittest.mock import patch

from scripts.transcript_insights.dv_token import _az_command


class AzureCliTokenCommandTests(unittest.TestCase):
    @patch("scripts.transcript_insights.dv_token.shutil.which")
    def test_windows_batch_wrapper_runs_through_cmd(self, which):
        which.return_value = r"C:\Program Files\Azure CLI\az.CMD"

        command = _az_command("https://source.crm.dynamics.com")

        self.assertEqual("cmd.exe", command[0])
        self.assertEqual(["/d", "/c"], command[1:3])
        self.assertEqual(r"C:\Program Files\Azure CLI\az.CMD", command[3])
        self.assertEqual("https://source.crm.dynamics.com", command[-3])

    @patch("scripts.transcript_insights.dv_token.shutil.which")
    def test_native_azure_cli_runs_directly(self, which):
        which.return_value = "/usr/local/bin/az"

        command = _az_command("https://source.crm.dynamics.com")

        self.assertEqual("/usr/local/bin/az", command[0])
        self.assertNotIn("cmd.exe", command)

    @patch("scripts.transcript_insights.dv_token.shutil.which")
    def test_token_request_is_scoped_to_configured_tenant(self, which):
        which.return_value = "/usr/local/bin/az"

        command = _az_command(
            "https://source.crm.dynamics.com",
            "11111111-2222-3333-4444-555555555555",
        )

        self.assertEqual(
            ["--tenant", "11111111-2222-3333-4444-555555555555"],
            command[-2:],
        )


if __name__ == "__main__":
    unittest.main()