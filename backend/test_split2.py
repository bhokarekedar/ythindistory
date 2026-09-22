import ffmpeg
in_file = ffmpeg.input('dummy.mp4')
splits = in_file.split()
print("splits type:", type(splits))
print("split 0:", splits[0])
print("split 1:", splits[1])
print("split 2:", splits[2])

# Or maybe it's just in_file.split(**{'outputs': 3}) ?
try:
    s = in_file.split(**{'outputs': 3})
    print(s[0], s[1], s[2])
except Exception as e:
    print(e)
    
