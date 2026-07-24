#!/usr/bin/env python3
"""Launch the Vesper 2.0 Tkinter dashboard."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from vesper.dashboard.app import main

if __name__ == "__main__":
    main()
