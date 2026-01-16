
import os
import unittest
from moviepy.editor import VideoFileClip, ImageClip
import moviepy.video.fx.all as vfx

class TestMoviePyResize(unittest.TestCase):
    def setUp(self):
        # Create a dummy video file
        self.test_file = "test_video.mp4"
        
        # Create a simple image
        from PIL import Image
        import numpy as np
        img = Image.new('RGB', (100, 100), color = 'red')
        img.save('test_img.png')
        
        clip = ImageClip('test_img.png', duration=1)
        clip.write_videofile(self.test_file, fps=24, logger=None)
        clip.close()

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
        if os.path.exists('test_img.png'):
            os.remove('test_img.png')

    def test_resize_logic(self):
        clip = VideoFileClip(self.test_file)
        
        try:
            # Replicate the logic in app.py
            try:
                clip_resized = vfx.resize(clip, height=50)
                print("Resized using vfx.resize")
            except AttributeError:
                if hasattr(clip, 'resize'):
                    clip_resized = clip.resize(height=50)
                    print("Resized using clip.resize")
                else:
                    if hasattr(vfx, 'resize'):
                        clip_resized = vfx.resize(clip, height=50)
                        print("Resized using vfx.resize (fallback)")
                    else:
                        raise Exception("Cannot find resize function in moviepy")
            
            self.assertIsNotNone(clip_resized)
            self.assertEqual(clip_resized.h, 50)
            clip_resized.close()
            
        finally:
            clip.close()

if __name__ == '__main__':
    unittest.main()
