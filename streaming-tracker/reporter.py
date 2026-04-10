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

import numpy as np
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as ticker
from matplotlib.colors import LinearSegmentedColormap, to_rgba
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
from matplotlib.patches import Polygon, FancyBboxPatch, Rectangle
from PIL import Image

import database as db
from config import REPORTS_DIR

logger = logging.getLogger(__name__)

# --- Dark "Performance Report" theme ---
THEME = {
    "bg":        "#0d0a1f",  # Figure background (deep navy/indigo)
    "panel_bg":  "#15112b",  # Right-side metrics panel
    "panel_edge":"#2a2449",  # Subtle panel border
    "text":      "#ffffff",
    "text_dim":  "#8a85a8",
    "grid":      "#252040",
    "accent":    "#d946ef",  # Magenta fallback
}

# Channel colors — vivid palette that reads well on dark backgrounds
CHANNEL_COLORS = {
    "Luzu TV":          "#ff7a45",
    "Olga":             "#4da6ff",
    "Blender":          "#d946ef",
    "Gelatina":         "#22e07a",
    "Bondi Live":       "#ff5a6e",
    "Carajo":           "#ffb648",
    "La Casa Streaming":"#2bd4c4",
    "Vorterix":         "#7b9cff",
}
DEFAULT_COLOR = THEME["accent"]

_SPANISH_MONTHS = [
    "ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
    "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE",
]


def _format_spanish_date(dt: datetime) -> str:
    return f"{dt.day} DE {_SPANISH_MONTHS[dt.month - 1]} DE {dt.year}"


def _format_k(value: float) -> str:
    """Format numbers as '12k', '1.5k', '850', etc."""
    if value >= 10000:
        return f"{int(round(value / 1000))}k"
    if value >= 1000:
        return f"{value / 1000:.1f}k".replace(".0k", "k")
    return f"{int(value)}"


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


def _apply_gradient_fill(ax, times, viewers, color, y_max):
    """Vertical gradient fill under the curve (transparent at bottom -> color at top)."""
    times_num = mdates.date2num(times)

    gradient = np.linspace(0, 1, 256).reshape(-1, 1)
    cmap = LinearSegmentedColormap.from_list(
        "fade",
        [to_rgba(color, 0.0), to_rgba(color, 0.55)],
    )

    extent = [times_num[0], times_num[-1], 0, y_max]
    im = ax.imshow(
        gradient, aspect="auto", cmap=cmap, origin="lower",
        extent=extent, zorder=2,
    )

    # Clip to the area under the curve
    polygon_points = list(zip(times_num, viewers)) + [
        (times_num[-1], 0),
        (times_num[0], 0),
    ]
    polygon = Polygon(polygon_points, closed=True, facecolor="none", edgecolor="none")
    ax.add_patch(polygon)
    im.set_clip_path(polygon)


