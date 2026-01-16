import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from comfy_utils import ComfyUIClient

class TestComfyUIClient(unittest.TestCase):
    def setUp(self):
        self.client = ComfyUIClient(server_address="dimond.top:7860")

    @patch('requests.get')
    def test_check_connection(self, mock_get):
        mock_get.return_value.status_code = 200
        self.assertTrue(self.client.check_connection())
        mock_get.assert_called_with(
            "http://dimond.top:7860/object_info",
            timeout=5,
            headers={'User-Agent': 'Mozilla/5.0'}
        )

    @patch('urllib.request.urlopen')
    def test_queue_prompt(self, mock_urlopen):
        # Mock response
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"prompt_id": "12345"}'
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        prompt_id = self.client.queue_prompt({})
        self.assertEqual(prompt_id, "12345")
        
        # Verify call args
        args, kwargs = mock_urlopen.call_args
        req = args[0]
        self.assertEqual(req.full_url, "http://dimond.top:7860/prompt")

    @patch('urllib.request.urlopen')
    def test_get_history(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"12345": {"outputs": {}}}'
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        history = self.client.get_history("12345")
        self.assertIn("12345", history)
        
        args, kwargs = mock_urlopen.call_args
        self.assertEqual(args[0], "http://dimond.top:7860/history/12345")

    @patch('requests.post')
    def test_upload_file(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"name": "test.png"}
        
        # Create dummy file
        with open("test_upload.png", "w") as f:
            f.write("dummy")
            
        try:
            res = self.client.upload_file("test_upload.png")
            self.assertEqual(res["name"], "test.png")
            
            args, kwargs = mock_post.call_args
            self.assertEqual(args[0], "http://dimond.top:7860/upload/image")
        finally:
            if os.path.exists("test_upload.png"):
                os.remove("test_upload.png")

if __name__ == '__main__':
    unittest.main()
