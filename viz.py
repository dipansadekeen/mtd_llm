# import pandas as pd
# import matplotlib.pyplot as plt

# HOST_CSV = "host_stats_onos.csv"
# LINK_CSV = "link_stats_onos.csv"

# WATCH_LINK_IDS = [
#     "of:0000000000000002:1 -> of:000000000000000b:4",
#     "of:0000000000000001:1 -> of:000000000000000b:1",
#     "of:0000000000000001:3 -> of:000000000000000d:1",
# ]

# WATCH_HOST_MACS = [
#     "00:00:00:00:00:02",
#     "00:00:00:00:00:0B",
# ]

# REFRESH_SEC = 2


# def safe_read(path):
#     try:
#         return pd.read_csv(path)
#     except Exception as e:
#         print(f"Could not read {path}: {e}")
#         return pd.DataFrame()


# def prepare(df):
#     if df.empty:
#         return df

#     df = df.copy()

#     if "timestamp" in df.columns:
#         df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
#         df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
#     else:
#         df["timestamp"] = range(len(df))

#     return df


# def plot_box(ax, df, id_col, value, title):
#     ax.clear()
#     ax.set_title(title, fontsize=9)

#     if df.empty:
#         ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
#         return

#     if id_col not in df.columns:
#         ax.text(0.5, 0.5, f"Missing column: {id_col}", ha="center", va="center", transform=ax.transAxes)
#         return

#     if id_col == "host_mac":
#         sub = df[df[id_col].astype(str).str.upper() == str(value).upper()].copy()
#     else:
#         sub = df[df[id_col].astype(str) == str(value)].copy()

#     if sub.empty:
#         ax.text(0.5, 0.5, "No match", ha="center", va="center", transform=ax.transAxes)
#         return

#     sub = sub.sort_values("timestamp")

#     ax.plot(sub["timestamp"], sub["tx_pps"], label="tx_pps")
#     ax.plot(sub["timestamp"], sub["rx_pps"], label="rx_pps")
#     ax.plot(sub["timestamp"], sub["tx_mbps"], label="tx_mbps")
#     ax.plot(sub["timestamp"], sub["rx_mbps"], label="rx_mbps")

#     ax.legend(fontsize=7)
#     ax.tick_params(axis="x", rotation=30)


# plt.ion()

# fig, axes = plt.subplots(3, 2, figsize=(16, 10))
# axes = axes.flatten()

# running = True

# def on_close(event):
#     global running
#     running = False

# fig.canvas.mpl_connect("close_event", on_close)

# while running and plt.fignum_exists(fig.number):
#     host_df = prepare(safe_read(HOST_CSV))
#     link_df = prepare(safe_read(LINK_CSV))

#     plot_box(axes[0], link_df, "link_id", WATCH_LINK_IDS[0], "Link A")
#     plot_box(axes[1], link_df, "link_id", WATCH_LINK_IDS[1], "Link B")
#     plot_box(axes[2], link_df, "link_id", WATCH_LINK_IDS[2], "Link C")

#     plot_box(axes[3], host_df, "host_mac", WATCH_HOST_MACS[0], "Host 02")
#     plot_box(axes[4], host_df, "host_mac", WATCH_HOST_MACS[1], "Host 0B")

#     axes[5].clear()
#     axes[5].set_title("Empty")
#     axes[5].axis("off")

#     plt.tight_layout()
#     plt.pause(REFRESH_SEC)

# plt.close("all")
# print("Plot window closed. Program stopped.")

"""
link_stats_live_plot.py
-----------------------
21 subplots in a 4-col x 6-row grid (one extra cell hidden).
Each subplot shows 4 lines for one link:
  rx_mbps, tx_mbps  → left axis (Mbps)
  rx_pps,  tx_pps   → right axis (pps, dashed)

Watches the CSV and appends new timestamps as they arrive.

Usage
-----
  python link_stats_live_plot.py
  python link_stats_live_plot.py /path/to/stats.csv
  python link_stats_live_plot.py stats.csv --interval 2
"""

