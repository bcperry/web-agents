import unittest
from unittest.mock import patch

import httpx
from fastapi import HTTPException
from fastapi.testclient import TestClient

from client import app, generate, get_token


class ExternalClientTests(unittest.TestCase):
    def test_app_only_token_targets_api(self):
        config = dict(CLIENT_ID="caller", CLIENT_SECRET="test-secret", API_CLIENT_ID="api", TENANT_ID="tenant", AUTHORITY="https://login.microsoftonline.us")
        with patch("client.msal.ConfidentialClientApplication") as identity:
            identity.return_value.acquire_token_for_client.return_value = {"access_token": "test-token"}
            self.assertEqual(get_token(config), "test-token")
            identity.assert_called_once_with("caller", authority="https://login.microsoftonline.us/tenant", client_credential="test-secret", timeout=30)
            identity.return_value.acquire_token_for_client.assert_called_once_with(scopes=["api://api/.default"])

    def test_generation_and_cleanup(self):
        requests = []

        def backend(request):
            requests.append(request)
            if request.url.path == "/api/sessions":
                return httpx.Response(201, json={"session_id": "test-session"})
            if request.method == "DELETE":
                return httpx.Response(204)
            return httpx.Response(200, text='event: text\ndata: {"content":"Hello"}\n\nevent: text\ndata: {"content":"!"}\n\nevent: done\ndata: {}\n\n')

        with httpx.Client(base_url="https://api.example", transport=httpx.MockTransport(backend), headers={"Authorization": "Bearer test-token"}) as client:
            self.assertEqual(generate(client, "agent"), "Hello!")
        self.assertEqual([request.method for request in requests], ["POST", "POST", "DELETE"])
        self.assertTrue(all(request.headers["Authorization"] == "Bearer test-token" for request in requests))
        self.assertIn(b'"profile_id":"agent"', requests[0].content)
        self.assertIn(b"Reply with a short hello.", requests[1].content)

    def test_stream_failures_are_not_success(self):
        for stream in ['event: error\ndata: {"message":"failure"}\n\n', 'event: text\ndata: {"content":"partial"}\n\n']:
            requests = []

            def backend(request):
                requests.append(request)
                if request.url.path == "/api/sessions":
                    return httpx.Response(201, json={"session_id": "test-session"})
                return httpx.Response(200, text=stream)

            with httpx.Client(base_url="https://api.example", transport=httpx.MockTransport(backend)) as client:
                with self.assertRaises(HTTPException):
                    generate(client, "agent")
            self.assertEqual(requests[-1].method, "DELETE")

    def test_browser_never_receives_token(self):
        with TestClient(app) as browser, patch("client.settings", return_value={"API_URL": "https://api.example", "PROFILE_ID": "agent"}), patch("client.get_token", return_value="private-token"), patch("client.generate", return_value="Hello!"):
            response = browser.post("http://localhost/ping", headers={"X-External-Test": "1"})
            self.assertEqual(response.json(), {"text": "Hello!"})
            self.assertEqual(browser.post("http://localhost/ping").status_code, 403)
            self.assertEqual(browser.get("http://untrusted.example/").status_code, 400)


if __name__ == "__main__":
    unittest.main()