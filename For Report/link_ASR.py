#!/usr/bin/env python3
"""
plot_link_stats.py  —  Read link_stats_onos.csv and plot rx_mbps per link
                        with attack success/failure shading (threshold = 10 Mbps).

Usage:
    python plot_link_stats.py
    python plot_link_stats.py myfile.csv

Requirements:
    pip install pandas matplotlib
"""

import sys
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ---------------------------------------------------------------------------
# Config — edit here
# ---------------------------------------------------------------------------
FILE      = "link_stats_onos_5_5_no_mtd.csv"
THRESHOLD = 10.0       # Mbps — attack successful if rx_mbps >= this
METRIC    = "rx_mbps"  # column to plot: rx_mbps or tx_mbps
TOP_N     = 6          # plot only top N busiest links
# ---------------------------------------------------------------------------


def shorten(link_id):
    return (link_id
            .replace("of:000000000000000", "")
            .replace("of:0000000000000", "")
            .strip())


def load(path):
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df = df.sort_values("timestamp")
    t0 = df["timestamp"].min()
    df["t_sec"] = (df["timestamp"] - t0).dt.total_seconds()
    return df


def pick_top_links(df):
    peak = df.groupby("link_id")[METRIC].max().sort_values(ascending=False)
    return peak.head(TOP_N).index.tolist()


def print_summary(df):
    rows = []
    for link, g in df.groupby("link_id"):
        peak    = g[METRIC].max()
        avg     = g[METRIC].mean()
        success = "YES" if peak >= THRESHOLD else "no"
        rows.append({
            "link":   shorten(link),
            "peak":   round(peak, 3),
            "avg":    round(avg, 3),
            "attack": success,
        })
    summary = pd.DataFrame(rows).sort_values("peak", ascending=False)
    print("\n=== Attack Summary ===")
    print(summary.to_string(index=False))
    hits = summary["attack"].eq("YES").sum()
    print(f"\nThreshold : {THRESHOLD} Mbps")
    print(f"Successful: {hits} / {len(summary)} links\n")


def plot(df, top_links):
    n = len(top_links)
    fig, axes = plt.subplots(n, 1, figsize=(13, 3.5 * n), sharex=True)
    if n == 1:
        axes = [axes]

    fig.suptitle(
        f"ONOS link stats  |  attack threshold = {THRESHOLD} Mbps  "
        f"(top {n} links by peak {METRIC})",
        fontsize=12, y=1.005
    )

    for ax, link in zip(axes, top_links):
        sub = df[df["link_id"] == link].sort_values("t_sec")
        t   = sub["t_sec"].values
        y   = sub[METRIC].values

        ax.fill_between(t, 0, y, where=(y >= THRESHOLD),
                        color="#E24B4A", alpha=0.25, step="post")
        ax.fill_between(t, 0, y, where=(y < THRESHOLD),
                        color="#378ADD", alpha=0.10, step="post")

        ax.plot(t, y, color="#378ADD", linewidth=1.8)
        ax.axhline(THRESHOLD, color="#E24B4A", linewidth=1.1,
                   linestyle="--")

        in_attack = False
        for i in range(len(t)):
            if y[i] >= THRESHOLD and not in_attack:
                ax.axvline(t[i], color="#E24B4A", linewidth=0.8, alpha=0.4)
                in_attack = True
            elif y[i] < THRESHOLD:
                in_attack = False

        peak_val = y.max()
        status   = "ATTACK SUCCESS" if peak_val >= THRESHOLD else "below threshold"
        color    = "#A32D2D" if peak_val >= THRESHOLD else "#3B6D11"
        ax.text(0.99, 0.96, f"{status}  (peak {peak_val:.2f} Mbps)",
                transform=ax.transAxes, ha="right", va="top",
                fontsize=8.5, color=color, fontweight="bold")

        ax.set_ylabel(METRIC, fontsize=9)
        ax.set_title(shorten(link), fontsize=9, loc="left", pad=3)
        ax.set_ylim(bottom=0)
        ax.grid(alpha=0.13)

    axes[-1].set_xlabel("Time (s)", fontsize=10)

    handles = [
        mpatches.Patch(color="#378ADD", alpha=0.6, label=METRIC),
        mpatches.Patch(color="#E24B4A", alpha=0.35,
                       label=f"Attack success (>= {THRESHOLD} Mbps)"),
        mpatches.Patch(color="#378ADD", alpha=0.15, label="Below threshold"),
        plt.Line2D([0], [0], color="#E24B4A", linestyle="--",
                   label=f"Threshold {THRESHOLD} Mbps"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=4,
               fontsize=8.5, bbox_to_anchor=(0.5, -0.015), framealpha=0.6)

    plt.tight_layout()
    out = "link_stats_attack_plot.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved -> {out}")
    plt.show()


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else FILE
    df   = load(path)
    print_summary(df)
    top  = pick_top_links(df)
    plot(df, top)

