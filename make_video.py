#!/usr/bin/env python3
"""Convenience root runner for English Shadowing Pipeline."""

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from backend.make_video import main

if __name__ == "__main__":
    main()
