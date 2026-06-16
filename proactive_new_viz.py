# visualize_candidate_scores.py  (improved)
#
# Same pipeline as before (decide_ilp -> dataframes -> CSVs), but the figures
# are rebuilt so they actually communicate the decision:
#   * the 0/1 `selected` flag and the raw `score` are NO LONGER normalized into
#     the metric heatmap (mixing a binary flag and an unbounded score with
#     per-column min-max scaling made the old heatmap misleading);
#   * `selected` becomes an amber gutter rail; `score` gets its own strip;
#   * every heatmap cell is annotated with its RAW value;
#   * two new figures: a ranked-score bar chart and a benefit-vs-cost scatter
#     with a break-even line, both highlighting the optimizer's picks.

import os
import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

from proactive_ilp_decision_compact import decide_ilp

OUT_DIR = "candidate_score_visuals"
TOP_N = 20

# shared palette (matches the interactive console)
SIGNAL = "#F2B441"   # selected by the optimizer
COOL = "#5BA8C4"     # passed over
INK = "#10161e"
THERMAL = LinearSegmentedColormap.from_list(
    "thermal",
    ["#10263B", "#1C5566", "#2A9D8F", "#E9C46A", "#F4A259"],
)


def set_style():
    mpl.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": "#cdd5dd",
        "axes.linewidth": 0.8,
        "axes.grid": True,
        "grid.color": "#eef1f4",
        "font.size": 11,
        "axes.titlesize": 15,
        "axes.titleweight": "semibold",
        "xtick.color": "#3b4753",
        "ytick.color": "#3b4753",
        "axes.labelcolor": "#3b4753",
    })


def normalize_columns(df, cols):
    out = df.copy()
    for c in cols:
        s = pd.to_numeric(out[c], errors="coerce").fillna(0.0)
        mn, mx = s.min(), s.max()
        out[c] = 0.0 if mx == mn else (s - mn) / (mx - mn)
    return out


def _fmt(v):
    if pd.isna(v):
        return "-"
    av = abs(v)
    if av >= 1000:
        return f"{v/1000:.0f}k" if av >= 100000 else f"{v/1000:.1f}k"
    if float(v).is_integer():
        return f"{int(v)}"
    return f"{v:.3f}" if av < 1 else f"{v:.2f}"


# ---------------------------------------------------------------- heatmap
def plot_heatmap(df, label_col, metric_cols, title, out_file, top_n=TOP_N):
    if df.empty:
        print(f"[SKIP] No data for {title}")
        return

    df = df.head(top_n).reset_index(drop=True)
    metric_cols = [c for c in metric_cols if c in df.columns]
    labels = df[label_col].astype(str).tolist()
    sel = df["selected"].astype(int).values if "selected" in df else np.zeros(len(df))

    norm = normalize_columns(df[metric_cols], metric_cols)[metric_cols].values
    raw = df[metric_cols].values

    n, m = len(df), len(metric_cols)
    fig_h = max(5.5, 0.42 * n + 1.4)
    fig_w = max(10, 1.05 * m + 3)
    fig, (gax, hax, sax) = plt.subplots(
        1, 3, figsize=(fig_w, fig_h),
        gridspec_kw={"width_ratios": [0.14, m, 1.1], "wspace": 0.04},
    )

    # --- gutter: selected rail ---
    gax.imshow(sel.reshape(-1, 1), aspect="auto", cmap=
               LinearSegmentedColormap.from_list("g", ["#e9edf1", SIGNAL]),
               vmin=0, vmax=1)
    gax.set_xticks([]); gax.set_yticks(range(n))
    gax.set_yticklabels(
        [("● " if s else "  ") + lab for s, lab in zip(sel, labels)],
        fontsize=10)
    gax.set_title("sel", fontsize=10, color="#6b7783")
    for spine in gax.spines.values():
        spine.set_visible(False)

    # --- main metric heatmap (raw values annotated) ---
    hax.imshow(norm, aspect="auto", cmap=THERMAL, vmin=0, vmax=1)
    hax.set_yticks([])
    hax.set_xticks(range(m))
    hax.set_xticklabels(metric_cols, rotation=40, ha="right", fontsize=10)
    for i in range(n):
        for j in range(m):
            txt = "#1a1206" if norm[i, j] > 0.55 else "#e9eef3"
            hax.text(j, i, _fmt(raw[i, j]), ha="center", va="center",
                     fontsize=8, color=txt)
    hax.set_title(title, loc="left")
    for spine in hax.spines.values():
        spine.set_visible(False)

    # --- score strip ---
    if "score" in df:
        sc = df["score"].values.reshape(-1, 1)
        sn = (sc - sc.min()) / (sc.max() - sc.min() + 1e-9)
        sax.imshow(sn, aspect="auto", cmap=
                   LinearSegmentedColormap.from_list("s", ["#eef1f4", COOL]),
                   vmin=0, vmax=1)
        for i, v in enumerate(df["score"].values):
            sax.text(0, i, f"{v:.3f}", ha="center", va="center",
                     fontsize=8.5, color="#1f2a33", fontweight="bold")
        sax.set_xticks([0]); sax.set_xticklabels(["score"], fontsize=10)
    sax.set_yticks([])
    for spine in sax.spines.values():
        spine.set_visible(False)

    fig.tight_layout()
    fig.savefig(out_file, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"[SAVED] {out_file}")


