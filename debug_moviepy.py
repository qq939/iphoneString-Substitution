
try:
    from moviepy.editor import VideoFileClip, ImageClip
    print("Imported from moviepy.editor")
except ImportError:
    print("Failed to import from moviepy.editor")

import os

def test_resize():
    # Create a dummy image
    from PIL import Image
    import numpy as np
    
    img = Image.new('RGB', (100, 100), color = 'red')
    img.save('test_img.png')
    
    try:
        clip = ImageClip('test_img.png', duration=1)
        print(f"Clip created: {clip}")
        
        if hasattr(clip, 'resize'):
            print("Clip has resize attribute")
            clip.resize(height=50)
            print("Resize successful")
        else:
            print("Clip DOES NOT have resize attribute")
            
            # Try to find where resize is
            import moviepy.video.fx.all as vfx
            print(f"Imported vfx: {vfx}")
            if hasattr(clip, 'resize'):
                print("Clip has resize attribute AFTER importing vfx")
            else:
                print("Clip STILL DOES NOT have resize attribute")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if os.path.exists('test_img.png'):
            os.remove('test_img.png')

if __name__ == "__main__":
    test_resize()