def _style_dark_axes(ax):
    """Apply the dark theme to an axes (ticks, spines, grid, background)."""
    ax.set_facecolor(THEME["bg"])
    ax.tick_params(colors=THEME["text_dim"], labelsize=9)
    ax.grid(True, alpha=0.25, color=THEME["grid"], linestyle="-", linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(THEME["grid"])
        ax.spines[side].set_linewidth(1)


def _draw_title_block(fig, channel_name: str, title: str, report_dt: datetime, color: str):
    """
    Title area: '<CANAL>: LIVESTREAM PERFORMANCE REPORT'
                 'PROGRAMA: "<title>"'
                 'INFORME DEL <fecha>'
    The channel name is drawn in color + italic, followed by the rest in white.
    """
    channel_upper = channel_name.upper()

    # First text: channel name (colored, italic)
    t1 = fig.text(
        0.055, 0.93, channel_upper,
        fontsize=22, fontweight="bold", color=color,
        fontstyle="italic", ha="left", va="top",
    )

    # Measure it so we can place the rest right after
    fig.canvas.draw()
    bbox = t1.get_window_extent(renderer=fig.canvas.get_renderer())
    bbox_fig = bbox.transformed(fig.transFigure.inverted())

    fig.text(
        bbox_fig.x1 + 0.003, 0.93, ": LIVESTREAM PERFORMANCE REPORT",
        fontsize=22, fontweight="bold", color=THEME["text"],
        ha="left", va="top",
    )

    # Program subtitle
    program_line = f'PROGRAMA: "{title}"'
    if len(program_line) > 85:
        program_line = program_line[:82] + '…"'
    fig.text(
        0.055, 0.86, program_line,
        fontsize=13, fontweight="bold", color=THEME["text"],
        ha="left", va="top",
    )

    # Date line
    fig.text(
        0.055, 0.815, f"INFORME DEL {_format_spanish_date(report_dt)}",
        fontsize=9, color=THEME["text_dim"],
        ha="left", va="top",
    )


def _draw_metrics_panel(fig, current: int, peak: int, avg: int, color: str,
                        thumb_img: Image.Image | None):
    """
    Right-side panel with: MÉTRICAS CLAVE / ACTUAL / PICO / PROMEDIO / thumbnail.
    """
    panel_left = 0.775
    panel_right = 0.975
    panel_top = 0.945
    panel_bottom = 0.055

    # Background box
    bg = FancyBboxPatch(
        (panel_left, panel_bottom),
        panel_right - panel_left,
        panel_top - panel_bottom,
        boxstyle="round,pad=0.005,rounding_size=0.012",
        facecolor=THEME["panel_bg"],
        edgecolor=THEME["panel_edge"],
        linewidth=1,
        transform=fig.transFigure,
        zorder=0,
    )
    fig.patches.append(bg)

    label_x = panel_left + 0.018

    # Header
    fig.text(
        label_x, panel_top - 0.025, "MÉTRICAS CLAVE",
        fontsize=11, fontweight="bold", color=THEME["text_dim"],
        ha="left", va="top",
    )

    # Horizontal divider under header
    fig.add_artist(Rectangle(
        (label_x, panel_top - 0.055),
        panel_right - label_x - 0.018, 0.0015,
        facecolor=THEME["panel_edge"], edgecolor="none",
        transform=fig.transFigure, zorder=1,
    ))

    # Metric cards: (label, value, value_color, y_label, y_value)
    metrics = [
        ("ACTUAL",   f"{current:,}", color,         panel_top - 0.09, panel_top - 0.14),
        ("PICO",     f"{peak:,}",    color,         panel_top - 0.24, panel_top - 0.29),
        ("PROMEDIO", f"{avg:,}",     THEME["text"], panel_top - 0.39, panel_top - 0.44),
    ]
    for label, value, val_color, y_label, y_value in metrics:
        fig.text(
            label_x, y_label, label,
            fontsize=10, fontweight="bold", color=THEME["text_dim"],
            ha="left", va="top",
        )
        fig.text(
            label_x, y_value, value,
            fontsize=26, fontweight="bold", color=val_color,
            ha="left", va="top",
        )

    # Thumbnail at bottom of panel
    if thumb_img is not None:
        thumb_width = panel_right - panel_left - 0.03
        thumb_height = 0.22
        thumb_x = panel_left + 0.015
        thumb_y = panel_bottom + 0.025

        thumb_ax = fig.add_axes([thumb_x, thumb_y, thumb_width, thumb_height])
        thumb_ax.imshow(thumb_img)
        thumb_ax.axis("off")
        for spine in thumb_ax.spines.values():
            spine.set_visible(False)


def generate_stream_graph(stream: dict, report_dir: str, snapshots: list[dict] | None = None) -> str:
    """
    Generate a "performance report" style graph for a single stream:
    dark theme, left-side gradient curve, right-side metrics panel + thumbnail.
    """
    if snapshots is None:
        snapshots = db.get_stream_snapshots(stream["id"])
    if len(snapshots) < 2:
        return ""

    times = [_parse_iso(s["recorded_at"]) for s in snapshots]
    viewers = [s["viewers"] for s in snapshots]

    channel_name = stream["channel_name"]
    title = stream["title"]
    color = CHANNEL_COLORS.get(channel_name, DEFAULT_COLOR)

    current = viewers[-1]
    peak = max(viewers)
    avg = sum(viewers) // len(viewers)
    y_max = max(peak * 1.15, 10)

    # Figure with dark background
    fig = plt.figure(figsize=(15, 6.5), facecolor=THEME["bg"])

    # --- Title block ---
    _draw_title_block(fig, channel_name, title, times[-1], color)

    # --- Graph axes (left side) ---
    # [left, bottom, width, height] in figure coords
    graph_ax = fig.add_axes([0.055, 0.11, 0.70, 0.62])
    _style_dark_axes(graph_ax)

    graph_ax.plot(times, viewers, color=color, linewidth=2.5, zorder=5)
    _apply_gradient_fill(graph_ax, times, viewers, color, y_max)

    # Endpoint dot (highlights current value)
    graph_ax.scatter(
        [times[-1]], [viewers[-1]],
        color=color, s=70, zorder=10,
        edgecolor="white", linewidth=1.2,
    )

    graph_ax.set_ylabel(
        "VISUALIZADORES", fontsize=10, color=THEME["text_dim"],
        fontweight="bold", labelpad=10,
    )
    graph_ax.set_xlabel(
        "HORA (UTC)", fontsize=10, color=THEME["text_dim"],
        fontweight="bold", labelpad=10,
    )
    graph_ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: _format_k(x)))
    graph_ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    graph_ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=10))
    graph_ax.set_xlim(times[0], times[-1])
    graph_ax.set_ylim(0, y_max)

    # --- Metrics panel (right side) ---
    thumb_img = _download_thumbnail(stream.get("thumbnail_url", ""))
    _draw_metrics_panel(fig, current, peak, avg, color, thumb_img)

    filename = f"{channel_name.replace(' ', '_')}_{stream['video_id']}.png"
    filepath = os.path.join(report_dir, filename)
    fig.savefig(filepath, dpi=150, facecolor=THEME["bg"], bbox_inches=None)
    plt.close(fig)

    logger.info(f"Graph saved: {filepath}")
    return filepath


