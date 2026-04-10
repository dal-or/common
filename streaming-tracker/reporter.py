"""
Report generator.

Generates:
1. Hourly reports: snapshot of currently live streams.
2. Daily reports: full-day summary of all streams that aired that day,
   ranked by peak viewers, with individual + timeline graphs.
"""

import io
import logging
import os
from datetime import datetime, date, timedelta
from urllib.request import urlopen, Request
from urllib.error import URLError

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as ticker
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from PIL import Image

import database as db
from config import REPORTS_DIR

logger = logging.getLogger(__name__)

# Colors for different channels (consistent across reports)
CHANNEL_COLORS = {
    "Luzu TV": "#FF6B35",
    "Olga": "#004E89",
    "Blender": "#7B2D8E",
    "Gelatina": "#1DB954",
    "Bondi Live": "#E63946",
    "Carajo": "#F4A261",
    "La Casa Streaming": "#2A9D8F",
    "Vorterix": "#264653",
}
DEFAULT_COLOR = "#666666"


def _ensure_reports_dir(subdir: str = "") -> str:
    path = os.path.join(REPORTS_DIR, subdir) if subdir else REPORTS_DIR
    os.makedirs(path, exist_ok=True)
    return path


def _parse_iso(dt_str: str) -> datetime:
    """Parse ISO datetime string, always returning a naive UTC datetime."""
    if not dt_str:
        return datetime.utcnow()
    # Handle YouTube's format with Z suffix
    dt_str = dt_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(dt_str)
        # Strip timezone info to keep everything as naive UTC
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt
    except ValueError:
        return datetime.utcnow()


def _download_thumbnail(url: str) -> Image.Image | None:
    """Download a thumbnail image from URL. Returns a PIL Image or None on failure."""
    if not url:
        return None
    try:
        req = Request(url, headers={"User-Agent": "StreamingTracker/1.0"})
        with urlopen(req, timeout=10) as resp:
            data = resp.read()
        return Image.open(io.BytesIO(data))
    except (URLError, OSError, Exception) as e:
        logger.warning(f"Could not download thumbnail: {e}")
        return None


def _add_thumbnail_to_axes(ax, thumb_img: Image.Image, position="right"):
    """
    Embed a thumbnail image into a matplotlib axes.
    Position: 'right' places it at bottom-right of the plot area.
    """
    # Resize to a reasonable size for the graph
    thumb_img.thumbnail((280, 160), Image.LANCZOS)
    imagebox = OffsetImage(thumb_img, zoom=1, alpha=0.85)
    imagebox.image.axes = ax

    # Place at bottom-right with a subtle border
    ab = AnnotationBbox(
        imagebox,
        (1.0, 0.0),
        xycoords="axes fraction",
        box_alignment=(1.05, -0.05),
        frameon=True,
        bboxprops=dict(boxstyle="round,pad=0.1", facecolor="white", edgecolor="#cccccc", linewidth=1),
    )
    ax.add_artist(ab)


