"""
Core tracker logic.

Two loops run at different intervals:
1. discover_live_streams (every LIVE_SEARCH_INTERVAL seconds):
   - For each channel, searches YouTube for active live streams.
   - Registers new streams in the database.
   - Detects streams that ended (were tracked but no longer live).

2. poll_viewer_counts (every POLL_INTERVAL seconds):
   - For all currently tracked live streams, fetches concurrent viewers.
   - Records a snapshot in the database.
"""

import logging
from datetime import datetime, timedelta

import database as db
import youtube_api as yt
from config import CHANNELS

logger = logging.getLogger(__name__)

# In-memory cache: channel_name -> {video_id: stream_id}
_active_streams: dict[str, dict[str, int]] = {}


def discover_live_streams():
    """
    Search each channel for live streams. Update the active streams cache.
    This is the expensive operation (100 quota units per channel).
    """
    logger.info("Discovering live streams...")
    all_live_video_ids = set()

    for channel_name, channel_id in CHANNELS.items():
        try:
            live_results = yt.search_live_streams(channel_id)
        except Exception as e:
            logger.error(f"Error searching {channel_name}: {e}")
            continue

        current_video_ids = set()
        for result in live_results:
            video_id = result["video_id"]
            title = result["title"]
            current_video_ids.add(video_id)
            all_live_video_ids.add(video_id)

            # Register in DB if new
            if channel_name not in _active_streams:
                _active_streams[channel_name] = {}

            if video_id not in _active_streams[channel_name]:
                # Get start time from video details
                details = yt.get_video_details([video_id])
                started_at = None
                if details:
                    started_at = details[0].get("actual_start_time")

                stream_id = db.upsert_stream(
                    channel_name=channel_name,
                    channel_id=channel_id,
                    video_id=video_id,
                    title=title,
                    started_at=started_at,
                )
                _active_streams[channel_name][video_id] = stream_id
                logger.info(
                    f"New live stream: {channel_name} - '{title}' "
                    f"(video_id={video_id}, stream_id={stream_id})"
                )

        # Check if any previously tracked streams for this channel have ended
        if channel_name in _active_streams:
            ended = set(_active_streams[channel_name].keys()) - current_video_ids
            for video_id in ended:
                # Double-check via videos.list before marking as ended
                # (search can be slightly delayed)
                if not yt.check_video_still_live(video_id):
                    logger.info(
                        f"Stream ended: {channel_name} - video_id={video_id}"
                    )
                    db.mark_stream_ended(video_id)
                    del _active_streams[channel_name][video_id]

    total_active = sum(len(v) for v in _active_streams.values())
    logger.info(f"Discovery complete. {total_active} active streams tracked.")


def poll_viewer_counts():
    """
    For all tracked live streams, fetch and record current viewer counts.
    This is cheap (1 quota unit per batch of up to 50 videos).
    """
    # Collect all active video IDs
    video_to_info: dict[str, tuple[str, int]] = {}  # video_id -> (channel_name, stream_id)
    for channel_name, streams in _active_streams.items():
        for video_id, stream_id in streams.items():
            video_to_info[video_id] = (channel_name, stream_id)

    if not video_to_info:
        logger.debug("No active streams to poll.")
        return

    video_ids = list(video_to_info.keys())
    details = yt.get_video_details(video_ids)

    now = datetime.utcnow().strftime("%H:%M:%S")
    for detail in details:
        video_id = detail["video_id"]
        if video_id not in video_to_info:
            continue

        channel_name, stream_id = video_to_info[video_id]

        if detail["is_live"]:
            viewers = detail["concurrent_viewers"]
            db.record_viewers(stream_id, viewers)
            db.upsert_stream(
                channel_name=channel_name,
                channel_id=detail["channel_id"],
                video_id=video_id,
                title=detail["title"],
            )
            logger.info(f"[{now}] {channel_name}: {viewers:,} viewers")
        else:
            # Stream ended between discovery cycles
            logger.info(f"[{now}] {channel_name}: stream ended (video_id={video_id})")
            db.mark_stream_ended(video_id)
            if video_id in _active_streams.get(channel_name, {}):
                del _active_streams[channel_name][video_id]

    # Check for videos that weren't returned (deleted/private)
    returned_ids = {d["video_id"] for d in details}
    for video_id in set(video_ids) - returned_ids:
        channel_name, stream_id = video_to_info[video_id]
        logger.warning(f"Video {video_id} not found in API response, marking ended.")
        db.mark_stream_ended(video_id)
        if video_id in _active_streams.get(channel_name, {}):
            del _active_streams[channel_name][video_id]
