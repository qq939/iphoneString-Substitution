
from moviepy.editor import VideoFileClip, VideoClip
import os

def test_subclip_existence():
    print("Checking VideoFileClip and subclip...")
    try:
        # Create a dummy video if not exists
        if not os.path.exists("test_video.mp4"):
            from moviepy.editor import ImageClip
            from PIL import Image
            import numpy as np
            img = Image.new('RGB', (100, 100), color = 'red')
            img.save('test_img.png')
            clip = ImageClip('test_img.png', duration=1)
            clip.write_videofile("test_video.mp4", fps=24)
            clip.close()

        clip = VideoFileClip("test_video.mp4")
        print(f"Clip type: {type(clip)}")
        print(f"Has subclip: {hasattr(clip, 'subclip')}")
        
        if hasattr(clip, 'subclip'):
            print(f"subclip method: {clip.subclip}")
            sub = clip.subclip(0, 0.5)
            print("subclip call success")
            sub.close()
        
        # Check fl_image result
        print("Checking fl_image result...")
        clip_resized = clip.fl_image(lambda x: x)
        print(f"Resized clip type: {type(clip_resized)}")
        print(f"Has subclip: {hasattr(clip_resized, 'subclip')}")
        
        if hasattr(clip_resized, 'subclip'):
             sub_resized = clip_resized.subclip(0, 0.5)
             print("subclip on resized clip success")
             sub_resized.close()

        clip.close()
        clip_resized.close()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_subclip_existence()