def generate_stream_graph(stream: dict, report_dir: str, snapshots: list[dict] | None = None) -> str:
    """
    Generate a viewer count graph for a single stream.
    Returns the path to the saved PNG.

    If snapshots is provided, use those (useful for filtering to a specific day).
    Otherwise, loads all snapshots for the stream.
    """
    if snapshots is None:
        snapshots = db.get_stream_snapshots(stream["id"])
    if len(snapshots) < 2:
        return ""

    times = [_parse_iso(s["recorded_at"]) for s in snapshots]
    viewers = [s["viewers"] for s in snapshots]

    color = CHANNEL_COLORS.get(stream["channel_name"], DEFAULT_COLOR)

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(times, viewers, color=color, linewidth=2)
    ax.fill_between(times, viewers, alpha=0.15, color=color)

    # Formatting
    ax.set_title(
        f'{stream["channel_name"]} - "{stream["title"]}"',
        fontsize=14, fontweight="bold", pad=15
    )
    ax.set_xlabel("Hora (UTC)", fontsize=11)
    ax.set_ylabel("Viewers", fontsize=11)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())

    # Stats annotation
    peak = max(viewers)
    avg = sum(viewers) // len(viewers)
    current = viewers[-1]
    stats_text = f"Actual: {current:,}  |  Pico: {peak:,}  |  Promedio: {avg:,}"
    ax.annotate(
        stats_text, xy=(0.5, 1.02), xycoords="axes fraction",
        ha="center", fontsize=10, color="#555555"
    )

    # Embed live thumbnail
    thumb_img = _download_thumbnail(stream.get("thumbnail_url", ""))
    if thumb_img:
        _add_thumbnail_to_axes(ax, thumb_img)

    ax.grid(True, alpha=0.3)
    ax.set_xlim(times[0], times[-1])
    ax.set_ylim(bottom=0)
    fig.tight_layout()

    filename = f"{stream['channel_name'].replace(' ', '_')}_{stream['video_id']}.png"
    filepath = os.path.join(report_dir, filename)
    fig.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close(fig)

    logger.info(f"Graph saved: {filepath}")
    return filepath


def generate_combined_graph(streams: list[dict], report_dir: str) -> str:
    """
    Generate a single graph comparing all currently live streams.
    Returns path to the saved PNG.
    """
    if not streams:
        return ""

    fig, ax = plt.subplots(figsize=(14, 6))

    for stream in streams:
        snapshots = db.get_stream_snapshots(stream["id"])
        if len(snapshots) < 2:
            continue

        times = [_parse_iso(s["recorded_at"]) for s in snapshots]
        viewers = [s["viewers"] for s in snapshots]
        color = CHANNEL_COLORS.get(stream["channel_name"], DEFAULT_COLOR)

        label = f'{stream["channel_name"]} ({viewers[-1]:,} viewers)'
        ax.plot(times, viewers, color=color, linewidth=2, label=label)

    ax.set_title(
        "Streaming en vivo - Comparativa de audiencia",
        fontsize=14, fontweight="bold", pad=15
    )
    ax.set_xlabel("Hora (UTC)", fontsize=11)
    ax.set_ylabel("Viewers", fontsize=11)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_ylim(bottom=0)
    fig.tight_layout()

    filename = "comparativa_audiencia.png"
    filepath = os.path.join(report_dir, filename)
    fig.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close(fig)

    logger.info(f"Combined graph saved: {filepath}")
    return filepath


