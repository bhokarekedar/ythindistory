from PIL import Image

img = Image.open("test_snap.jpg")
# The logo is at 50,50. If we crop a small area at 50,50, it shouldn't be solid color if logo is there.
# But it's easier to just check if watermark works by modifying the script to output info.
