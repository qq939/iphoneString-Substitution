import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import json

sys.path.append(os.getcwd())
import comfy_utils

class TestMultiServerStatus(unittest.TestCase):
    def setUp(self):
        self.original_server_list = comfy_utils.SERVER_LIST
        comfy_utils.SERVER_LIST = ["server1:8188", "server2:8188"]
        
    def tearDown(self):
        comfy_utils.SERVER_LIST = self.original_server_list

    @patch('urllib.request.urlopen')
    def test_check_status_found_on_second_server(self, mock_urlopen):
        # Setup:
        # Server 1: Network error (get_history)
        # Server 2: Found in history
        
        # We need to mock urlopen to raise error for server1 and return data for server2
        
        def side_effect(url, timeout=10):
            req_url = url.full_url if hasattr(url, 'full_url') else url
            if "server1" in req_url:
                raise Exception("Network error")
            elif "server2" in req_url and "history" in req_url:
                mock_resp = MagicMock()
                # Return history with success
                history_data = {
                    "prompt_id_123": {
                        "outputs": {
                            "9": {
                                "images": [{"filename": "out.png", "type": "output"}]
                            }
                        }
                    }
                }
                mock_resp.read.return_value = json.dumps(history_data).encode('utf-8')
                mock_resp.__enter__.return_value = mock_resp
                return mock_resp
            return MagicMock()

        mock_urlopen.side_effect = side_effect
        
        status, result = comfy_utils.check_status("prompt_id_123")
        self.assertEqual(status, "SUCCEEDED")
        self.assertEqual(result['filename'], "out.png")

    @patch('urllib.request.urlopen')
    def test_check_status_network_error_returns_pending(self, mock_urlopen):
        # Setup:
        # All servers raise Exception
        mock_urlopen.side_effect = Exception("Network error")
        
        status, result = comfy_utils.check_status("prompt_id_123")
        self.assertEqual(status, "PENDING")
        
    @patch('urllib.request.urlopen')
    def test_check_status_not_found_returns_failed(self, mock_urlopen):
        # Setup:
        # All servers return empty history and empty queue (Not Found)
        
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"{}" # Empty dict
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.side_effect = None
        mock_urlopen.return_value = mock_resp
        
        status, result = comfy_utils.check_status("prompt_id_123")
        self.assertEqual(status, "FAILED")

if __name__ == '__main__':
    unittest.main()
