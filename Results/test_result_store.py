import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Results.result_store import save_execution_run, sync_pending_runs, sync_status


class FakeQuery:
    def __init__(self, client, table):
        self.client = client
        self.table_name = table
        self.rows = None
        self.conflict = None

    def upsert(self, rows, on_conflict):
        self.rows = rows
        self.conflict = on_conflict
        return self

    def execute(self):
        if self.client.failure:
            raise RuntimeError("simulated cloud outage")
        self.client.calls.append((self.table_name, self.rows, self.conflict))


class FakeClient:
    def __init__(self, failure=False):
        self.failure = failure
        self.calls = []

    def table(self, name):
        return FakeQuery(self, name)


class ResultStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "results.sqlite3"
        self.records = [
            {
                "Environment_Name": "QA",
                "Module_Name": "Billing",
                "TestCase_Name": "TC login",
                "Result": "Passed",
                "StartTime": "19-11-2026 10:15:00",
            }
        ]

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cloud_sync_upserts_run_and_results(self):
        save_execution_run(self.records, self.db_path)
        fake_client = FakeClient()
        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_KEY": "sb_secret_test",
            },
        ), patch("supabase.create_client", return_value=fake_client):
            result = sync_pending_runs(self.db_path)

        self.assertEqual(result["status"], "ok")
        self.assertEqual([call[0] for call in fake_client.calls], [
            "execution_runs",
            "test_case_results",
        ])
        self.assertEqual(sync_status(self.db_path)["pending_runs"], 0)

    def test_failed_cloud_sync_keeps_run_pending(self):
        save_execution_run(self.records, self.db_path)
        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_KEY": "sb_secret_test",
            },
        ), patch("supabase.create_client", return_value=FakeClient(failure=True)):
            result = sync_pending_runs(self.db_path)

        self.assertEqual(result["status"], "pending")
        self.assertEqual(sync_status(self.db_path)["pending_runs"], 1)

    def test_publishable_key_is_rejected_without_cloud_client(self):
        save_execution_run(self.records, self.db_path)
        with patch.dict(
            os.environ,
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_KEY": "sb_publishable_test",
            },
        ), patch("supabase.create_client") as create_client:
            result = sync_pending_runs(self.db_path)

        self.assertEqual(result["status"], "server_secret_required")
        create_client.assert_not_called()
        self.assertEqual(sync_status(self.db_path)["pending_runs"], 1)


if __name__ == "__main__":
    unittest.main()