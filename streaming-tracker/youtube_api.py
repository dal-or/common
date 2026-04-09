"""
YouTube Data API v3 wrapper with API key pool rotation.

Quota strategy:
- search.list (100 units/call): used only for channels without a known active stream.
- videos.list (1 unit/call): used every minute to read viewers, batched.
- API keys rotate automatically when one hits quota limit (403 quotaExceeded).
- Daily quota resets at midnight Pacific Time.

With smart search (skip channels with active streams) + key pool:
  - Initial discovery: 8 channels × 100 = 800 units
  - Re-search only when a stream ends: ~10 program changes/day × 8 channels × 100 = 8,000 units
  - Viewer polling: ~1,440 units/day (1 batched call/min)
  - Total: ~10,240 units/day → fits in 2 keys comfortably
"""

import logging
from typing import Optional
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import YOUTUBE_API_KEYS

logger = logging.getLogger(__name__)


class ApiKeyPool:
    """
    Manages a pool of YouTube API keys with automatic rotation.

    When a key hits quota (403 quotaExceeded), it's marked as exhausted
    and the next key in the pool is used. All keys reset at the start
    of each new UTC day (YouTube resets at midnight Pacific, but UTC
    is close enough for our purposes).
    """

    def __init__(self, api_keys: list[str]):
        self._keys = [k for k in api_keys if k]
        if not self._keys:
            raise ValueError("No API keys configured")
        self._current_index = 0
        self._exhausted: set[int] = set()
        self._clients: dict[int, object] = {}
        logger.info(f"API key pool initialized with {len(self._keys)} key(s)")

    @property
    def available_count(self) -> int:
        return len(self._keys) - len(self._exhausted)

    def _build_client(self, index: int):
        if index not in self._clients:
            self._clients[index] = build(
                "youtube", "v3", developerKey=self._keys[index]
            )
        return self._clients[index]

    def get_client(self):
        """Get a YouTube client using the current active key."""
        if self.available_count == 0:
            raise QuotaExhaustedError(
                f"All {len(self._keys)} API key(s) have exceeded their quota. "
                f"Add more keys to YOUTUBE_API_KEYS or wait for quota reset."
            )
        return self._build_client(self._current_index)

    def mark_exhausted(self):
        """Mark the current key as exhausted and rotate to the next available one."""
        key_num = self._current_index + 1
        logger.warning(
            f"API key #{key_num}/{len(self._keys)} quota exhausted. "
            f"{self.available_count - 1} key(s) remaining."
        )
        self._exhausted.add(self._current_index)
        self._rotate()

    def _rotate(self):
        """Rotate to the next non-exhausted key."""
        for _ in range(len(self._keys)):
            self._current_index = (self._current_index + 1) % len(self._keys)
            if self._current_index not in self._exhausted:
                logger.info(f"Rotated to API key #{self._current_index + 1}/{len(self._keys)}")
                return
        # All exhausted — will raise on next get_client() call

    def reset_all(self):
        """Reset all keys (call when quota resets, e.g., new day)."""
        if self._exhausted:
            logger.info(f"Resetting {len(self._exhausted)} exhausted key(s)")
            self._exhausted.clear()


class QuotaExhaustedError(Exception):
    """Raised when all API keys in the pool have exceeded quota."""
    pass


# --- Module-level pool instance ---
_pool: Optional[ApiKeyPool] = None


def init_api_pool(api_keys: list[str]):
    """Initialize the API key pool. Called from main.py on startup."""
    global _pool
    _pool = ApiKeyPool(api_keys)


def _get_pool() -> ApiKeyPool:
    if _pool is None:
        raise RuntimeError("API key pool not initialized. Call init_api_pool() first.")
    return _pool


def _handle_http_error(e: HttpError) -> bool:
    """
    Handle an HttpError. If it's a quota error, rotate the key and return True
    (caller should retry). Otherwise return False.
    """
    if e.resp.status == 403:
        error_reason = ""
        if e.error_details:
            for detail in e.error_details:
                error_reason = detail.get("reason", "")
                if error_reason in ("quotaExceeded", "rateLimitExceeded", "dailyLimitExceeded"):
                    _get_pool().mark_exhausted()
                    return True
    return False


