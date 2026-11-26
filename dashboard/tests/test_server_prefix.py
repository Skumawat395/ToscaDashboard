"""The dashboard served under a sub-path (URL_PREFIX), as behind IIS at
https://ondemandqa.com/automationreports."""

import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # dashboard/


def load_server(prefix: str):
    with patch.dict(os.environ, {"URL_PREFIX": prefix}):
        import server

        return importlib.reload(server)


class PrefixTests(unittest.TestCase):
    def setUp(self):
        self.server = load_server("/automationreports")
        self.client = self.server.app.test_client()

    def tearDown(self):
        load_server("")  # leave an unprefixed module for other tests

    def test_page_and_api_live_under_the_prefix(self):
        self.assertEqual(self.client.get("/automationreports/").status_code, 200)
        self.assertEqual(self.client.get("/automationreports/api/auth-status").status_code, 200)
        self.assertEqual(self.client.get("/automationreports/api/results").status_code, 401)

    def test_bare_prefix_and_root_redirect_to_prefix_with_slash(self):
        for path in ("/automationreports", "/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 308, path)
            self.assertEqual(response.headers["Location"], "/automationreports/")

    def test_paths_outside_the_prefix_are_not_served(self):
        self.assertEqual(self.client.get("/api/results").status_code, 404)

    def test_health_also_answers_without_prefix(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)

    def test_login_cookie_is_scoped_to_the_prefix(self):
        with patch.object(self.server, "DASHBOARD_USERNAME", "u"), patch.object(
            self.server, "DASHBOARD_PASSWORD", "p"
        ):
            response = self.client.post(
                "/automationreports/api/login", json={"username": "u", "password": "p"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Path=/automationreports/", response.headers["Set-Cookie"])
        self.assertEqual(self.client.get("/automationreports/api/auth-status").get_json(),
                         {"authenticated": True})

    def test_execution_redirect_stays_under_prefix(self):
        response = self.client.get("/automationreports/execution")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].startswith("/automationreports/"))

    def test_page_uses_only_relative_urls(self):
        html = self.client.get("/automationreports/").get_data(as_text=True)
        for absolute in ("fetch('/api", 'src="/assets', "assign('/"):
            self.assertNotIn(absolute, html)


class NoPrefixTests(unittest.TestCase):
    def test_served_at_root_when_prefix_is_empty(self):
        client = load_server("").app.test_client()
        self.assertEqual(client.get("/").status_code, 200)
        self.assertEqual(client.get("/api/auth-status").status_code, 200)


if __name__ == "__main__":
    unittest.main()
