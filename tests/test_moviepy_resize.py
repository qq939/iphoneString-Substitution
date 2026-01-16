
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
        
        # Simulate import of explicit_resize
        try:
            from moviepy.video.fx.resize import resize as explicit_resize
        except ImportError:
            try:
                from moviepy.video.fx.all import resize as explicit_resize
            except ImportError:
                explicit_resize = None

        try:
            # Replicate the UPDATED logic in app.py
            try:
                if hasattr(vfx, 'resize'):
                    clip_resized = vfx.resize(clip, height=50)
                    print("Resized using vfx.resize")
                elif hasattr(clip, 'resize'):
                    clip_resized = clip.resize(height=50)
                    print("Resized using clip.resize")
                elif explicit_resize:
                    clip_resized = explicit_resize(clip, height=50)
                    print("Resized using explicit_resize")
                else:
                    raise Exception("Cannot find resize function")
            except AttributeError:
                if hasattr(clip, 'resize'):
                    clip_resized = clip.resize(height=50)
                    print("Resized using clip.resize (fallback)")
                elif explicit_resize:
                    clip_resized = explicit_resize(clip, height=50)
                    print("Resized using explicit_resize (fallback)")
                else:
                    raise Exception("AttributeError during resize and no fallback available")
            
            self.assertIsNotNone(clip_resized)
            self.assertEqual(clip_resized.h, 50)
            clip_resized.close()
            
        finally:
            clip.close()

if __name__ == '__main__':
    unittest.main()