def generate_hourly_report() -> str:
    """
    Generate the full hourly report: text summary + graphs.
    Returns the text report.
    """
    now = datetime.utcnow()
    timestamp = now.strftime("%Y-%m-%d_%H-%M")
    report_dir = _ensure_reports_dir(timestamp)

    streams = db.get_active_streams()

    # --- Text report ---
    lines = []
    lines.append("=" * 60)
    lines.append(f"  REPORTE DE AUDIENCIA - {now.strftime('%Y-%m-%d %H:%M')} UTC")
    lines.append("=" * 60)
    lines.append("")

    if not streams:
        lines.append("No hay streams en vivo en este momento.")
    else:
        lines.append(f"Canales en vivo: {len(streams)}")
        lines.append("")

        total_viewers = 0
        for i, stream in enumerate(streams, 1):
            current = stream.get("current_viewers") or 0
            peak = stream.get("peak_viewers") or 0
            avg = stream.get("avg_viewers") or 0
            snapshots = stream.get("snapshot_count") or 0
            total_viewers += current

            started = stream.get("started_at") or stream.get("first_seen") or "?"
            if started and started != "?":
                start_dt = _parse_iso(started)
                duration = now - start_dt
                hours, remainder = divmod(int(duration.total_seconds()), 3600)
                minutes = remainder // 60
                duration_str = f"{hours}h {minutes}m"
            else:
                duration_str = "?"

            lines.append(f"  {i}. {stream['channel_name']}")
            lines.append(f"     Programa: {stream['title']}")
            lines.append(f"     Viewers actuales: {current:,}")
            lines.append(f"     Pico: {peak:,}  |  Promedio: {avg:,}")
            lines.append(f"     Duracion: {duration_str}  |  Muestras: {snapshots}")
            lines.append(f"     Video: https://youtube.com/watch?v={stream['video_id']}")
            lines.append("")

        lines.append(f"  TOTAL VIEWERS: {total_viewers:,}")
        lines.append("")

    lines.append("=" * 60)
    report_text = "\n".join(lines)

    # Save text report
    report_path = os.path.join(report_dir, "reporte.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    logger.info(f"Text report saved: {report_path}")

    # --- Graphs ---
    for stream in streams:
        generate_stream_graph(stream, report_dir)

    generate_combined_graph(streams, report_dir)

    # Print report to console
    print(report_text)

    return report_text


# ---------------------------------------------------------------------------
# Daily report
# ---------------------------------------------------------------------------


def generate_daily_timeline_graph(
    streams: list[dict],
    day: str,
    report_dir: str,
) -> str:
    """
    Build a single timeline graph showing viewer curves for every stream
    that aired on `day`. Each stream is drawn with its channel color,
    plotted against the actual time of day when its snapshots were recorded.
    """
    if not streams:
        return ""

    fig, ax = plt.subplots(figsize=(16, 7))

    day_start = datetime.strptime(day, "%Y-%m-%d")
    day_end = day_start + timedelta(days=1)

    any_data = False
    for stream in streams:
        snapshots = db.get_stream_snapshots_for_day(stream["id"], day)
        if len(snapshots) < 2:
            continue
        any_data = True

        times = [_parse_iso(s["recorded_at"]) for s in snapshots]
        viewers = [s["viewers"] for s in snapshots]
        color = CHANNEL_COLORS.get(stream["channel_name"], DEFAULT_COLOR)

        peak = max(viewers)
        label = f'{stream["channel_name"]} — {stream["title"][:40]} (pico {peak:,})'
        ax.plot(times, viewers, color=color, linewidth=1.8, label=label)
        ax.fill_between(times, viewers, alpha=0.08, color=color)

    if not any_data:
        plt.close(fig)
        return ""

    ax.set_title(
        f"Timeline de audiencia — {day} (UTC)",
        fontsize=15, fontweight="bold", pad=15
    )
    ax.set_xlabel("Hora del día (UTC)", fontsize=11)
    ax.set_ylabel("Viewers", fontsize=11)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
    ax.set_xlim(day_start, day_end)
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3)
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.12),
        ncol=2,
        fontsize=8,
        frameon=False,
    )
    fig.tight_layout()

    filepath = os.path.join(report_dir, "timeline_dia.png")
    fig.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Daily timeline graph saved: {filepath}")
    return filepath


def generate_daily_ranking_graph(streams: list[dict], day: str, report_dir: str) -> str:
    """Horizontal bar chart ranking all streams by peak viewers."""
    if not streams:
        return ""

    ranked = sorted(
        [s for s in streams if (s.get("peak_viewers") or 0) > 0],
        key=lambda s: s["peak_viewers"],
        reverse=True,
    )
    if not ranked:
        return ""

    labels = [
        f'{s["channel_name"]} — {s["title"][:45]}'
        for s in ranked
    ]
    peaks = [s["peak_viewers"] for s in ranked]
    colors = [CHANNEL_COLORS.get(s["channel_name"], DEFAULT_COLOR) for s in ranked]

    height = max(4, 0.45 * len(ranked) + 2)
    fig, ax = plt.subplots(figsize=(14, height))
    bars = ax.barh(range(len(ranked)), peaks, color=colors)
    ax.set_yticks(range(len(ranked)))
    ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Pico de viewers", fontsize=11)
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{int(x):,}"))
    ax.set_title(
        f"Ranking de programas por pico de audiencia — {day} (UTC)",
        fontsize=14, fontweight="bold", pad=15,
    )

    # Value labels on bars
    for bar, peak in zip(bars, peaks):
        ax.text(
            bar.get_width(),
            bar.get_y() + bar.get_height() / 2,
            f" {peak:,}",
            va="center",
            ha="left",
            fontsize=9,
        )

    ax.grid(True, axis="x", alpha=0.3)
    fig.tight_layout()

    filepath = os.path.join(report_dir, "ranking_dia.png")
    fig.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Daily ranking graph saved: {filepath}")
    return filepath


