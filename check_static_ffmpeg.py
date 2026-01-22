
import shutil
import static_ffmpeg
import sys

print("Adding paths...")
static_ffmpeg.add_paths()
print(f"ffmpeg: {shutil.which('ffmpeg')}")
print(f"ffprobe: {shutil.which('ffprobe')}")
