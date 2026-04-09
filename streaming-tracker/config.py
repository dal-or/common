"""
Configuration for the streaming channel tracker.

Channels are loaded from channels.json. Each entry needs a "name" and a "url".
The URL can be:
  - A channel URL:  https://www.youtube.com/@Handle
  - A channel URL:  https://www.youtube.com/channel/UC...
  - A direct channel ID: UC...

On first run, channel IDs are resolved via the YouTube API and cached
back into channels.json so subsequent runs don't spend extra quota.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the same directory as this file, regardless of cwd
_base_dir = Path(__file__).resolve().parent
load_dotenv(_base_dir / ".env")

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
REPORTS_DIR = os.getenv("REPORTS_DIR", str(_base_dir / "reports"))
DB_PATH = os.getenv("DB_PATH", str(_base_dir / "streaming_tracker.db"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))
LIVE_SEARCH_INTERVAL = int(os.getenv("LIVE_SEARCH_INTERVAL", "300"))
CHANNELS_FILE = os.getenv("CHANNELS_FILE", str(_base_dir / "channels.json"))
