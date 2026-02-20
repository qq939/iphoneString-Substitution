
import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, SECTOR_TASKS


class TestSector1718(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    @patch("app.run_sector17_task")
    def test_sector17_submit_starts_task(self, mock_run_task):
        response = self.app.post("/sector17_submit", data={"text": "Test Query"})

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "processing")
        self.assertIn("task_id", data)

        task_id = data["task_id"]
        self.assertIn(task_id, SECTOR_TASKS)
        self.assertEqual(SECTOR_TASKS[task_id]["status"], "processing")

        mock_run_task.assert_called_once()

    def test_sector17_submit_missing_text(self):
        response = self.app.post("/sector17_submit", data={"text": ""})
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertIn("error", data)

    @patch("app.requests.get")
    def test_sector18_get_prompt_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = "Prompt from OBS".encode("utf-8")
        mock_get.return_value = mock_response

        response = self.app.get("/sector18_get_prompt")

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["content"], "Prompt from OBS")

    @patch("app.requests.get")
    def test_sector18_get_prompt_failure(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.content = b""
        mock_get.return_value = mock_response

        response = self.app.get("/sector18_get_prompt")

        self.assertEqual(response.status_code, 502)
        data = json.loads(response.data)
        self.assertIn("Failed to fetch", data["error"])


if __name__ == "__main__":
    unittest.main()