# #!/usr/bin/env python3

# import sys
# import pandas as pd
# import matplotlib.pyplot as plt
# import numpy as np

# # ---------------------------------------------------------------------------
# # Config
# # ---------------------------------------------------------------------------
# WITH_MTD_FILE    = "link_stats_onos_5_5_mtd.csv"
# WITHOUT_MTD_FILE = "link_stats_onos_5_5_no_mtd.csv"

# THRESHOLD = 10.0
# METRIC    = "rx_mbps"   # rx_mbps or tx_mbps
# TOP_N     = 6
# # ---------------------------------------------------------------------------


# def shorten(link_id):
#     return (str(link_id)
#             .replace("of:000000000000000", "")
#             .replace("of:0000000000000", "")
#             .strip())


# def load(path, case_name):
#     df = pd.read_csv(path, parse_dates=["timestamp"])
#     df = df.sort_values("timestamp")
#     t0 = df["timestamp"].min()
#     df["t_sec"] = (df["timestamp"] - t0).dt.total_seconds()
#     df["case"] = case_name
#     return df


# def pick_top_links(df_all):
#     peak = df_all.groupby("link_id")[METRIC].max().sort_values(ascending=False)
#     return peak.head(TOP_N).index.tolist()


# def print_summary(df_all):
#     rows = []

#     for (case, link), g in df_all.groupby(["case", "link_id"]):
#         rows.append({
#             "case": case,
#             "link": shorten(link),
#             "peak_mbps": round(g[METRIC].max(), 3),
#             "avg_mbps": round(g[METRIC].mean(), 3),
#             "spike_over_10": "YES" if g[METRIC].max() >= THRESHOLD else "no",
#         })

#     summary = pd.DataFrame(rows).sort_values(["link", "case"])
#     print("\n=== Link Spike Summary ===")
#     print(summary.to_string(index=False))
#     print(f"\nReference threshold: {THRESHOLD} Mbps\n")


# def plot_compare(df_all, top_links):
#     n = len(top_links)
#     fig, axes = plt.subplots(n, 1, figsize=(13, 3.2 * n), sharex=True)

#     if n == 1:
#         axes = [axes]

#     fig.suptitle(
#         f"Link Utilization Spikes: With MTD vs Without MTD "
#         f"(Top {n} links by peak {METRIC})",
#         fontsize=13,
#         y=1.005
#     )

#     for ax, link in zip(axes, top_links):
#         for case_name in ["Without MTD", "With MTD"]:
#             sub = df_all[
#                 (df_all["link_id"] == link) &
#                 (df_all["case"] == case_name)
#             ].sort_values("t_sec")

#             if sub.empty:
#                 continue

#             ax.plot(
#                 sub["t_sec"],
#                 sub[METRIC],
#                 linewidth=2.0,
#                 marker="o",
#                 markersize=3,
#                 label=case_name
#             )

#         ax.axhline(
#             THRESHOLD,
#             linewidth=1.3,
#             linestyle=":",
#             label="10 Mbps threshold"
#         )

#         ax.set_title(shorten(link), fontsize=10, loc="left")
#         ax.set_ylabel("Mbps")
#         ax.set_ylim(bottom=0)
#         ax.grid(alpha=0.25)

#     axes[-1].set_xlabel("Time (s)")

#     handles, labels = axes[0].get_legend_handles_labels()
#     fig.legend(
#         handles,
#         labels,
#         loc="lower center",
#         ncol=3,
#         fontsize=9,
#         bbox_to_anchor=(0.5, -0.015)
#     )

#     plt.tight_layout()
#     out = "link_stats_mtd_vs_without_mtd.png"
#     plt.savefig(out, dpi=150, bbox_inches="tight")
#     print(f"Saved -> {out}")
#     plt.show()


# if __name__ == "__main__":
#     df_with = load(WITH_MTD_FILE, "With MTD")
#     df_without = load(WITHOUT_MTD_FILE, "Without MTD")

#     df_all = pd.concat([df_without, df_with], ignore_index=True)

#     print_summary(df_all)

#     top_links = pick_top_links(df_all)

#     plot_compare(df_all, top_links)