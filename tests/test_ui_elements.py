
import os
import unittest
import signal
from contextlib import contextmanager


class UITimeoutError(Exception):
    pass


def _timeout_handler(signum, frame):
    raise UITimeoutError("ui elements test timeout")


@contextmanager
def timeout_scope(seconds=5):
    original_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, original_handler)

class TestUIElements(unittest.TestCase):
    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.index_path = os.path.join(self.base_dir, 'templates', 'index.html')
        self.css_path = os.path.join(self.base_dir, 'static', 'css', 'style.css')

    def test_refresh_buttons_use_svg(self):
        """Verify that panel refresh buttons use SVG icons and no emoji remains"""
        with timeout_scope(5):
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
        with timeout_scope(5):
            with open(self.index_path, 'r', encoding='utf-8') as f:
                content = f.read()
                self.assertIn('id="saveCharacterFromCurrentBtn"', content)
                self.assertIn('onclick="saveCharacterFromCurrentVideo()"', content)

    def test_css_rules_exist(self):
        """Verify that new CSS rules for transparent controls exist"""
        with timeout_scope(5):
            with open(self.css_path, 'r', encoding='utf-8') as f:
                content = f.read()
                self.assertIn('::file-selector-button', content)
                self.assertIn('background: transparent', content)
                self.assertIn('input[type="radio"]', content)
                self.assertIn('input[type="checkbox"]', content)
                self.assertIn('appearance: none', content)
                self.assertIn('.inline-refresh-btn', content)
                self.assertNotIn('#refresh-btn', content)

    def test_i2v_sectors_exist(self):
        with timeout_scope(5):
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
        with timeout_scope(5):
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

    def test_audio_emotions_and_button_order(self):
        with timeout_scope(5):
            with open(self.index_path, 'r', encoding='utf-8') as f:
                content = f.read()
                self.assertIn('id="audioUploadForm"', content)
                self.assertIn('value="Happy"', content)
                self.assertIn('value="Angry"', content)
                self.assertIn('value="Sad"', content)
                self.assertIn('value="Fear"', content)
                self.assertNotIn('value="Hate"', content)
                self.assertNotIn('value="Low"', content)
                self.assertNotIn('value="Surprise"', content)
                self.assertNotIn('value="Neutral"', content)

                file_idx = content.find('name="file"')
                btn_idx = content.find('id="audioUploadBtn"')
                self.assertNotEqual(file_idx, -1)
                self.assertNotEqual(btn_idx, -1)
                self.assertLess(file_idx, btn_idx)

    def test_button_and_text_input_styles(self):
        with timeout_scope(5):
            with open(self.css_path, 'r', encoding='utf-8') as f:
                content = f.read()
                self.assertIn('input[type="text"] {', content)
                self.assertIn('width: 100%;', content)
                self.assertIn('button {', content)
                self.assertIn('background: transparent;', content)
                self.assertIn('.action-btn {', content)
                self.assertIn('background: transparent;', content)
                self.assertIn('.control-btn {', content)
                self.assertIn('background: transparent;', content)

if __name__ == '__main__':
    unittest.main()