import sys
import time
import argparse
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# STATS        = ["rx_mbps", "tx_mbps", "rx_pps",  "tx_pps"]
# STAT_LABELS  = ["RX Mbps", "TX Mbps", "RX pps",  "TX pps"]
# STAT_COLOURS = ["#4C9BE8", "#E8734C", "#4CE87A",  "#E8D44C"]
# STAT_STYLES  = ["-",       "-",       "--",        "--"]
STATS        = ["rx_mbps", "tx_mbps"]
STAT_LABELS  = ["RX Mbps", "TX Mbps"]
STAT_COLOURS = ["#4C9BE8", "#E8734C"]
STAT_STYLES  = ["-",       "-"]

COLS = 4
ROWS = 6   # 4×6 = 24 cells, 21 used, 3 hidden

MBPS_MAX = 15    # fixed upper limit for Mbps axis (expands if data exceeds it)
PPS_MAX  = 100   # fixed upper limit for pps axis (expands if data exceeds it)

def shorten_link(link_id: str) -> str:
    parts = link_id.split(" -> ")
    def short(dev):
        segs = dev.split(":")
        return f"{segs[-2].lstrip('0') or '0'}:{segs[-1]}"
    return " → ".join(short(p) for p in parts)


def load_csv(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, parse_dates=["timestamp"])
    return df.sort_values("timestamp").reset_index(drop=True)


def build_figure(links, short_names):
    n = len(links)

    fig, axes = plt.subplots(
        ROWS, COLS,
        figsize=(22, 14),
        facecolor="#0f1117",
        squeeze=False,
    )
    fig.suptitle(
        "ONOS Link Statistics — All Links",
        color="white", fontsize=13, fontweight="bold", y=0.995,
    )

    # hide unused cells
    for idx in range(n, ROWS * COLS):
        r, c = divmod(idx, COLS)
        axes[r][c].set_visible(False)

    twin_axes = []

    for idx, (link, name) in enumerate(zip(links, short_names)):
        r, c = divmod(idx, COLS)
        ax = axes[r][c]
        ax.set_facecolor("#1a1d27")
        ax.tick_params(colors="white", labelsize=5)
        ax.tick_params(axis='y', colors="#4C9BE8", labelsize=5)
        for spine in ax.spines.values():
            spine.set_edgecolor("#333")
        ax.set_title(name, color="white", fontsize=6.5, pad=2, fontweight="bold")
        ax.set_ylabel("Mbps", color="#4C9BE8", fontsize=5.5)
        ax.grid(True, color="#2a2d3a", linewidth=0.4, linestyle="--")

        # for only mbps
        # ax2 = ax.twinx()
        # ax2.tick_params(axis='y', colors="#4CE87A", labelsize=5)
        # ax2.set_ylabel("pps", color="#4CE87A", fontsize=5.5)
        # twin_axes.append(ax2)

        twin_axes.append(None) # added later


    # legend — top right, horizontal
    legend_elements = [
        plt.Line2D([0], [0], color=STAT_COLOURS[i], lw=1.5,
                   linestyle=STAT_STYLES[i], label=STAT_LABELS[i])
        for i in range(len(STATS))
    ]
    fig.legend(
        handles=legend_elements,
        loc="lower right",
        bbox_to_anchor=(0.98, 0.002),
        fontsize=7.5,
        framealpha=0.25,
        labelcolor="white",
        facecolor="#1a1d27",
        edgecolor="#444",
        ncol=4,
    )

    fig.tight_layout(rect=[0, 0.02, 1, 0.995], pad=1.2, h_pad=1.5, w_pad=1.0)
    ts_text = fig.text(0.01, 0.002, "", ha="left", color="#888", fontsize=7)
    return fig, axes, twin_axes, ts_text


# def build_lines(axes, twin_axes, links):
#     """lines[link_idx] = dict with line objects and axis refs."""
#     lines = []
#     for idx in range(len(links)):
#         r, c = divmod(idx, COLS)
#         ax   = axes[r][c]
#         twin = twin_axes[idx]

#         mbps_lines = []
#         for stat, col in zip(["rx_mbps", "tx_mbps"], STAT_COLOURS[:2]):
#             (line,) = ax.plot([], [], lw=1.2, color=col, alpha=0.9, linestyle="-")
#             mbps_lines.append(line)

#         pps_lines = []
#         for stat, col in zip(["rx_pps", "tx_pps"], STAT_COLOURS[2:]):
#             (line,) = twin.plot([], [], lw=1.2, color=col, alpha=0.9, linestyle="--")
#             pps_lines.append(line)

