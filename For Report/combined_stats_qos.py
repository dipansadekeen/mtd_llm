#!/usr/bin/env python3
"""
compare_iperf3.py  —  Parse any number of iperf3 server-side UDP logs and plot:
                       1. Per-file summary bar charts (throughput, jitter, loss %)
                       2. Time-series lines per file + their average

Usage:
    python compare_iperf3.py                        # uses FILES list below
    python compare_iperf3.py f1.txt f2.txt f3.txt  # or pass files as arguments

Requirements:
    pip install matplotlib numpy
"""

import re
import sys
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

# ---------------------------------------------------------------------------
# >>>  SET YOUR FILES HERE (used when no command-line arguments are given)  <<<
# ---------------------------------------------------------------------------
FILES = [
    "capture_test10_qos_h3_to_h38_MTD.txt",
    "capture_test10_qos_h39_to_h2_MTD.txt",
    "capture_test8_qos_h2_to_h39__no_MTD.txt",
    "capture_test8_qos_h38_to_h3_no_MTD.txt",
]

# Optional: set custom short labels. If fewer labels than files, auto-fills.
LABELS = ["h38_mtd","h2_mtd", "h2_no_mtd", "h38_no_mtd"]   # e.g. ["Living Room", "Bedroom", "Office", "Garage"]

# ---------------------------------------------------------------------------
# Color palette — cycles automatically for any number of files
# ---------------------------------------------------------------------------
PALETTE = [
    "#378ADD", "#1D9E75", "#E24B4A", "#EF9F27",
    "#5348b7", "#D4537E", "#639922", "#0F6E56",
    "#BA7517", "#A32D2D", "#3C3489", "#085041",
]

# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------

INTERVAL_RE = re.compile(
    r"\[\s*\d+\]\s+"
    r"(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)\s+sec\s+"
    r"[\d.]+\s+\w+Bytes\s+"
    r"([\d.]+)\s+(\w+)bits/sec\s+"
    r"([\d.]+)\s+ms\s+"
    r"(-?\d+)/(\d+)"
)

SUMMARY_RE = re.compile(
    r"\[\s*\d+\]\s+0\.00-[\d.]+\s+sec\s+.*?"
    r"([\d.]+)\s+ms\s+"
    r"(\d+)/(\d+)\s+\(([\d.]+)%\)\s+receiver"
)


def parse_file(path):
    times, bitrates, jitters, losses = [], [], [], []
    summary = {}

    with open(path) as f:
        text = f.read()

    m = SUMMARY_RE.search(text)
    if m:
        summary = {
            "jitter_ms": float(m.group(1)),
            "lost":      int(m.group(2)),
            "total":     int(m.group(3)),
            "loss_pct":  float(m.group(4)),
        }

    for line in text.splitlines():
        m = INTERVAL_RE.search(line)
        if not m:
            continue
        t_start, t_end = float(m.group(1)), float(m.group(2))
        if t_end - t_start > 10:
            continue

        bitrate = float(m.group(3))
        unit    = m.group(4)
        jitter  = float(m.group(5))
        lost    = int(m.group(6))

        if unit == "K":
            bitrate /= 1000.0

        times.append((t_start + t_end) / 2)
        bitrates.append(bitrate)
        jitters.append(jitter)
        losses.append(max(0, lost))

    summary["avg_throughput_mbps"] = (
        sum(bitrates) / len(bitrates) if bitrates else 0.0
    )

    return times, bitrates, jitters, losses, summary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_labels(files, custom):
    labels = list(custom)
    for i in range(len(labels), len(files)):
        name = files[i].replace("\\", "/").split("/")[-1]
        labels.append(name)
    return labels


def interpolate_to_common(datasets_vals, n=300):
    result = []
    for times, vals in datasets_vals:
        if len(times) < 2:
            result.append(np.full(n, np.nan))
            continue
        t_common = np.linspace(min(times), max(times), n)
        result.append(np.interp(t_common, times, vals))
    t_axis = np.linspace(0, 300, n)
    return t_axis, result


def colors_for(n):
    return [PALETTE[i % len(PALETTE)] for i in range(n)]


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

