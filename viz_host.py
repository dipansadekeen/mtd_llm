Try AI directly in your favourite apps … Use Gemini to generate drafts and refine content, plus get Gemini Pro with access to Google's next-gen AI for US$19.99 US$4.99 for 3 months
1
100%
"""
viz_host_fixed_pps_mbps.py
---------------------------
Live ONOS host plot with both Mbps and pps.

Each host subplot shows:
  rx_mbps, tx_mbps -> left y-axis
  rx_pps,  tx_pps  -> right y-axis

Usage:
  python viz_host_fixed_pps_mbps.py
  python viz_host_fixed_pps_mbps.py host_stats_onos.csv --interval 1
"""

import sys
import time
import argparse
from pathlib import Path
import re

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

MBPS_STATS   = ["rx_mbps", "tx_mbps"]
PPS_STATS    = ["rx_pps",  "tx_pps"]

MBPS_LABELS  = ["RX Mbps", "TX Mbps"]
PPS_LABELS   = ["RX pps",  "TX pps"]

MBPS_COLOURS = ["#4C9BE8", "#E8734C"]
PPS_COLOURS  = ["#4CE87A", "#E8D44C"]

MBPS_STYLES  = ["-", "-"]
PPS_STYLES   = ["--", "--"]

COLS = 4

MBPS_MAX = 1       # left axis starts at 0..1 Mbps, expands if needed
PPS_MAX  = 500     # right axis starts at 0..500 pps, expands if needed


def mac_to_host(mac_addr: str) -> str:
    """
    Converts Mininet-style MAC to host name:
      00:00:00:00:00:22 -> h34
      00:00:00:00:00:01 -> h1
    """
    mac_addr = str(mac_addr).upper()

    if re.match(r"^00:00:00:00:00:[0-9A-F]{2}$", mac_addr):
        return f"h{int(mac_addr.split(':')[-1], 16)}"

    return mac_addr[-8:]


def host_sort_key(host_mac: str):
    """Sort h1, h2, ..., h40 based on MAC suffix."""
    mac_addr = str(host_mac).upper()

    if re.match(r"^00:00:00:00:00:[0-9A-F]{2}$", mac_addr):
        return (0, int(mac_addr.split(":")[-1], 16))

    return (1, mac_addr)


