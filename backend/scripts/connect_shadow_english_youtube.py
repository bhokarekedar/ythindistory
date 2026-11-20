#!/usr/bin/env python3
"""Interactive YouTube Channel Connection Script for Shadow English Daily.

Authorizes the YouTube account for https://www.youtube.com/@ShadowEnglishDaily-d4z
and stores the token into backend/data/youtube_token_shadow_english.json
without touching existing tokens for other channels.
"""

import os
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from shadowing_pipeline.core.youtube_uploader import authenticate_channel, get_channel_status

def main():
    print("=" * 70)
    print("  YouTube Channel Authorization for Shadow English Daily")
    print("  Target Channel: https://www.youtube.com/@ShadowEnglishDaily-d4z")
    print("=" * 70)
    print("\n👉 A Google login page will open in your browser.")
    print("👉 IMPORTANT: When prompted, select the Google Account / Brand Account for:")
    print("   'Shadow English Daily' (@ShadowEnglishDaily-d4z)\n")
    print("Opening browser (local port 8089)...")

    token_file = backend_dir / "data" / "youtube_token_shadow_english.json"
    secrets_file = backend_dir / "data" / "client_secrets.json"

    if not secrets_file.exists():
        print(f"\n❌ Error: Google OAuth client secrets file not found at:\n   {secrets_file}")
        print("Please ensure client_secrets.json is present in backend/data/.")
        sys.exit(1)

    result = authenticate_channel(
        token_path=str(token_file),
        client_secrets_path=str(secrets_file),
        port=8089
    )

    if result.get("success") and result.get("connected"):
        print("\n" + "=" * 70)
        print("🎉 SUCCESS! Connected to YouTube Channel:")
        print(f"   Channel Title: {result.get('channel_title')}")
        print(f"   Channel Handle: {result.get('custom_url')}")
        print(f"   Channel ID:    {result.get('channel_id')}")
        print(f"   Token Saved:   {result.get('token_file')}")
        if result.get("is_target_channel"):
            print("   ✅ MATCHED: Connected directly to @ShadowEnglishDaily-d4z!")
        else:
            print(f"   ⚠️ NOTE: Channel handle is '{result.get('custom_url')}'. Ensure this is your desired channel.")
        print("=" * 70)
    else:
        print(f"\n❌ Authorization incomplete or failed:")
        print(f"   {result.get('message')}")
        sys.exit(1)

if __name__ == "__main__":
    main()

