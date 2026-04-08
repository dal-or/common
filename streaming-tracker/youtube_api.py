"""
YouTube Data API v3 wrapper for fetching live stream information.

Quota strategy:
- search.list (100 units/call) is used sparingly to discover live video IDs.
- videos.list (1 unit/call) is used every minute to fetch viewer counts.
  We batch up to 50 video IDs per call, so it stays very cheap.

Daily quota default: 10,000 units.
With 8 channels searched every 5 min: 8 * (1440/5) * 100 = ~230,400 -> too much!
So instead: one search per channel every 5 min BUT we batch channels cleverly.

Better approach: use channels.list to get each channel's "live" broadcast via
the channel's content details, or search once and cache the video ID until it
changes. We combine search calls: one search.list can have only one channelId,
so we need one per channel. But we only re-search every 5 minutes and only
if we don't already have an active stream for that channel.
"""

import logging
from typing import Optional
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import YOUTUBE_API_KEY

logger = logging.getLogger(__name__)

_youtube = None


def get_youtube_client():
    global _youtube
    if _youtube is None:
        _youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    return _youtube


def search_live_streams(channel_id: str) -> list[dict]:
    """
    Search for currently live streams on a channel.
    Returns list of {video_id, title}.
    Costs 100 quota units.
    """
    yt = get_youtube_client()
    try:
        response = yt.search().list(
            part="id,snippet",
            channelId=channel_id,
            eventType="live",
            type="video",
            maxResults=5,
        ).execute()

        results = []
        for item in response.get("items", []):
            results.append({
                "video_id": item["id"]["videoId"],
                "title": item["snippet"]["title"],
            })
        return results

    except HttpError as e:
        logger.error(f"YouTube search error for channel {channel_id}: {e}")
        return []


def get_video_details(video_ids: list[str]) -> list[dict]:
    """
    Get details for a list of videos, including live viewer count.
    Accepts up to 50 IDs per call. Costs 1 quota unit per call.

    Returns list of dicts with:
    - video_id, title, channel_id, channel_title
    - is_live, concurrent_viewers, actual_start_time
    """
    if not video_ids:
        return []

    yt = get_youtube_client()
    results = []

    # Process in batches of 50 (YouTube API limit)
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        try:
            response = yt.videos().list(
                part="snippet,liveStreamingDetails",
                id=",".join(batch),
            ).execute()

            for item in response.get("items", []):
                live_details = item.get("liveStreamingDetails", {})
                snippet = item.get("snippet", {})

                concurrent_viewers = live_details.get("concurrentViewers")
                actual_start = live_details.get("actualStartTime")
                actual_end = live_details.get("actualEndTime")

                results.append({
                    "video_id": item["id"],
                    "title": snippet.get("title", "Unknown"),
                    "channel_id": snippet.get("channelId", ""),
                    "channel_title": snippet.get("channelTitle", ""),
                    "is_live": concurrent_viewers is not None and actual_end is None,
                    "concurrent_viewers": int(concurrent_viewers) if concurrent_viewers else 0,
                    "actual_start_time": actual_start,
                    "actual_end_time": actual_end,
                })

        except HttpError as e:
            logger.error(f"YouTube videos.list error: {e}")

    return results


def check_video_still_live(video_id: str) -> Optional[dict]:
    """Quick check if a single video is still live. Returns detail dict or None."""
    details = get_video_details([video_id])
    if details and details[0]["is_live"]:
        return details[0]
    return None
