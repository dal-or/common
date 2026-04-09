"""
Hourly report generator.

Generates:
1. A text summary of all currently live streams with stats.
2. A PNG graph per stream showing viewers over time.
3. A combined PNG comparing all live streams.
"""

import logging
import os
from datetime import datetime

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as ticker

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


def generate_stream_graph(stream: dict, report_dir: str) -> str:
    """
    Generate a viewer count graph for a single stream.
    Returns the path to the saved PNG.
    """
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
