"""
Configuration for the streaming channel tracker.

Channels are defined here. To add a new channel, add its name and
YouTube channel ID to the CHANNELS dict.
"""

import os
from dotenv import load_dotenv

load_dotenv()

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
REPORTS_DIR = os.getenv("REPORTS_DIR", "./reports")
DB_PATH = os.getenv("DB_PATH", "./streaming_tracker.db")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))
LIVE_SEARCH_INTERVAL = int(os.getenv("LIVE_SEARCH_INTERVAL", "300"))

# Argentine streaming channels
# Format: "Display Name": "YouTube Channel ID"
# To find a channel ID: go to the channel page -> view source -> search "channelId"
# or use https://www.youtube.com/@ChannelHandle and the API to resolve it.
CHANNELS = {
    "Luzu TV": "UCv4RMih7kQ4gMPEqC9GiynA",
    "Olga": "UCTEQCJWqLOYEeLsi3FXrFsQ",
    "Blender": "UCsUP-hEJVFr__ka3ySKzqKg",
    "Gelatina": "UChvC-yLmKPV8syP4L-p71MQ",
    "Bondi Live": "UC7MBJm1I5M-bNmDE11G8xHw",
    "Carajo": "UCYM-scYr_BmMGOwPeqEh7ow",
    "La Casa Streaming": "UC0u3cDdKBjkNF8IFjdCF4QA",
    "Vorterix": "UCvCTWHCbBC0b31JxnZSZzTg",
}