def _api_call_with_retry(fn, max_retries=None):
    """
    Execute an API call function with automatic key rotation on quota errors.
    fn receives a youtube client and should return the result.
    Retries up to len(pool keys) times on quota errors.
    """
    pool = _get_pool()
    if max_retries is None:
        max_retries = len(pool._keys)

    for attempt in range(max_retries):
        try:
            client = pool.get_client()
            return fn(client)
        except QuotaExhaustedError:
            raise
        except HttpError as e:
            if _handle_http_error(e) and attempt < max_retries - 1:
                continue  # Retry with next key
            raise

    raise QuotaExhaustedError("All retries exhausted")


def reset_exhausted_keys():
    """Reset exhausted keys. Called daily or when needed."""
    pool = _get_pool()
    pool.reset_all()


def search_live_streams(channel_id: str) -> list[dict]:
    """
    Search for currently live streams on a channel.
    Returns list of {video_id, title}.
    Costs 100 quota units.
    """
    def _call(yt):
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

    try:
        return _api_call_with_retry(_call)
    except (HttpError, QuotaExhaustedError) as e:
        logger.error(f"YouTube search error for channel {channel_id}: {e}")
        return []


def get_video_details(video_ids: list[str]) -> list[dict]:
    """
    Get details for a list of videos, including live viewer count.
    Accepts up to 50 IDs per call. Costs 1 quota unit per call.
    """
    if not video_ids:
        return []

    all_results = []

    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        batch_str = ",".join(batch)

        def _call(yt, ids=batch_str):
            return yt.videos().list(
                part="snippet,liveStreamingDetails",
                id=ids,
            ).execute()

        try:
            response = _api_call_with_retry(_call)
        except (HttpError, QuotaExhaustedError) as e:
            logger.error(f"YouTube videos.list error: {e}")
            continue

        for item in response.get("items", []):
            live_details = item.get("liveStreamingDetails", {})
            snippet = item.get("snippet", {})

            concurrent_viewers = live_details.get("concurrentViewers")
            actual_start = live_details.get("actualStartTime")
            actual_end = live_details.get("actualEndTime")

            thumbnails = snippet.get("thumbnails", {})
            thumbnail_url = (
                thumbnails.get("maxres", {}).get("url")
                or thumbnails.get("standard", {}).get("url")
                or thumbnails.get("high", {}).get("url")
                or thumbnails.get("medium", {}).get("url")
                or thumbnails.get("default", {}).get("url")
                or ""
            )

            all_results.append({
                "video_id": item["id"],
                "title": snippet.get("title", "Unknown"),
                "channel_id": snippet.get("channelId", ""),
                "channel_title": snippet.get("channelTitle", ""),
                "is_live": concurrent_viewers is not None and actual_end is None,
                "concurrent_viewers": int(concurrent_viewers) if concurrent_viewers else 0,
                "actual_start_time": actual_start,
                "actual_end_time": actual_end,
                "thumbnail_url": thumbnail_url,
            })

    return all_results


def check_video_still_live(video_id: str) -> Optional[dict]:
    """Quick check if a single video is still live. Returns detail dict or None."""
    details = get_video_details([video_id])
    if details and details[0]["is_live"]:
        return details[0]
    return None


def resolve_handle_to_channel_id(handle: str) -> Optional[str]:
    """
    Resolve a YouTube handle (e.g. 'olgaenvivo') to a channel ID.
    Uses channels.list with forHandle parameter. Costs 1 quota unit.
    """
    def _call_handle(yt):
        return yt.channels().list(part="id", forHandle=handle).execute()

    def _call_search(yt):
        return yt.search().list(
            part="snippet", q=handle, type="channel", maxResults=1
        ).execute()

    try:
        response = _api_call_with_retry(_call_handle)
        items = response.get("items", [])
        if items:
            return items[0]["id"]

        logger.warning(f"forHandle lookup failed for @{handle}, trying search...")
        response = _api_call_with_retry(_call_search)
        items = response.get("items", [])
        if items:
            return items[0]["snippet"]["channelId"]

        return None

    except (HttpError, QuotaExhaustedError) as e:
        logger.error(f"Error resolving handle @{handle}: {e}")
        return None
