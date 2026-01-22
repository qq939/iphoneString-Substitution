
import os
import sys
try:
    import imageio_ffmpeg
    print(f"ffmpeg exe: {imageio_ffmpeg.get_ffmpeg_exe()}")
except ImportError:
    print("imageio_ffmpeg not installed")

# Check for ffprobe
import shutil
print(f"ffmpeg in path: {shutil.which('ffmpeg')}")
print(f"ffprobe in path: {shutil.which('ffprobe')}")
