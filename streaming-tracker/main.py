#!/usr/bin/env python3
"""
Argentine YouTube Streaming Channel Tracker

Tracks viewer counts for live streaming channels (Luzu TV, Olga, Blender, etc.)
every minute, stores data in SQLite, and generates hourly reports with graphs.

Usage:
    python main.py              # Run the tracker (continuous)
    python main.py --report     # Generate a one-off report from existing data
    python main.py --status     # Show current status of tracked streams
"""

import argparse
import logging
import signal
import sys
import time
from datetime import datetime

import schedule

import database as db
import tracker
import reporter
import channels as ch
import youtube_api as yt
from config import YOUTUBE_API_KEYS, POLL_INTERVAL, LIVE_SEARCH_INTERVAL

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("tracker.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# Track the current day to reset exhausted keys at midnight
_current_day = None


def handle_shutdown(signum, frame):
    logger.info("Shutting down gracefully...")
    sys.exit(0)


def _check_daily_reset():
    """Reset exhausted API keys at the start of each new day."""
    global _current_day
    today = datetime.utcnow().date()
    if _current_day is not None and today != _current_day:
        logger.info("New day detected — resetting API key quota status.")
        yt.reset_exhausted_keys()
    _current_day = today


def run_tracker():
    """Main tracker loop."""
    if not YOUTUBE_API_KEYS or YOUTUBE_API_KEYS == ["your_api_key_here"]:
        logger.error(
            "YouTube API key not configured. "
            "Copy .env.example to .env and set YOUTUBE_API_KEY "
            "or YOUTUBE_API_KEYS (comma-separated for multiple keys)."
        )
        sys.exit(1)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # Initialize API key pool
    yt.init_api_pool(YOUTUBE_API_KEYS)

    db.init_db()

    # Resolve channel URLs to IDs (reads channels.json)
    resolved = ch.resolve_channels(yt.resolve_handle_to_channel_id)
    if not resolved:
        logger.error(
            "No channels could be resolved. Check channels.json and your API key."
        )
        sys.exit(1)
    tracker.init_channels(resolved)

    logger.info("=" * 50)
    logger.info("Streaming Channel Tracker - Starting")
    logger.info(f"  API keys: {len(YOUTUBE_API_KEYS)}")
    logger.info(f"  Channels: {len(resolved)}")
    logger.info(f"  Poll interval: {POLL_INTERVAL}s")
    logger.info(f"  Live search interval: {LIVE_SEARCH_INTERVAL}s")
    logger.info("=" * 50)

    # Initialize day tracking for key reset
    _check_daily_reset()

    # Run discovery immediately on start
    tracker.discover_live_streams()
    tracker.poll_viewer_counts()

    # Schedule tasks
    schedule.every(POLL_INTERVAL).seconds.do(tracker.poll_viewer_counts)
    schedule.every(LIVE_SEARCH_INTERVAL).seconds.do(tracker.discover_live_streams)
    schedule.every().hour.at(":00").do(reporter.generate_hourly_report)
    schedule.every(5).minutes.do(_check_daily_reset)

    logger.info("Scheduler started. Press Ctrl+C to stop.")

    while True:
        schedule.run_pending()
        time.sleep(1)


def show_status():
    """Show current status of tracked streams."""
    db.init_db()
    streams = db.get_active_streams()

    if not streams:
        print("No active streams being tracked.")
        print("Run the tracker first: python main.py")
        return

    print(f"\nActive streams: {len(streams)}\n")
    for s in streams:
        current = s.get("current_viewers") or 0
        peak = s.get("peak_viewers") or 0
        print(f"  {s['channel_name']}: {current:,} viewers (peak: {peak:,})")
        print(f"    {s['title']}")
        print(f"    https://youtube.com/watch?v={s['video_id']}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Track Argentine YouTube streaming channels"
    )
    parser.add_argument(
        "--report", action="store_true",
        help="Generate a one-off report from existing data"
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Show current status of tracked streams"
    )
    args = parser.parse_args()

    if args.report:
        db.init_db()
        reporter.generate_hourly_report()
    elif args.status:
        show_status()
    else:
        run_tracker()


if __name__ == "__main__":
    main()