#         lines.append({"mbps": mbps_lines, "pps": pps_lines, "ax": ax, "twin": twin})
#     return lines
#  only mbps files
def build_lines(axes, twin_axes, links):
    lines = []
    for idx in range(len(links)):
        r, c = divmod(idx, COLS)
        ax   = axes[r][c]

        mbps_lines = []
        for col in STAT_COLOURS:
            (line,) = ax.plot([], [], lw=1.2, color=col, alpha=0.9, linestyle="-")
            mbps_lines.append(line)

        lines.append({"mbps": mbps_lines, "pps": [], "ax": ax, "twin": twin_axes[idx]})
    return lines

def refresh_plot(df, links, lines, ts_text):
    timestamps = sorted(df["timestamp"].unique())
    ts_map     = {ts: i for i, ts in enumerate(timestamps)}
    n_ts       = len(timestamps)
 
    for idx, link in enumerate(links):
        sub = df[df["link_id"] == link].copy()
        sub["x"] = sub["timestamp"].map(ts_map)
        sub = sub.sort_values("x")
 
        entry = lines[idx]
        ax    = entry["ax"]
        twin  = entry["twin"]
 
        # update lines
        for j, stat in enumerate(["rx_mbps", "tx_mbps"]):
            entry["mbps"][j].set_data(sub["x"].values, sub[stat].values)
        # for j, stat in enumerate(["rx_pps", "tx_pps"]):
        #     entry["pps"][j].set_data(sub["x"].values, sub[stat].values)
 
        # x limits
        ax.set_xlim(-0.5, max(1, n_ts - 0.5))
        # twin.set_xlim(-0.5, max(1, n_ts - 0.5))
 
        # y limits — Mbps (fixed at MBPS_MAX, expands only if data exceeds it)
        mbps_vals = pd.concat([sub["rx_mbps"], sub["tx_mbps"]]).values
        valid = mbps_vals[~np.isnan(mbps_vals)]
        mbps_max = max(MBPS_MAX, valid.max()) if len(valid) else MBPS_MAX
        ax.set_ylim(0, mbps_max)
 
        # # y limits — pps (fixed at PPS_MAX, expands only if data exceeds it)
        # pps_vals = pd.concat([sub["rx_pps"], sub["tx_pps"]]).values
        # valid = pps_vals[~np.isnan(pps_vals)]
        # pps_max = max(PPS_MAX, valid.max()) if len(valid) else PPS_MAX
        # twin.set_ylim(0, pps_max)
 
        # x tick labels (time only, no date)
        step = max(1, n_ts // 4)
        tick_idx = list(range(0, n_ts, step))
        ax.set_xticks(tick_idx)
        ax.set_xticklabels(
            [str(timestamps[i])[-8:] for i in tick_idx],
            rotation=30, ha="right", fontsize=4.5, color="white",
        )
 
    if timestamps:
        ts_text.set_text(f"Latest: {timestamps[-1]}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", nargs="?", default="link_stats_onos.csv")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="Seconds between CSV re-reads (default: 1)")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        sys.exit(f"[ERROR] File not found: {csv_path}")

    df          = load_csv(str(csv_path))
    links       = sorted(df["link_id"].unique())
    short_names = [shorten_link(l) for l in links]

    print(f"Found {len(links)} links.")

    fig, axes, twin_axes, ts_text = build_figure(links, short_names)
    lines = build_lines(axes, twin_axes, links)

    plt.ion()
    plt.show()

    seen_timestamps = set()
    print(f"Watching {csv_path}  (refresh every {args.interval}s) ...")
    print("Close the window to stop.\n")

    while plt.fignum_exists(fig.number):
        try:
            df = load_csv(str(csv_path))
        except Exception as e:
            print(f"[WARN] Could not read CSV: {e}")
            time.sleep(args.interval)
            continue

        new_ts = set(df["timestamp"].unique()) - seen_timestamps
        if new_ts:
            seen_timestamps.update(new_ts)
            print(f"  +{len(new_ts)} new timestamp(s) — total {len(seen_timestamps)}")
            refresh_plot(df, links, lines, ts_text)
            fig.canvas.draw()
            fig.canvas.flush_events()

        time.sleep(args.interval)

    print("Window closed — done.")


if __name__ == "__main__":
    main()