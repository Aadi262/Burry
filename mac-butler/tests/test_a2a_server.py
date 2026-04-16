#!/usr/bin/env python3

import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from channels import a2a_server


class A2AServerContractTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), a2a_server.A2AHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _get(self, path: str) -> tuple[int, dict]:
        try:
            with urlopen(f"{self.base_url}{path}", timeout=2) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def _post(self, path: str, payload: dict) -> tuple[int, dict]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=2) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def test_v1_agent_card_advertises_versioned_endpoints(self):
        status, payload = self._get("/api/v1/agent-card")

        self.assertEqual(status, 200)
        self.assertEqual(payload["contract_version"], a2a_server.CONTRACT_VERSION)
        self.assertTrue(payload["endpoints"]["run"].endswith("/api/v1/run"))
        self.assertTrue(payload["endpoints"]["interrupt"].endswith("/api/v1/interrupt"))
        self.assertTrue(all(isinstance(item, dict) for item in payload["capabilities"]["tools"]))
        self.assertIn("capability_id", payload["capabilities"]["tools"][0])

    @patch("channels.a2a_server._run_task")
    def test_v1_run_accepts_command_request_payload(self, mock_run_task):
        started = threading.Event()
        mock_run_task.side_effect = lambda _task: started.set()

        status, payload = self._post("/api/v1/run", {"text": "open cursor", "source": "hud"})

        self.assertEqual(status, 202)
        self.assertEqual(payload["contract_version"], a2a_server.CONTRACT_VERSION)
        self.assertEqual(payload["status"], "accepted")
        self.assertEqual(payload["data"]["task"], "open cursor")
        self.assertTrue(started.wait(timeout=1.0))
        mock_run_task.assert_called_once_with("open cursor")

    def test_health_route_reports_contract_version(self):
        status, payload = self._get("/api/v1/health")

        self.assertEqual(status, 200)
        self.assertEqual(payload["api_version"], "v1")
        self.assertEqual(payload["contract_version"], a2a_server.CONTRACT_VERSION)

    def test_legacy_agent_card_route_is_removed(self):
        status, payload = self._get("/agent-card")

        self.assertEqual(status, 404)
        self.assertEqual(payload["code"], "not_found")


if __name__ == "__main__":
    unittest.main()
