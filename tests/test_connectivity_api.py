import unittest
import requests
import json
import time
import threading
import sys
import os
import unittest.mock

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, COMFY_STATUS
import comfy_utils

class TestConnectivityAPI(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_comfy_status_endpoint(self):
        """Test /comfy_status endpoint structure"""
        response = self.app.get('/comfy_status')
        data = json.loads(response.data)
        
        self.assertIn('status', data)
        self.assertIn('ip', data)
        self.assertIn('last_checked', data)

    @unittest.mock.patch('comfy_utils.client.find_fastest_server')
    def test_retest_connection(self, mock_find):
        """Test /retest_connection endpoint"""
        # Mock find_fastest_server to avoid actual network call delay or failure
        mock_find.return_value = True
        
        response = self.app.post('/retest_connection')
        data = json.loads(response.data)
        
        self.assertIn('status', data)
        if data['status'] == 'success':
            self.assertTrue(data['connected'])
            self.assertIn('ip', data)

if __name__ == '__main__':
    unittest.main()
