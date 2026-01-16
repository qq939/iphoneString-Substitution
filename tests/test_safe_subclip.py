
import os
import unittest
import sys
sys.path.append(os.getcwd()) # Add current dir to path to import app

from moviepy.editor import VideoFileClip, ImageClip
from app import safe_subclip, opencv_resize_clip

class TestSafeSubclip(unittest.TestCase):
    def setUp(self):
        self.test_file = "test_subclip.mp4"
        self.img_file = "test_subclip_img.png"
        
        from PIL import Image
        img = Image.new('RGB', (100, 100), color = 'red')
        img.save(self.img_file)
        
        clip = ImageClip(self.img_file, duration=2)
        clip.write_videofile(self.test_file, fps=24, logger=None)
        clip.close()

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
        if os.path.exists(self.img_file):
            os.remove(self.img_file)

    def test_safe_subclip_on_fileclip(self):
        clip = VideoFileClip(self.test_file)
        sub = safe_subclip(clip, 0, 1)
        self.assertIsNotNone(sub)
        self.assertEqual(sub.duration, 1)
        sub.close()
        clip.close()

    def test_safe_subclip_on_resized_clip(self):
        clip = VideoFileClip(self.test_file)
        resized = opencv_resize_clip(clip, 50)
        sub = safe_subclip(resized, 0, 1)
        self.assertIsNotNone(sub)
        self.assertEqual(sub.duration, 1)
        
        # Verify it's resized
        frame = sub.get_frame(0)
        self.assertEqual(frame.shape[0], 50)
        
        sub.close()
        resized.close()
        clip.close()

if __name__ == '__main__':
    unittest.main()
