import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # dashboard/

from result_store import (  # noqa: E402
    get_execution_results,
    save_execution_run,
    save_new_executions,
    sync_pending_runs,
    sync_status,
)


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

    def test_reimport_skips_logs_already_stored(self):
        first = save_execution_run(self.records, self.db_path)
        self.assertIsNotNone(first)
        # Same Tosca log read again (entry not re-executed) -> no new run.
        self.assertIsNone(save_execution_run(self.records, self.db_path))
        self.assertEqual(sync_status(self.db_path)["total_runs"], 1)

    def test_new_execution_is_added_as_separate_run(self):
        save_execution_run(self.records, self.db_path)
        rerun = dict(self.records[0], StartTime="21-11-2026 09:00:00", Result="Failed")
        # Batch contains the new log twice plus the old one: only the new log is stored, once.
        run_id = save_execution_run([self.records[0], rerun, dict(rerun)], self.db_path)
        self.assertIsNotNone(run_id)
        rows = [r for r in get_execution_results(self.db_path) if r["run_id"] == run_id]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Result"], "Failed")
        self.assertEqual(sync_status(self.db_path)["total_runs"], 2)


    def _log(self, name, start, end):
        return dict(self.records[0], TestCase_Name=name, StartTime=start, EndTime=end)

    def test_two_executions_before_one_import_become_two_reports(self):
        save_new_executions(self.records, self.db_path)  # earlier import (19-11 10:15)
        logs = self.records + [  # TCShell returns ALL logs, old one included
            self._log("TC a", "20-11-2026 09:00:00", "20-11-2026 09:05:00"),
            self._log("TC b", "20-11-2026 09:06:00", "20-11-2026 09:20:00"),
            self._log("TC a", "20-11-2026 14:00:00", "20-11-2026 14:04:00"),
        ]
        run_ids = save_new_executions(logs, self.db_path, gap_minutes=60)
        self.assertEqual(len(run_ids), 2)
        rows = get_execution_results(self.db_path)
        per_run = {rid: sorted(r["TestCaseName"] for r in rows if r["run_id"] == rid) for rid in run_ids}
        self.assertEqual(per_run[run_ids[0]], ["TC a", "TC b"])
        self.assertEqual(per_run[run_ids[1]], ["TC a"])
        # Importing the same output again adds nothing.
        self.assertEqual(save_new_executions(logs, self.db_path), [])
        self.assertEqual(sync_status(self.db_path)["total_runs"], 3)


if __name__ == "__main__":
    unittest.main()