def load_csv(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, parse_dates=["timestamp"])
    df.columns = df.columns.str.strip()

    required = ["timestamp", "host_ip", "host_mac", "rx_mbps", "tx_mbps", "rx_pps", "tx_pps"]
    missing = [c for c in required if c not in df.columns]

    if missing:
        sys.exit(f"[ERROR] Missing required columns: {missing}. Found columns: {list(df.columns)}")

    for col in ["rx_mbps", "tx_mbps", "rx_pps", "tx_pps"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    return df.sort_values("timestamp").reset_index(drop=True)


def build_host_labels(df, hosts):
    labels = []

    for host_mac in hosts:
        sub = df[df["host_mac"] == host_mac].sort_values("timestamp")
        latest_ip = sub["host_ip"].iloc[-1] if len(sub) else ""
        host_name = mac_to_host(host_mac)
        labels.append(f"{host_name} | {latest_ip}")

    return labels


def build_figure(hosts, host_labels):
    n = len(hosts)
    rows = int(np.ceil(n / COLS))

    fig, axes = plt.subplots(
        rows, COLS,
        figsize=(22, max(8, rows * 2.25)),
        facecolor="#0f1117",
        squeeze=False,
    )

    fig.suptitle(
        "ONOS Host Statistics — Mbps and pps",
        color="white", fontsize=13, fontweight="bold", y=0.995,
    )

    for idx in range(n, rows * COLS):
        r, c = divmod(idx, COLS)
        axes[r][c].set_visible(False)

    twin_axes = []

    for idx, name in enumerate(host_labels):
        r, c = divmod(idx, COLS)
        ax = axes[r][c]

        ax.set_facecolor("#1a1d27")
        ax.tick_params(colors="white", labelsize=5)
        ax.tick_params(axis="y", colors="#4C9BE8", labelsize=5)

        for spine in ax.spines.values():
            spine.set_edgecolor("#333")

        ax.set_title(name, color="white", fontsize=6.5, pad=2, fontweight="bold")
        ax.set_ylabel("Mbps", color="#4C9BE8", fontsize=5.5)
        ax.grid(True, color="#2a2d3a", linewidth=0.4, linestyle="--")

        ax2 = ax.twinx()
        ax2.tick_params(axis="y", colors="#4CE87A", labelsize=5)
        ax2.set_ylabel("pps", color="#4CE87A", fontsize=5.5)
        ax2.set_facecolor("none")

        for spine in ax2.spines.values():
            spine.set_edgecolor("#333")

        twin_axes.append(ax2)   # IMPORTANT: exactly one twin axis per host

    legend_elements = []

    for label, colour, style in zip(MBPS_LABELS, MBPS_COLOURS, MBPS_STYLES):
        legend_elements.append(
            plt.Line2D([0], [0], color=colour, lw=1.5, linestyle=style, label=label)
        )

    for label, colour, style in zip(PPS_LABELS, PPS_COLOURS, PPS_STYLES):
        legend_elements.append(
            plt.Line2D([0], [0], color=colour, lw=1.5, linestyle=style, label=label)
        )

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


def build_lines(axes, twin_axes, hosts):
    lines = []

    for idx in range(len(hosts)):
        r, c = divmod(idx, COLS)
        ax = axes[r][c]
        twin = twin_axes[idx]

        mbps_lines = []
        for colour, style in zip(MBPS_COLOURS, MBPS_STYLES):
            (line,) = ax.plot([], [], lw=1.2, color=colour, alpha=0.9, linestyle=style)
            mbps_lines.append(line)

        pps_lines = []
        for colour, style in zip(PPS_COLOURS, PPS_STYLES):
            (line,) = twin.plot([], [], lw=1.1, color=colour, alpha=0.9, linestyle=style)
            pps_lines.append(line)

        lines.append({"mbps": mbps_lines, "pps": pps_lines, "ax": ax, "twin": twin})

    return lines


def refresh_plot(df, hosts, lines, ts_text):
    timestamps = sorted(df["timestamp"].unique())
    ts_map = {ts: i for i, ts in enumerate(timestamps)}
    n_ts = len(timestamps)

    for idx, host_mac in enumerate(hosts):
        sub = df[df["host_mac"] == host_mac].copy()
        sub["x"] = sub["timestamp"].map(ts_map)
        sub = sub.sort_values("x")

        entry = lines[idx]
        ax = entry["ax"]
        twin = entry["twin"]

        for j, stat in enumerate(MBPS_STATS):
            entry["mbps"][j].set_data(sub["x"].values, sub[stat].values)

        for j, stat in enumerate(PPS_STATS):
            entry["pps"][j].set_data(sub["x"].values, sub[stat].values)

        ax.set_xlim(-0.5, max(1, n_ts - 0.5))
        twin.set_xlim(-0.5, max(1, n_ts - 0.5))

        mbps_vals = pd.concat([sub["rx_mbps"], sub["tx_mbps"]]).to_numpy(dtype=float)
        mbps_vals = mbps_vals[~np.isnan(mbps_vals)]
        mbps_max = max(MBPS_MAX, mbps_vals.max()) if len(mbps_vals) else MBPS_MAX
        ax.set_ylim(0, mbps_max * 1.05 if mbps_max > 0 else MBPS_MAX)

        pps_vals = pd.concat([sub["rx_pps"], sub["tx_pps"]]).to_numpy(dtype=float)
        pps_vals = pps_vals[~np.isnan(pps_vals)]
        pps_max = max(PPS_MAX, pps_vals.max()) if len(pps_vals) else PPS_MAX
        twin.set_ylim(0, pps_max * 1.05 if pps_max > 0 else PPS_MAX)

        step = max(1, n_ts // 4)
        tick_idx = list(range(0, n_ts, step))

        ax.set_xticks(tick_idx)
        ax.set_xticklabels(
            [pd.Timestamp(timestamps[i]).strftime("%H:%M:%S") for i in tick_idx],
            rotation=30, ha="right", fontsize=4.5, color="white",
        )

    if timestamps:
        ts_text.set_text(f"Latest: {pd.Timestamp(timestamps[-1])}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", nargs="?", default="host_stats_onos.csv")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="Seconds between CSV re-reads (default: 1)")
    args = parser.parse_args()

    csv_path = Path(args.csv)

    if not csv_path.exists():
        sys.exit(f"[ERROR] File not found: {csv_path}")

    df = load_csv(str(csv_path))

    hosts = sorted(df["host_mac"].unique(), key=host_sort_key)
    host_labels = build_host_labels(df, hosts)

    print(f"Found {len(hosts)} hosts.")

    fig, axes, twin_axes, ts_text = build_figure(hosts, host_labels)
    lines = build_lines(axes, twin_axes, hosts)

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

            refresh_plot(df, hosts, lines, ts_text)

            fig.canvas.draw()
            fig.canvas.flush_events()

        time.sleep(args.interval)

    print("Window closed — done.")


if __name__ == "__main__":
    main()