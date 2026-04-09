"""
Channel loader: reads channels.json, resolves URLs to channel IDs,
and caches the resolved IDs back to the file.
"""

import json
import logging
import re

from config import CHANNELS_FILE

logger = logging.getLogger(__name__)


def load_channels_file() -> list[dict]:
    """Load the raw channel list from JSON."""
    with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_channels_file(channels: list[dict]):
    """Save the channel list back to JSON (with resolved IDs cached)."""
    with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
        json.dump(channels, f, indent=4, ensure_ascii=False)
    logger.info(f"Saved resolved channel IDs to {CHANNELS_FILE}")


def extract_handle_or_id(url: str) -> tuple[str, str]:
    """
    Parse a YouTube URL and extract either a handle or channel ID.
    Returns (type, value) where type is 'handle', 'channel_id', or 'unknown'.

    Examples:
      https://www.youtube.com/@Handle        -> ('handle', 'Handle')
      https://www.youtube.com/channel/UC...   -> ('channel_id', 'UC...')
      https://youtube.com/@Handle             -> ('handle', 'Handle')
      UC...                                   -> ('channel_id', 'UC...')
    """
    url = url.strip()

    # Direct channel ID (starts with UC)
    if re.match(r"^UC[\w-]{22}$", url):
        return ("channel_id", url)

    # @Handle in URL
    match = re.search(r"youtube\.com/@([\w.-]+)", url)
    if match:
        return ("handle", match.group(1))

    # /channel/UC... in URL
    match = re.search(r"youtube\.com/channel/(UC[\w-]{22})", url)
    if match:
        return ("channel_id", match.group(1))

    # /c/CustomName or /user/Username
    match = re.search(r"youtube\.com/(?:c|user)/([\w.-]+)", url)
    if match:
        return ("handle", match.group(1))

    return ("unknown", url)


def resolve_channels(resolve_fn) -> dict[str, str]:
    """
    Load channels from JSON, resolve any missing channel IDs, cache them,
    and return a dict of {name: channel_id}.

    resolve_fn: a function(handle: str) -> Optional[str] that resolves
                a YouTube handle to a channel ID via the API.
    """
    channels = load_channels_file()
    result = {}
    needs_save = False

    for entry in channels:
        name = entry["name"]
        url = entry.get("url", "")
        cached_id = entry.get("channel_id")

        # If we already have a cached channel_id, use it
        if cached_id:
            result[name] = cached_id
            continue

        url_type, value = extract_handle_or_id(url)

        if url_type == "channel_id":
            entry["channel_id"] = value
            result[name] = value
            needs_save = True
            logger.info(f"Resolved {name}: channel ID from URL -> {value}")

        elif url_type == "handle":
            resolved_id = resolve_fn(value)
            if resolved_id:
                entry["channel_id"] = resolved_id
                result[name] = resolved_id
                needs_save = True
                logger.info(f"Resolved {name}: @{value} -> {resolved_id}")
            else:
                logger.error(
                    f"Could not resolve channel ID for {name} (@{value}). "
                    f"Skipping. You can manually add 'channel_id' to channels.json."
                )
        else:
            logger.error(
                f"Unrecognized URL format for {name}: '{url}'. "
                f"Use https://www.youtube.com/@Handle or a channel ID."
            )

    if needs_save:
        save_channels_file(channels)

    return result
