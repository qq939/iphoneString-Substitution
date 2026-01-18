
import os
import unittest

class TestUIElements(unittest.TestCase):
    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.index_path = os.path.join(self.base_dir, 'templates', 'index.html')
        self.css_path = os.path.join(self.base_dir, 'static', 'css', 'style.css')

    def test_refresh_buttons_use_svg(self):
        """Verify that panel refresh buttons use SVG icons and no emoji remains"""
        with open(self.index_path, 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertNotIn('🔄', content)
            self.assertIn('class="inline-refresh-btn"', content)
            self.assertIn('onclick="refreshCharacter()"', content)
            self.assertIn('onclick="updateLatestVideo(true)"', content)
            self.assertIn('onclick="updateLatestAudio(true)"', content)
            self.assertGreaterEqual(content.count('class="inline-refresh-btn"'), 4)
            self.assertGreaterEqual(content.count('<svg'), 3)

    def test_character_video_plus_button_exists(self):
        with open(self.index_path, 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertIn('id="saveCharacterFromCurrentBtn"', content)
            self.assertIn('onclick="saveCharacterFromCurrentVideo()"', content)

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
            self.assertIn('.inline-refresh-btn', content)
            self.assertNotIn('#refresh-btn', content)

    def test_i2v_sectors_exist(self):
        with open(self.index_path, 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertIn('id="i2vText9"', content)
            self.assertIn('id="i2vText10"', content)
            self.assertIn('id="i2vText11"', content)
            self.assertIn('id="i2vText12"', content)

            self.assertIn('onclick="submitI2V(9)"', content)
            self.assertIn('onclick="submitI2V(10)"', content)
            self.assertIn('onclick="submitI2V(11)"', content)
            self.assertIn('onclick="submitI2V(12)"', content)

            self.assertIn('id="i2vStatus9"', content)
            self.assertIn('id="i2vStatus10"', content)
            self.assertIn('id="i2vStatus11"', content)
            self.assertIn('id="i2vStatus12"', content)

            self.assertNotIn('id="i2vSubmitBtn"', content)

    def test_transition_sectors_exist(self):
        with open(self.index_path, 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertIn('id="transitionForm13"', content)
            self.assertIn('id="transitionForm14"', content)
            self.assertIn('id="transitionForm15"', content)
            self.assertIn('id="transitionForm16"', content)
            self.assertIn('id="transitionStatus13"', content)
            self.assertIn('id="transitionStatus14"', content)
            self.assertIn('id="transitionStatus15"', content)
            self.assertIn('id="transitionStatus16"', content)

if __name__ == '__main__':
    unittest.main()
