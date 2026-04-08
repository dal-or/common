"""
Database module for storing live stream viewer data.

Schema:
- streams: tracks each live stream (video) detected
- viewer_snapshots: stores viewer count samples taken every minute
"""

import sqlite3
from datetime import datetime
from typing import Optional

from config import DB_PATH


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS streams (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_name    TEXT    NOT NULL,
            channel_id      TEXT    NOT NULL,
            video_id        TEXT    NOT NULL UNIQUE,
            title           TEXT    NOT NULL,
            started_at      TEXT,           -- ISO 8601 from YouTube
            ended_at        TEXT,           -- set when stream ends
            first_seen      TEXT    NOT NULL DEFAULT (datetime('now')),
            last_seen       TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS viewer_snapshots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            stream_id       INTEGER NOT NULL REFERENCES streams(id),
            viewers         INTEGER NOT NULL,
            recorded_at     TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_snapshots_stream
            ON viewer_snapshots(stream_id);
        CREATE INDEX IF NOT EXISTS idx_snapshots_time
            ON viewer_snapshots(recorded_at);
        CREATE INDEX IF NOT EXISTS idx_streams_video
            ON streams(video_id);
        CREATE INDEX IF NOT EXISTS idx_streams_channel
            ON streams(channel_name);
    """)
    conn.commit()
    conn.close()


def upsert_stream(
    channel_name: str,
    channel_id: str,
    video_id: str,
    title: str,
    started_at: Optional[str] = None,
) -> int:
    """Insert or update a stream record. Returns the stream id."""
    conn = get_connection()
    now = datetime.utcnow().isoformat()

    # Try to find existing
    row = conn.execute(
        "SELECT id FROM streams WHERE video_id = ?", (video_id,)
    ).fetchone()

    if row:
        stream_id = row["id"]
        conn.execute(
            "UPDATE streams SET last_seen = ?, title = ? WHERE id = ?",
            (now, title, stream_id),
        )
    else:
        cur = conn.execute(
            """INSERT INTO streams (channel_name, channel_id, video_id, title,
                                    started_at, first_seen, last_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (channel_name, channel_id, video_id, title, started_at, now, now),
        )
        stream_id = cur.lastrowid

    conn.commit()
    conn.close()
    return stream_id


def record_viewers(stream_id: int, viewers: int):
    """Record a viewer count snapshot."""
    conn = get_connection()
    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO viewer_snapshots (stream_id, viewers, recorded_at) VALUES (?, ?, ?)",
        (stream_id, viewers, now),
    )
    conn.commit()
    conn.close()


def mark_stream_ended(video_id: str):
    """Mark a stream as ended."""
    conn = get_connection()
    now = datetime.utcnow().isoformat()
    conn.execute(
        "UPDATE streams SET ended_at = ? WHERE video_id = ? AND ended_at IS NULL",
        (now, video_id),
    )
    conn.commit()
    conn.close()


def get_active_streams() -> list[dict]:
    """Get all streams that haven't ended."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT s.*,
                  (SELECT viewers FROM viewer_snapshots
                   WHERE stream_id = s.id ORDER BY recorded_at DESC LIMIT 1) as current_viewers,
                  (SELECT MAX(viewers) FROM viewer_snapshots WHERE stream_id = s.id) as peak_viewers,
                  (SELECT AVG(viewers) FROM viewer_snapshots WHERE stream_id = s.id) as avg_viewers,
                  (SELECT COUNT(*) FROM viewer_snapshots WHERE stream_id = s.id) as snapshot_count
           FROM streams s
           WHERE s.ended_at IS NULL
           ORDER BY current_viewers DESC"""
    ).fetchall()
    result = [dict(r) for r in rows]
    conn.close()
    return result


def get_stream_snapshots(stream_id: int) -> list[dict]:
    """Get all viewer snapshots for a stream."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT viewers, recorded_at
           FROM viewer_snapshots
           WHERE stream_id = ?
           ORDER BY recorded_at ASC""",
        (stream_id,),
    ).fetchall()
    result = [dict(r) for r in rows]
    conn.close()
    return result


def get_streams_active_in_last_hours(hours: int = 1) -> list[dict]:
    """Get streams that were active in the last N hours (including ended ones)."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT s.*,
                  (SELECT viewers FROM viewer_snapshots
                   WHERE stream_id = s.id ORDER BY recorded_at DESC LIMIT 1) as current_viewers,
                  (SELECT MAX(viewers) FROM viewer_snapshots WHERE stream_id = s.id) as peak_viewers,
                  (SELECT CAST(AVG(viewers) AS INTEGER) FROM viewer_snapshots WHERE stream_id = s.id) as avg_viewers,
                  (SELECT COUNT(*) FROM viewer_snapshots WHERE stream_id = s.id) as snapshot_count
           FROM streams s
           WHERE s.last_seen >= datetime('now', ? || ' hours')
           ORDER BY current_viewers DESC""",
        (f"-{hours}",),
    ).fetchall()
    result = [dict(r) for r in rows]
    conn.close()
    return result
