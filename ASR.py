import json
import matplotlib.pyplot as plt
import numpy as np

# Example structure after parsing your JSON rounds
rounds = [
    {"label": "R1", "decision": "rrm", "outcome": "neutral",
     "candidates": [
         {"id": "host:02", "type": "host", "before": 7.81, "after": [0.6, 0.7, 0.6, 63.76]},
         {"id": "link:0002→0008", "type": "link", "before": 16.90, "after": [2.38, 2.8, 2.38, 2.8]},
     ]},
    # ... more rounds
]

# Compute ASR per candidate
for r in rounds:
    for c in r["candidates"]:
        peak_after = max(c["after"])
        c["asr"] = min(peak_after / c["before"], 1.0) if c["before"] > 0 else 0

# --- Plot 1: ASR per round (bar chart) ---
round_labels = [r["label"] for r in rounds]
mean_asr = [np.mean([c["asr"] for c in r["candidates"]]) for r in rounds]
colors = ["green" if a < 0.3 else "orange" if a < 0.7 else "red" for a in mean_asr]

plt.figure(figsize=(10, 4))
plt.bar(round_labels, mean_asr, color=colors)
plt.axhline(0.5, linestyle="--", color="gray", label="50% threshold")
plt.ylabel("Attack Success Rate")
plt.title("ASR per Round")
plt.ylim(0, 1.1)
plt.legend()
plt.tight_layout()
plt.savefig("asr_per_round.png", dpi=150)
# python# --- Plot 2: ASR over time (after-points trajectory) ---
fig, axes = plt.subplots(2, 4, figsize=(14, 6))
for ax, r in zip(axes.flat, rounds):
    for c in r["candidates"]:
        normalized = [v / c["before"] for v in c["after"]]
        ax.plot(["t+1","t+2","t+3","t+4"], normalized,
                label=c["id"], marker="o", linewidth=1.5)
    ax.axhline(0.5, linestyle="--", color="gray", linewidth=0.8)
    ax.set_title(f"{r['label']} ({r['decision']})", fontsize=9)
    ax.set_ylim(0, None)
    ax.set_ylabel("Normalized pps")
plt.suptitle("Attack Rebound Trajectory per Round")
plt.tight_layout()
plt.savefig("asr_trajectory.png", dpi=150)
# python# --- Plot 3: Heatmap (candidate × round) ---
import seaborn as sns
import pandas as pd

rows = []
for r in rounds:
    for c in r["candidates"]:
        rows.append({"Round": r["label"], "Candidate": c["id"], "ASR": c["asr"]})

df = pd.DataFrame(rows).pivot(index="Candidate", columns="Round", values="ASR")
plt.figure(figsize=(10, 5))
sns.heatmap(df, annot=True, fmt=".2f", cmap="RdYlGn_r", vmin=0, vmax=1,
            linewidths=0.5, cbar_kws={"label": "ASR"})
plt.title("ASR Heatmap — Candidate × Round")
plt.tight_layout()
plt.savefig("asr_heatmap.png", dpi=150)