def generate_daily_report(day: str | None = None) -> str:
    """
    Generate a full report for a given day (UTC).

    day: 'YYYY-MM-DD'. If None, uses today (UTC).

    Outputs to reports/daily_<day>/:
      - reporte.txt        text summary ranked by peak viewers
      - timeline_dia.png   all streams plotted against time of day
      - ranking_dia.png    bar chart of programs by peak
      - <channel>_<vid>.png  individual stream graph (one per stream)
    """
    if day is None:
        day = datetime.utcnow().strftime("%Y-%m-%d")

    # Validate format
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Invalid day format: {day!r}. Expected YYYY-MM-DD.")

    report_dir = _ensure_reports_dir(f"daily_{day}")
    streams = db.get_streams_for_day(day)

    # --- Text report ---
    lines = []
    lines.append("=" * 70)
    lines.append(f"  REPORTE DIARIO DE AUDIENCIA — {day} (UTC)")
    lines.append("=" * 70)
    lines.append("")

    if not streams:
        lines.append("No se registraron streams durante este día.")
    else:
        lines.append(f"Total de programas trackeados: {len(streams)}")
        lines.append("")
        lines.append("Ranking por pico de audiencia:")
        lines.append("-" * 70)

        grand_peak = 0
        for i, stream in enumerate(streams, 1):
            peak = stream.get("peak_viewers") or 0
            avg = stream.get("avg_viewers") or 0
            snapshots = stream.get("snapshot_count") or 0
            grand_peak = max(grand_peak, peak)

            first = stream.get("day_first_snapshot") or ""
            last = stream.get("day_last_snapshot") or ""
            if first and last:
                start_dt = _parse_iso(first)
                end_dt = _parse_iso(last)
                duration = end_dt - start_dt
                hours, remainder = divmod(int(duration.total_seconds()), 3600)
                minutes = remainder // 60
                duration_str = f"{hours}h {minutes}m"
                time_range = f"{start_dt.strftime('%H:%M')}-{end_dt.strftime('%H:%M')}"
            else:
                duration_str = "?"
                time_range = "?"

            lines.append(f"  {i}. {stream['channel_name']} — {stream['title']}")
            lines.append(f"     Horario (UTC): {time_range}   Duración: {duration_str}")
            lines.append(f"     Pico: {peak:,}   Promedio: {avg:,}   Muestras: {snapshots}")
            lines.append(f"     https://youtube.com/watch?v={stream['video_id']}")
            lines.append("")

        lines.append(f"Pico más alto del día: {grand_peak:,} viewers")
        lines.append("")

    lines.append("=" * 70)
    report_text = "\n".join(lines)

    report_path = os.path.join(report_dir, "reporte.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    logger.info(f"Daily text report saved: {report_path}")

    # --- Graphs ---
    if streams:
        generate_daily_timeline_graph(streams, day, report_dir)
        generate_daily_ranking_graph(streams, day, report_dir)

        for stream in streams:
            day_snapshots = db.get_stream_snapshots_for_day(stream["id"], day)
            generate_stream_graph(stream, report_dir, snapshots=day_snapshots)

    print(report_text)
    logger.info(f"Daily report complete: {report_dir}")
    return report_text
