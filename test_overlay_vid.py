import ffmpeg
import os

video_path = "/Users/kedarbhokare/Desktop/code/ytstoryhindiautomation/backend/output/5c5ed069_final.mp4"
watermark_path = "/Users/kedarbhokare/Desktop/code/ytstoryhindiautomation/backend/intro/watermark.png"
output_path = "test_vid.mp4"

if os.path.exists(output_path):
    os.remove(output_path)

try:
    vid = ffmpeg.input(video_path, t=2).video
    vid = vid.filter("scale", 1280, 720).filter("setsar", 1)

    wm = ffmpeg.input(watermark_path, loop=1).filter('scale', 200, -1)
    
    out_stream = ffmpeg.overlay(vid, wm, x=50, y=50, shortest=1)
    out_stream = out_stream.output(output_path, vcodec='libx264')
    ffmpeg.run(out_stream, overwrite_output=True, capture_stdout=True, capture_stderr=True)
    print("Success with loop")
except ffmpeg.Error as e:
    print(e.stderr.decode('utf8'))