def generate_combined_graph(streams: list[dict], report_dir: str) -> str:
    """
    Dark-theme comparative graph of all currently live streams.
    """
    if not streams:
        return ""

    fig = plt.figure(figsize=(15, 6.5), facecolor=THEME["bg"])
    ax = fig.add_axes([0.06, 0.12, 0.91, 0.76])
    _style_dark_axes(ax)

    any_data = False
    for stream in streams:
        snapshots = db.get_stream_snapshots(stream["id"])
        if len(snapshots) < 2:
            continue
        any_data = True

        times = [_parse_iso(s["recorded_at"]) for s in snapshots]
        viewers = [s["viewers"] for s in snapshots]
        color = CHANNEL_COLORS.get(stream["channel_name"], DEFAULT_COLOR)

        label = f'{stream["channel_name"]} ({viewers[-1]:,})'
        ax.plot(times, viewers, color=color, linewidth=2.2, label=label, zorder=5)
        ax.fill_between(times, viewers, alpha=0.08, color=color, zorder=1)

    if not any_data:
        plt.close(fig)
        return ""

    fig.text(
        0.06, 0.945, "COMPARATIVA DE AUDIENCIA — STREAMING EN VIVO",
        fontsize=16, fontweight="bold", color=THEME["text"], va="top",
    )

    ax.set_xlabel("HORA (UTC)", fontsize=10, color=THEME["text_dim"],
                  fontweight="bold", labelpad=8)
    ax.set_ylabel("VISUALIZADORES", fontsize=10, color=THEME["text_dim"],
                  fontweight="bold", labelpad=8)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: _format_k(x)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.set_ylim(bottom=0)

    legend = ax.legend(
        loc="upper left", fontsize=9, frameon=True,
        facecolor=THEME["panel_bg"], edgecolor=THEME["panel_edge"],
        labelcolor=THEME["text"],
    )
    for text in legend.get_texts():
        text.set_color(THEME["text"])

    filename = "comparativa_audiencia.png"
    filepath = os.path.join(report_dir, filename)
    fig.savefig(filepath, dpi=150, facecolor=THEME["bg"])
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

    fig = plt.figure(figsize=(16, 7.5), facecolor=THEME["bg"])
    ax = fig.add_axes([0.055, 0.25, 0.92, 0.60])
    _style_dark_axes(ax)

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
        ax.plot(times, viewers, color=color, linewidth=1.8, label=label, zorder=5)
        ax.fill_between(times, viewers, alpha=0.06, color=color, zorder=1)

    if not any_data:
        plt.close(fig)
        return ""

    fig.text(
        0.055, 0.945, f"TIMELINE DE AUDIENCIA — {day} (UTC)",
        fontsize=18, fontweight="bold", color=THEME["text"], va="top",
    )
    fig.text(
        0.055, 0.905, "Curvas de viewers de todos los programas del día",
        fontsize=10, color=THEME["text_dim"], va="top",
    )

    ax.set_xlabel("HORA DEL DÍA (UTC)", fontsize=10, color=THEME["text_dim"],
                  fontweight="bold", labelpad=8)
    ax.set_ylabel("VISUALIZADORES", fontsize=10, color=THEME["text_dim"],
                  fontweight="bold", labelpad=8)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: _format_k(x)))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
    ax.set_xlim(day_start, day_end)
    ax.set_ylim(bottom=0)

    legend = ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.18),
        ncol=2, fontsize=8, frameon=False,
    )
    for text in legend.get_texts():
        text.set_color(THEME["text"])

    filepath = os.path.join(report_dir, "timeline_dia.png")
    fig.savefig(filepath, dpi=150, facecolor=THEME["bg"])
    plt.close(fig)
    logger.info(f"Daily timeline graph saved: {filepath}")
    return filepath


