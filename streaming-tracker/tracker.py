"""
Core tracker logic.

Two loops run at different intervals:
1. discover_live_streams (every LIVE_SEARCH_INTERVAL seconds):
   - For channels WITHOUT a known active stream, searches YouTube (100 units each).
   - Channels that already have a tracked live stream are SKIPPED (saves quota).
   - Registers new streams in the database.
   - Detects streams that ended (were tracked but no longer live).

2. poll_viewer_counts (every POLL_INTERVAL seconds):
   - For all currently tracked live streams, fetches concurrent viewers.
   - Uses videos.list batched (1 unit total), very cheap.
   - Also detects stream endings between discovery cycles.
"""

import logging
from datetime import datetime

import database as db
import youtube_api as yt

logger = logging.getLogger(__name__)

# In-memory cache: channel_name -> {video_id: stream_id}
_active_streams: dict[str, dict[str, int]] = {}

# Loaded channels: {name: channel_id} — set by init_channels()
_channels: dict[str, str] = {}


def init_channels(channels: dict[str, str]):
    """Set the channels dict from the resolved channels.json."""
    global _channels
    _channels = channels
    logger.info(f"Tracker initialized with {len(_channels)} channels: {', '.join(_channels.keys())}")


def discover_live_streams():
    """
    Search for live streams, but ONLY on channels that don't have a known
    active stream. This is the key quota optimization.

    Channels with an active stream are verified via poll_viewer_counts()
    (which uses the cheap videos.list endpoint).
    """
    logger.info("Discovering live streams...")

    # Determine which channels need a search
    channels_to_search = {}
    channels_skipped = []
    for channel_name, channel_id in _channels.items():
        active = _active_streams.get(channel_name, {})
        if active:
            channels_skipped.append(channel_name)
        else:
            channels_to_search[channel_name] = channel_id

    if channels_skipped:
        logger.info(
            f"Skipping {len(channels_skipped)} channel(s) with active streams: "
            f"{', '.join(channels_skipped)}"
        )

    if not channels_to_search:
        logger.info("All channels have active streams. No search needed.")
        return

    logger.info(
        f"Searching {len(channels_to_search)} channel(s): "
        f"{', '.join(channels_to_search.keys())} "
        f"(cost: ~{len(channels_to_search) * 100} quota units)"
    )

    for channel_name, channel_id in channels_to_search.items():
        try:
            live_results = yt.search_live_streams(channel_id)
        except Exception as e:
            logger.error(f"Error searching {channel_name}: {e}")
            continue

        for result in live_results:
            video_id = result["video_id"]
            title = result["title"]

            if channel_name not in _active_streams:
                _active_streams[channel_name] = {}

            if video_id not in _active_streams[channel_name]:
                details = yt.get_video_details([video_id])
                started_at = None
                thumbnail_url = ""
                if details:
                    started_at = details[0].get("actual_start_time")
                    thumbnail_url = details[0].get("thumbnail_url", "")

                stream_id = db.upsert_stream(
                    channel_name=channel_name,
                    channel_id=channel_id,
                    video_id=video_id,
                    title=title,
                    started_at=started_at,
                    thumbnail_url=thumbnail_url,
                )
                _active_streams[channel_name][video_id] = stream_id
                logger.info(
                    f"New live stream: {channel_name} - '{title}' "
                    f"(video_id={video_id}, stream_id={stream_id})"
                )

    total_active = sum(len(v) for v in _active_streams.values())
    logger.info(f"Discovery complete. {total_active} active stream(s) tracked.")


def poll_viewer_counts():
    """
    For all tracked live streams, fetch and record current viewer counts.
    This is cheap: 1 quota unit per batch of up to 50 videos.

    Also detects stream endings — if a video is no longer live, it gets
    removed from _active_streams so the next discovery cycle will search
    that channel again.
    """
    video_to_info: dict[str, tuple[str, int]] = {}
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
                thumbnail_url=detail.get("thumbnail_url", ""),
            )
            logger.info(f"[{now}] {channel_name}: {viewers:,} viewers")
        else:
            logger.info(f"[{now}] {channel_name}: stream ended (video_id={video_id})")
            db.mark_stream_ended(video_id)
            if video_id in _active_streams.get(channel_name, {}):
                del _active_streams[channel_name][video_id]

    # Videos not returned by API (deleted/private)
    returned_ids = {d["video_id"] for d in details}
    for video_id in set(video_ids) - returned_ids:
        channel_name, stream_id = video_to_info[video_id]
        logger.warning(f"Video {video_id} not found in API response, marking ended.")
        db.mark_stream_ended(video_id)
        if video_id in _active_streams.get(channel_name, {}):
            del _active_streams[channel_name][video_id]
