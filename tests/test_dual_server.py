import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import time

# Add parent directory to path to import comfy_utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import comfy_utils

class TestDualServer(unittest.TestCase):
    def setUp(self):
        # Reset the client for each test
        self.client = comfy_utils.ComfyUIClient()
        # Ensure we start with no server selected
        self.client.base_url = None
        self.client.server_address = None

    @patch('requests.get')
    def test_find_fastest_server_first_available(self, mock_get):
        """Test that it picks the first available server"""
        # Setup mock to fail for first server and succeed for second
        def side_effect(url, *args, **kwargs):
            if "192.168.0.210" in url:
                raise Exception("Connection failed")
            elif "192.168.50.210" in url:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                return mock_resp
            return MagicMock(status_code=404)
            
        mock_get.side_effect = side_effect
        
        # Reset server list order to ensure we test what we think we are testing
        # But find_fastest_server runs concurrently, so order in list doesn't matter for "first available" logic
        # strictly speaking, but it matters for which one gets submitted first.
        
        result = self.client.find_fastest_server()
        
        self.assertTrue(result)
        self.assertIn("192.168.50.210", self.client.base_url)
        self.assertNotIn("192.168.0.210", self.client.base_url)

    @patch('requests.get')
    def test_find_fastest_server_concurrent_speed(self, mock_get):
        """Test that it picks the fastest responding server"""
        # We need to simulate delay. 
        # Since ThreadPoolExecutor is used, we can't easily control exact timing with simple side_effect
        # without sleep, which makes test slow.
        # But we can assume that if one raises exception immediately and other sleeps 0.1s, the exception one won't be picked.
        # Wait, if one raises exception, it's ignored. 
        # If both succeed, the first one to return should be picked.
        
        def side_effect(url, *args, **kwargs):
            if "192.168.0.210" in url:
                time.sleep(0.2) # Slower
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                return mock_resp
            elif "192.168.50.210" in url:
                time.sleep(0.01) # Faster
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                return mock_resp
            return MagicMock(status_code=404)
            
        mock_get.side_effect = side_effect
        
        result = self.client.find_fastest_server()
        
        self.assertTrue(result)
        # Should pick the faster one (192.168.50.210)
        self.assertIn("192.168.50.210", self.client.base_url)

    @patch('requests.get')
    def test_check_connection_switch(self, mock_get):
        """Test that check_connection switches server if current fails"""
        # First, set a server manually
        self.client._set_server_address("192.168.0.210:7860")
        
        # Mock first call (check_connection) to fail
        # Mock subsequent calls (find_fastest_server) to succeed with other server
        
        call_count = 0
        def side_effect(url, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            # First call: check existing connection (192.168.0.210) -> Fail
            if call_count == 1:
                if "192.168.0.210" in url:
                    raise Exception("Connection lost")
            
            # Subsequent calls: find_fastest_server -> 192.168.50.210 succeeds
            if "192.168.50.210" in url:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                return mock_resp
            
            # 192.168.0.210 continues to fail
            if "192.168.0.210" in url:
                raise Exception("Still down")
                
            return MagicMock(status_code=404)
            
        mock_get.side_effect = side_effect
        
        # This should trigger a switch
        result = self.client.check_connection()
        
        self.assertTrue(result)
        # Should have switched to the other server
        self.assertIn("192.168.50.210", self.client.base_url)

if __name__ == '__main__':
    unittest.main()
