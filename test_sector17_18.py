
import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import json

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app

class TestSector1718(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    @patch('app.extractor_utils.process_query_to_prompt')
    @patch('app.obs_utils.upload_file')
    def test_sector17_submit_success(self, mock_upload, mock_process):
        # Setup mocks
        mock_process.return_value = "Generated Prompt Content"
        mock_upload.return_value = "http://obs.dimond.top/prompt.txt"

        # Make request
        response = self.app.post('/sector17_submit', data={'text': 'Test Query'})
        
        # Verify
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['url'], "http://obs.dimond.top/prompt.txt")
        self.assertEqual(data['content'], "Generated Prompt Content")

        # Check mock calls
        mock_process.assert_called_once()
        mock_upload.assert_called_once()

    @patch('app.extractor_utils.process_query_to_prompt')
    def test_sector17_submit_error(self, mock_process):
        # Setup mock to fail
        mock_process.return_value = "Error: Something went wrong"

        # Make request
        response = self.app.post('/sector17_submit', data={'text': 'Test Query'})
        
        # Verify
        self.assertEqual(response.status_code, 500)
        data = json.loads(response.data)
        self.assertEqual(data['error'], "Error: Something went wrong")

    @patch('app.requests.get')
    def test_sector18_get_prompt_success(self, mock_get):
        # Setup mock
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Prompt from OBS"
        mock_get.return_value = mock_response

        # Make request
        response = self.app.get('/sector18_get_prompt')
        
        # Verify
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['content'], "Prompt from OBS")

    @patch('app.requests.get')
    def test_sector18_get_prompt_failure(self, mock_get):
        # Setup mock
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        # Make request
        response = self.app.get('/sector18_get_prompt')
        
        # Verify
        self.assertEqual(response.status_code, 502)
        data = json.loads(response.data)
        self.assertTrue('Failed to fetch' in data['error'])

if __name__ == '__main__':
    unittest.main()
