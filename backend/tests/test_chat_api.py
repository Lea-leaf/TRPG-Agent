import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class _FakeSessionService:
    def __init__(self):
        self.calls = []

    def process_turn(self, message: str, session_id: str | None = None) -> dict:
        self.calls.append({"message": message, "session_id": session_id})
        return {
            "reply": f"echo:{message}",
            "plan": None,
            "session_id": session_id or "generated-session",
        }


class ChatApiTests(unittest.TestCase):
    def test_chat_endpoint_returns_service_result(self):
        fake = _FakeSessionService()
        with patch("app.api.chat.CHAT_SESSION_SERVICE", fake):
            client = TestClient(app)
            resp = client.post(
                "/api/chat",
                json={"message": "你好", "session_id": "demo-1"},
            )

        self.assertEqual(200, resp.status_code)
        data = resp.json()
        self.assertEqual("echo:你好", data["reply"])
        self.assertEqual("demo-1", data["session_id"])
        self.assertIn("plan", data)
        self.assertEqual("你好", fake.calls[0]["message"])
        self.assertEqual("demo-1", fake.calls[0]["session_id"])

    def test_chat_endpoint_accepts_missing_session_id(self):
        fake = _FakeSessionService()
        with patch("app.api.chat.CHAT_SESSION_SERVICE", fake):
            client = TestClient(app)
            resp = client.post("/api/chat", json={"message": "hello"})

        self.assertEqual(200, resp.status_code)
        data = resp.json()
        self.assertEqual("generated-session", data["session_id"])


if __name__ == "__main__":
    unittest.main()
