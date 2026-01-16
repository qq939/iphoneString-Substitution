
import os
import unittest

class TestUIElements(unittest.TestCase):
    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.index_path = os.path.join(self.base_dir, 'templates', 'index.html')
        self.css_path = os.path.join(self.base_dir, 'static', 'css', 'style.css')

    def test_refresh_button_exists(self):
        """Verify that the refresh button with SVG icon exists in index.html"""
        with open(self.index_path, 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertIn('id="refresh-btn"', content)
            self.assertIn('<svg', content)
            self.assertIn('onclick="location.reload()"', content)

    def test_css_rules_exist(self):
        """Verify that new CSS rules for transparent controls exist"""
        with open(self.css_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # Check for file input button styling
            self.assertIn('::file-selector-button', content)
            self.assertIn('background: transparent', content)
            
            # Check for radio/checkbox styling
            self.assertIn('input[type="radio"]', content)
            self.assertIn('input[type="checkbox"]', content)
            self.assertIn('appearance: none', content)
            self.assertIn('#refresh-btn', content)

if __name__ == '__main__':
    unittest.main()
