import unittest
import requests
import json
import time
import threading
import sys
import os

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

    def test_retest_connection(self):
        """Test /retest_connection endpoint"""
        # Mock find_fastest_server to avoid actual network call delay or failure
        # But for integration test we might want real call. 
        # Given the environment, let's try real call first, if it fails (offline), it should still return valid JSON.
        
        response = self.app.post('/retest_connection')
        data = json.loads(response.data)
        
        self.assertIn('status', data)
        if data['status'] == 'success':
            self.assertTrue(data['connected'])
            self.assertIn('ip', data)
        else:
            # If it fails, it might return error status if exception raised
            pass

if __name__ == '__main__':
    unittest.main()