def generate_daily_ranking_graph(streams: list[dict], day: str, report_dir: str) -> str:
    """Dark-theme horizontal bar chart ranking all streams by peak viewers."""
    if not streams:
        return ""

    ranked = sorted(
        [s for s in streams if (s.get("peak_viewers") or 0) > 0],
        key=lambda s: s["peak_viewers"],
        reverse=True,
    )
    if not ranked:
        return ""

    labels = [f'{s["channel_name"]} — {s["title"][:45]}' for s in ranked]
    peaks = [s["peak_viewers"] for s in ranked]
    colors = [CHANNEL_COLORS.get(s["channel_name"], DEFAULT_COLOR) for s in ranked]

    height = max(4.5, 0.50 * len(ranked) + 2.5)
    fig = plt.figure(figsize=(14, height), facecolor=THEME["bg"])
    ax = fig.add_axes([0.30, 0.10, 0.65, 0.80])
    _style_dark_axes(ax)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)

    bars = ax.barh(range(len(ranked)), peaks, color=colors, edgecolor="none", zorder=5)
    ax.set_yticks(range(len(ranked)))
    ax.set_yticklabels(labels, fontsize=9, color=THEME["text"])
    ax.invert_yaxis()
    ax.set_xlabel("PICO DE VIEWERS", fontsize=10, color=THEME["text_dim"],
                  fontweight="bold", labelpad=10)
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: _format_k(x)))

    fig.text(
        0.05, 0.96, f"RANKING DEL DÍA — {day} (UTC)",
        fontsize=18, fontweight="bold", color=THEME["text"], va="top",
    )
    fig.text(
        0.05, 0.925, "Programas ordenados por pico de audiencia",
        fontsize=10, color=THEME["text_dim"], va="top",
    )

    # Value labels
    max_peak = max(peaks)
    for bar, peak in zip(bars, peaks):
        ax.text(
            bar.get_width() + max_peak * 0.005,
            bar.get_y() + bar.get_height() / 2,
            f"{peak:,}",
            va="center", ha="left", fontsize=9,
            color=THEME["text"], fontweight="bold",
        )

    ax.set_xlim(0, max_peak * 1.12)

    filepath = os.path.join(report_dir, "ranking_dia.png")
    fig.savefig(filepath, dpi=150, facecolor=THEME["bg"])
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
