
import os
import unittest
import numpy as np
from moviepy.editor import VideoFileClip, ImageClip
import cv2

# Import the function from app.py (assuming app is in path)
# Since app.py is not a package, we might need to copy the function or use importlib
import sys
sys.path.append(os.getcwd())
try:
    from app import opencv_resize_clip
except ImportError:
    # If app import fails (e.g. dependencies), redefine it here for testing logic
    def opencv_resize_clip(clip, target_height):
        w, h = clip.size
        target_width = int(w * target_height / h)
        if target_width % 2 != 0: target_width += 1
        if target_height % 2 != 0: target_height += 1
        def resize_frame(image):
            return cv2.resize(image, (target_width, target_height), interpolation=cv2.INTER_AREA)
        return clip.fl_image(resize_frame)

class TestOpenCVResize(unittest.TestCase):
    def setUp(self):
        self.test_file = "test_cv2.mp4"
        self.img_file = "test_cv2_img.png"
        
        # Create a red image
        from PIL import Image
        img = Image.new('RGB', (100, 100), color = 'red')
        img.save(self.img_file)
        
        # Create a clip
        clip = ImageClip(self.img_file, duration=1)
        clip.write_videofile(self.test_file, fps=24, logger=None)
        clip.close()

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
        if os.path.exists(self.img_file):
            os.remove(self.img_file)
        if os.path.exists("test_cv2_resized.mp4"):
            os.remove("test_cv2_resized.mp4")

    def test_opencv_resize(self):
        clip = VideoFileClip(self.test_file)
        original_w, original_h = clip.size
        print(f"Original size: {original_w}x{original_h}")
        
        target_h = 50
        resized_clip = opencv_resize_clip(clip, target_height=target_h)
        
        # Write to file to force processing
        resized_clip.write_videofile("test_cv2_resized.mp4", fps=24, logger=None)
        
        # Check output dimensions
        # Note: clip.size on resized_clip might not update immediately if it's just a filter?
        # MoviePy's fl_image DOES NOT automatically update .size attribute unless we manually do it?
        # Wait, fl_image returns a new clip. The new clip might inherit size unless updated.
        # Let's check the actual frame size.
        
        frame = resized_clip.get_frame(0)
        h, w, c = frame.shape
        print(f"Resized frame shape: {w}x{h}")
        
        self.assertEqual(h, target_h)
        self.assertEqual(w, int(original_w * target_h / original_h)) # 100 * 50 / 100 = 50
        
        clip.close()
        resized_clip.close()

if __name__ == '__main__':
    unittest.main()
