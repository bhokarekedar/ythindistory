import os
import sys

# Anchor paths
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, base_dir)

from publishing.youtube_publisher import YouTubePublisher

print("=" * 60)
print("  ViralLoop YouTube Channel Authorization")
print("=" * 60)
print("\nOpening your browser to authorize your YouTube channel...")
print("If the browser does not open automatically, copy and paste the link shown below.\n")

publisher = YouTubePublisher()
res = publisher.authenticate_local(port=8088)

if res.get("connected"):
    print("\n" + "=" * 60)
    print(f"🎉 SUCCESS! Connected to YouTube Channel: {res.get('channel_title')}")
    print("=" * 60)
else:
    print(f"\n❌ Authorization incomplete: {res.get('message')}")

