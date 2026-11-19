"""Retry uploading locally stored Tosca runs to Supabase."""

from result_store import sync_pending_runs, sync_status


def main() -> int:
    result = sync_pending_runs()
    status = sync_status()
    print(f"Sync result: {result['status']}")
    print(f"Runs synced this time: {result['synced_runs']}")
    print(f"Runs still pending: {status['pending_runs']}")
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())