def plot(files, labels):
    n = len(files)
    colors = colors_for(n)

    datasets = []
    for path in files:
        try:
            datasets.append(parse_file(path))
        except FileNotFoundError:
            print(f"ERROR: File not found — {path}")
            sys.exit(1)

    throughputs = [d[4].get("avg_throughput_mbps", 0) for d in datasets]
    jitter_vals = [d[4].get("jitter_ms", 0)           for d in datasets]
    loss_pcts   = [d[4].get("loss_pct", 0)            for d in datasets]

    t_ax, tp_i = interpolate_to_common([(d[0], d[1]) for d in datasets])
    _,    j_i  = interpolate_to_common([(d[0], d[2]) for d in datasets])
    _,    l_i  = interpolate_to_common([(d[0], d[3]) for d in datasets])

    fig = plt.figure(figsize=(16, 10))
    fig.suptitle(f"iperf3 UDP — {n}-File Comparison", fontsize=13, y=0.995)

    gs = fig.add_gridspec(
        3, 2, hspace=0.50, wspace=0.32,
        left=0.07, right=0.97, top=0.95, bottom=0.07
    )

    ax_bt = fig.add_subplot(gs[0, 0])
    ax_bj = fig.add_subplot(gs[1, 0])
    ax_bl = fig.add_subplot(gs[2, 0])
    ax_tt = fig.add_subplot(gs[0, 1])
    ax_tj = fig.add_subplot(gs[1, 1])
    ax_tl = fig.add_subplot(gs[2, 1])

    x     = np.arange(n)
    bar_w = max(0.2, min(0.6, 0.8 / n * 2))

    def bar_chart(ax, vals, title, ylabel, fmt="{:.2f}"):
        bars = ax.bar(x, vals, width=bar_w, color=colors, edgecolor="none")
        ax.set_title(title, fontsize=10, loc="left")
        ax.set_xticks(x)
        ax.set_xticklabels(
            labels,
            fontsize=max(6, 9 - n // 4),
            rotation=15 if n > 5 else 0,
            ha="right" if n > 5 else "center"
        )
        ax.set_ylim(bottom=0)
        ax.set_ylabel(ylabel)
        ax.grid(axis="y", alpha=0.15)
        pad = max(vals) * 0.01 if max(vals) > 0 else 0.01
        for bar, val in zip(bars, vals):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + pad,
                fmt.format(val),
                ha="center", va="bottom", fontsize=max(6, 8 - n // 4)
            )

    bar_chart(ax_bt, throughputs, "Avg Throughput",    "Mbps", "{:.2f}")
    bar_chart(ax_bj, jitter_vals, "End-to-End Jitter", "ms",   "{:.2f}")
    bar_chart(ax_bl, loss_pcts,   "Packet Loss",        "%",   "{:.2f}%")

    def ts_chart(ax, t, interp_list, title, ylabel):
        lw = max(0.7, 1.4 - n * 0.05)
        for i, vals in enumerate(interp_list):
            ax.plot(t, vals, color=colors[i], linewidth=lw,
                    alpha=0.55, label=labels[i])
        avg = np.nanmean(np.vstack(interp_list), axis=0)
        ax.plot(t, avg, color="#111", linewidth=2.0,
                linestyle="--", label="Average", zorder=5)
        ax.set_title(title, fontsize=10, loc="left")
        ax.set_ylabel(ylabel)
        ax.set_xlabel("Time (s)")
        ax.set_xlim(0, 300)
        ax.set_ylim(bottom=0)
        ax.grid(alpha=0.15)
        ncol = max(1, (n + 1) // 3)
        ax.legend(fontsize=7, ncol=ncol, framealpha=0.5)

    ts_chart(ax_tt, t_ax, tp_i, "Throughput over time",    "Mbps")
    ts_chart(ax_tj, t_ax, j_i,  "Jitter over time",        "ms")
    ts_chart(ax_tl, t_ax, l_i,  "Packet loss over time",   "lost pkts")

    def jitter_fmt(x, _):
        return f"{x/1000:.1f}s" if x >= 1000 else f"{x:.0f}ms"
    ax_tj.yaxis.set_major_formatter(ticker.FuncFormatter(jitter_fmt))

    out = "iperf3_comparison.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved -> {out}")
    plt.show()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    files  = sys.argv[1:] if len(sys.argv) > 1 else FILES
    labels = make_labels(files, LABELS)
    plot(files, labels)