# ---------------------------------------------------------------- rank bars
def plot_rank(df, label_col, title, out_file, top_n=TOP_N):
    if df.empty:
        return
    df = df.sort_values("score", ascending=True).tail(top_n).reset_index(drop=True)
    sel = df["selected"].astype(int).values if "selected" in df else np.zeros(len(df))
    colors = [SIGNAL if s else COOL for s in sel]

    fig, ax = plt.subplots(figsize=(10, max(5, 0.42 * len(df) + 1)))
    y = np.arange(len(df))
    ax.barh(y, df["score"].values, color=colors,
            edgecolor="white", linewidth=0.6, height=0.72)
    ax.axvline(0, color="#aab4bd", lw=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels([("● " if s else "") + str(l)
                        for s, l in zip(sel, df[label_col])], fontsize=10)
    for yi, v in zip(y, df["score"].values):
        ax.text(v + (0.02 if v >= 0 else -0.02), yi, f"{v:.3f}",
                va="center", ha="left" if v >= 0 else "right",
                fontsize=9, color="#33414c")
    ax.set_title(title, loc="left")
    ax.set_xlabel("score")
    ax.grid(axis="y", visible=False)
    handles = [plt.Rectangle((0, 0), 1, 1, color=SIGNAL),
               plt.Rectangle((0, 0), 1, 1, color=COOL)]
    ax.legend(handles, ["selected", "passed over"], frameon=False,
              loc="lower right", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_file, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"[SAVED] {out_file}")


# ---------------------------------------------------------------- scatter
def plot_tradeoff(df, label_col, title, out_file):
    if df.empty or "benefit" not in df or "cost" not in df:
        return
    sel = df["selected"].astype(int).values if "selected" in df else np.zeros(len(df))
    s = df["score"].values
    size = 60 + 260 * (np.abs(s) / (np.abs(s).max() + 1e-9))

    fig, ax = plt.subplots(figsize=(8.5, 7))
    lim = max(df["benefit"].max(), df["cost"].max()) * 1.08
    ax.plot([0, lim], [0, lim], "--", color="#9aa6b0", lw=1, zorder=1)
    ax.text(lim, lim, " benefit = cost", color="#9aa6b0", fontsize=9,
            ha="right", va="bottom")

    m0 = sel == 0
    ax.scatter(df["cost"][m0], df["benefit"][m0], s=size[m0],
               facecolors="none", edgecolors=COOL, linewidths=1.6,
               label="passed over", zorder=2)
    m1 = sel == 1
    ax.scatter(df["cost"][m1], df["benefit"][m1], s=size[m1],
               color=SIGNAL, edgecolors="#1a130a", linewidths=0.8,
               label="selected", zorder=3)
    # label the selected points
    for _, r in df[sel == 1].iterrows():
        ax.annotate(str(r[label_col]), (r["cost"], r["benefit"]),
                    fontsize=8, color="#33414c",
                    xytext=(5, 5), textcoords="offset points")

    ax.set_xlim(0, lim); ax.set_ylim(0, lim)
    ax.set_xlabel("cost"); ax.set_ylabel("benefit")
    ax.set_title(title, loc="left")
    ax.legend(frameon=False, loc="lower right", fontsize=9)
    fig.tight_layout()
    fig.savefig(out_file, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"[SAVED] {out_file}")


# ---------------------------------------------------------------- dataframes
def build_ip_dataframe(ip_candidates, selected_hosts):
    df = pd.DataFrame(ip_candidates)
    if df.empty:
        return df
    sel = set(selected_hosts)
    df["selected"] = df["host"].apply(lambda h: 1 if h in sel else 0)
    df["candidate"] = df.apply(
        lambda r: f"{'* ' if r['selected'] else ''}{r['host']}", axis=1)
    return df.sort_values("score", ascending=False).reset_index(drop=True)


def build_route_dataframe(route_candidates, selected_routes):
    df = pd.DataFrame(route_candidates)
    if df.empty:
        return df
    pairs = {(r["src"], r["dst"]) for r in selected_routes}
    df["selected"] = df.apply(
        lambda r: 1 if (r["src"], r["dst"]) in pairs else 0, axis=1)
    df["candidate"] = df.apply(
        lambda r: f"{'* ' if r['selected'] else ''}{r['src']}->{r['dst']}|opt{r['current_option']}",
        axis=1)
    return df.sort_values("score", ascending=False).reset_index(drop=True)


def summarize(name, df):
    if df.empty:
        print(f"\n{name}: (no candidates)")
        return
    sel = df[df["selected"] == 1]
    print(f"\n{name}: {len(df)} candidates, {len(sel)} selected")
    show = [c for c in ["candidate", "score", "benefit", "cost"] if c in df.columns]
    with pd.option_context("display.max_rows", 8, "display.width", 120):
        print(df[show].head(8).to_string(index=False))


# ---------------------------------------------------------------- main
def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    set_style()

    action, selected_hosts, selected_routes, details = decide_ilp()
    print("Selected action:", action)
    print("Selected IP hosts:", selected_hosts)
    print("Selected routes:", [(r["src"], r["dst"]) for r in selected_routes])

    ip_df = build_ip_dataframe(details.get("ip_candidates", []), selected_hosts)
    route_df = build_route_dataframe(details.get("route_candidates", []), selected_routes)

    # rounded CSVs for clean data display
    for df, fn in [(ip_df, "ip_candidates_scores.csv"),
                   (route_df, "route_candidates_scores.csv")]:
        path = os.path.join(OUT_DIR, fn)
        df.round(4).to_csv(path, index=False)
        print(f"[SAVED] {path}")

    summarize("IP hosts", ip_df)
    summarize("Routes", route_df)

    ip_metrics = ["benefit", "cost", "p_host", "traffic_risk", "monitor_score",
                  "ip_exposure", "grid_priority", "rx_pps", "tx_pps",
                  "rx_mbps", "tx_mbps"]
    route_metrics = ["benefit", "cost", "p_route", "route_exposure",
                     "link_usage", "link_monitor", "current_option"]

    P = lambda f: os.path.join(OUT_DIR, f)

    plot_rank(ip_df, "candidate", f"Top {TOP_N} IP hosts by score", P("ip_rank.png"))
    plot_tradeoff(ip_df, "host", "IP hosts: benefit vs cost", P("ip_tradeoff.png"))
    plot_heatmap(ip_df, "candidate", ip_metrics,
                 f"Top {TOP_N} IP candidates", P("ip_candidate_heatmap.png"))

    plot_rank(route_df, "candidate", f"Top {TOP_N} routes by score", P("route_rank.png"))
    plot_tradeoff(route_df, "candidate", "Routes: benefit vs cost", P("route_tradeoff.png"))
    plot_heatmap(route_df, "candidate", route_metrics,
                 f"Top {TOP_N} route candidates", P("route_candidate_heatmap.png"))


if __name__ == "__main__":
    main()