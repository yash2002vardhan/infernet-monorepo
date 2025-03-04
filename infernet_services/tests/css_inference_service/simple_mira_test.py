"""
Simple test for Mira Network integration.
This script tests the Mira Network integration by making direct API calls.
"""

import unittest
import os
import sys
from pathlib import Path
import json
import requests

# Add the project root to the Python path
project_root = str(Path(__file__).parent.parent.parent.parent)
if project_root not in sys.path:
    sys.path.append(project_root)

# Use the API key from conftest.py
MIRANETWORK_API_KEY = "sk-mira-34a4ecb272fa1ee16ab63ec4e6563b145f0418d2bf0aaed3"

class TestMiraNetworkAPI(unittest.TestCase):
    """Test class for Mira Network API integration"""

    def test_mira_network_api_direct(self):
        """Test Mira Network API directly without using the css_mux function"""
        # Define the API endpoint
        url = "https://api.mira.network/v1/chat/completions"
        
        # Define the headers
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {MIRANETWORK_API_KEY}"
        }
        
        # Define the payload
        payload = {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "user",
                    "content": "Explain quantum computing in one paragraph."
                }
            ],
            "temperature": 0.7,
            "max_tokens": 100
        }
        
        # Make the API call
        response = requests.post(url, headers=headers, json=payload)
        
        # Print the response for debugging
        print(f"Status code: {response.status_code}")
        print(f"Response: {response.text}")
        
        # Verify the response
        self.assertEqual(response.status_code, 200)
        response_json = response.json()
        self.assertIn("choices", response_json)
        self.assertGreater(len(response_json["choices"]), 0)
        self.assertIn("message", response_json["choices"][0])
        self.assertIn("content", response_json["choices"][0]["message"])
        self.assertGreater(len(response_json["choices"][0]["message"]["content"]), 0)

if __name__ == "__main__":
    unittest.main() 
