import ffmpeg
in_file = ffmpeg.input('dummy.mp4')
try:
    print(in_file.split(outputs=3))
except Exception as e:
    print("split(outputs=3) error:", e)

try:
    print(in_file.filter_multi_output('split'))
except Exception as e:
    print("filter_multi_output error:", e)
