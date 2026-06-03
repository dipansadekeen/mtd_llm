# module_llm_helper.py
from datetime import timedelta
from langchain_ollama import ChatOllama
import numpy as np
import pandas as pd
import requests, time, json
import json, re, time
from datetime import datetime
import csv
import importlib
import mtd_utils
import pandas as pd
import random
from ip_shuffle_endpoint import ip_shuffle_endpoint
from route_mutate_endpoint import route_shuffle_endpoint
from collections import deque
import os
from collections import defaultdict

# from mtd_utils import HostIPQueueManager, all_hosts
from mtd_utils import HostIPQueueManager, RouteHistoryManager, all_hosts
from module_path_selector import *
TOPOLOGY_FILE = "topology_s10.txt"


# ===================== CELL 1: build HOST-focused scene + store what will be shown to LLM =====================
HOST_CSV = "host_stats_onos.csv"          # <-- your host stats CSV
HOST_META = "host_metadata.json"    # <-- optional (mac->host mapping)
WINDOW_MINUTES = 5
TREND_POINTS = 10
SCENE_LOG = "llm_scene_log.jsonl"
DECISION_LOG = "llm_decision_log.jsonl"



LINK_CSV   = "link_stats_onos.csv"
WINDOW_MINUTES = 5
TREND_POINTS   = 10

SCENE_LOG    = "llm_scene_log_link.jsonl"
DECISION_LOG = "llm_decision_log_link.jsonl"

HOST_CSV = "host_stats_onos.csv"
LINK_CSV = "link_stats_onos.csv"
EXAMPLES_JSONL = "examples.jsonl"


def now_iso():
    return datetime.now().isoformat()

def build_host_stats(df, trend_points=10):
    """
    Input: df already filtered to the desired time window
    Output: list of host objects (one per MAC)
    """
    hosts = []
    for mac, g in df.groupby("host_mac"):
        g = g.sort_values("timestamp").tail(trend_points)

        tx_pps = g["tx_pps"].astype(float).values
        rx_pps = g["rx_pps"].astype(float).values

        tx_kbps = g["tx_mbps"].astype(float).values * 1000.0
        rx_kbps = g["rx_mbps"].astype(float).values * 1000.0

        if len(tx_pps) < 2:
            continue

        host_obj = {
            "mac": str(mac),

            "tx_pps_trend": [round(x, 2) for x in tx_pps.tolist()],
            "rx_pps_trend": [round(x, 2) for x in rx_pps.tolist()],

            "tx_kbps_trend": [round(x, 2) for x in tx_kbps.tolist()],
            "rx_kbps_trend": [round(x, 2) for x in rx_kbps.tolist()],

            "tx_pps_mean": round(float(np.mean(tx_pps)), 2),
            "rx_pps_mean": round(float(np.mean(rx_pps)), 2),

            "tx_pps_std": round(float(np.std(tx_pps)), 3),
            "rx_pps_std": round(float(np.std(rx_pps)), 3),

            "tx_pps_max": round(float(np.max(tx_pps)), 2),
            "rx_pps_max": round(float(np.max(rx_pps)), 2),

            "tx_kbps_mean": round(float(np.mean(tx_kbps)), 2),
            "rx_kbps_mean": round(float(np.mean(rx_kbps)), 2),

            "tx_kbps_std": round(float(np.std(tx_kbps)), 3),
            "rx_kbps_std": round(float(np.std(rx_kbps)), 3),

            "tx_kbps_max": round(float(np.max(tx_kbps)), 2),
            "rx_kbps_max": round(float(np.max(rx_kbps)), 2),

            "tx_pps_delta": round(float(tx_pps[-1] - tx_pps[-2]), 2),
            "rx_pps_delta": round(float(rx_pps[-1] - rx_pps[-2]), 2),

            "tx_kbps_delta": round(float(tx_kbps[-1] - tx_kbps[-2]), 2),
            "rx_kbps_delta": round(float(rx_kbps[-1] - rx_kbps[-2]), 2),
        }

        hosts.append(host_obj)

    return hosts




def now_iso():
    return datetime.now().isoformat()

def build_link_stats(df, trend_points=10):
    """
    Input: df already filtered to the desired time window
    Output: list of link objects (one per link_id)
    """
    links = []

    for link_id, g in df.groupby("link_id"):
        g = g.sort_values("timestamp").tail(trend_points)

        rx_pps = g["rx_pps"].astype(float).values
        tx_pps = g["tx_pps"].astype(float).values

        rx_kbps = g["rx_mbps"].astype(float).values * 1000.0
        tx_kbps = g["tx_mbps"].astype(float).values * 1000.0

        if len(rx_pps) < 2:
            continue

        link_obj = {
            "link_id": str(link_id),

            "rx_pps_trend": [round(x, 2) for x in rx_pps.tolist()],
            "tx_pps_trend": [round(x, 2) for x in tx_pps.tolist()],

            "rx_kbps_trend": [round(x, 2) for x in rx_kbps.tolist()],
            "tx_kbps_trend": [round(x, 2) for x in tx_kbps.tolist()],

            "rx_pps_mean": round(float(np.mean(rx_pps)), 2),
            "tx_pps_mean": round(float(np.mean(tx_pps)), 2),

            "rx_pps_std": round(float(np.std(rx_pps)), 3),
            "tx_pps_std": round(float(np.std(tx_pps)), 3),

            "rx_pps_max": round(float(np.max(rx_pps)), 2),
            "tx_pps_max": round(float(np.max(tx_pps)), 2),

            "rx_kbps_mean": round(float(np.mean(rx_kbps)), 2),
            "tx_kbps_mean": round(float(np.mean(tx_kbps)), 2),

            "rx_kbps_std": round(float(np.std(rx_kbps)), 3),
            "tx_kbps_std": round(float(np.std(tx_kbps)), 3),

            "rx_kbps_max": round(float(np.max(rx_kbps)), 2),
            "tx_kbps_max": round(float(np.max(tx_kbps)), 2),

            "rx_pps_delta": round(float(rx_pps[-1] - rx_pps[-2]), 2),
            "tx_pps_delta": round(float(tx_pps[-1] - tx_pps[-2]), 2),

            "rx_kbps_delta": round(float(rx_kbps[-1] - rx_kbps[-2]), 2),
            "tx_kbps_delta": round(float(tx_kbps[-1] - tx_kbps[-2]), 2),
        }

        links.append(link_obj)

    return links

def get_flagged_entities_with_trends(out1, out2):
    """
    Reads host/link LLM outputs, extracts flagged MACs and link_ids,
    then fetches last WINDOW_MINUTES of trend data only for those entities.

    Returns:
        host_report
        link_report
        flagged_macs
        flagged_links
        flagged_host_stats
        flagged_link_stats
    """

    # ---------- parse LLM outputs ----------
    host_report = json.loads(out1) if isinstance(out1, str) else out1
    link_report = json.loads(out2) if isinstance(out2, str) else out2

    flagged_macs = host_report.get("macs_to_shuffle", []) if host_report.get("decision") == "ip_shuffle" else []
    flagged_links = link_report.get("links_to_avoid", []) if link_report.get("decision") == "reroute" else []

    flagged_macs_set = set(flagged_macs)
    flagged_links_set = set(flagged_links)

    # ---------- host side ----------
    flagged_host_stats = []
    hdf = pd.read_csv(HOST_CSV)
    hdf["timestamp"] = pd.to_datetime(hdf["timestamp"], errors="coerce")
    hdf = hdf.dropna(subset=["timestamp"])

    if not hdf.empty and flagged_macs_set:
        h_end = hdf["timestamp"].max()
        h_min = h_end - pd.Timedelta(minutes=WINDOW_MINUTES)
        hdfw = hdf[hdf["timestamp"] >= h_min].copy()

        if not hdfw.empty:
            all_hosts = build_host_stats(hdfw, trend_points=TREND_POINTS)
            flagged_host_stats = [
                {
                    "mac": h["mac"],
                    "tx_pps_trend": h["tx_pps_trend"],
                    "rx_pps_trend": h["rx_pps_trend"],
                    "tx_kbps_trend": h["tx_kbps_trend"],
                    "rx_kbps_trend": h["rx_kbps_trend"]
                }
                for h in all_hosts if h["mac"] in flagged_macs_set
            ]

    # ---------- link side ----------
    flagged_link_stats = []
    ldf = pd.read_csv(LINK_CSV)
    ldf["timestamp"] = pd.to_datetime(ldf["timestamp"], errors="coerce")
    ldf = ldf.dropna(subset=["timestamp"])

    if not ldf.empty and flagged_links_set:
        l_end = ldf["timestamp"].max()
        l_min = l_end - pd.Timedelta(minutes=WINDOW_MINUTES)
        ldfw = ldf[ldf["timestamp"] >= l_min].copy()

        if not ldfw.empty:
            all_links = build_link_stats(ldfw, trend_points=TREND_POINTS)
            flagged_link_stats = [
                {
                    "link_id": l["link_id"],
                    "rx_pps_trend": l["rx_pps_trend"],
                    "tx_pps_trend": l["tx_pps_trend"],
                    "rx_kbps_trend": l["rx_kbps_trend"],
                    "tx_kbps_trend": l["tx_kbps_trend"]
                }
                for l in all_links if l["link_id"] in flagged_links_set
            ]

    return (
        host_report,
        link_report,
        flagged_macs,
        flagged_links,
        flagged_host_stats,
        flagged_link_stats
    )


# [
#  "gpt-oss:20b-cloud",
#  "qwen3.5:cloud",
#  "gemma4:26b-cloud",
#  "deepseek-v4-flash:cloud"
# ]
CLOUD_URL = "https://ollama.com/api/chat"
API_KEY = "23fbf0f676584a7983158ded37540f2c.9C4Aw8pI8jXQlC1vDCGIF7nb"
MODEL_NAME = "gpt-oss:20b-cloud"
# MODEL_NAME="deepseek-v4-flash:cloud"

def call_cloud_llm(prompt):

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "system",
                "content": "Return ONLY valid JSON. No text."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "stream": False,
        "options": {
            "temperature": 0,
            "top_p": 0.9
        }
    }

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    start = time.time()

    r = requests.post(CLOUD_URL, headers=headers, json=payload, timeout=300)
    r.raise_for_status()

    latency = time.time() - start

    out = r.json().get("message", {}).get("content", "").strip()

    return out, latency

def call_cloud_llm_judge(prompt,model_name_1):

    payload = {
        "model": model_name_1,
        "messages": [
            {
                "role": "system",
                "content": "Return ONLY valid JSON. No text."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "stream": False,
        "options": {
            "temperature": 0,
            "top_p": 0.9
        }
    }

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    start = time.time()

    r = requests.post(CLOUD_URL, headers=headers, json=payload, timeout=300)
    r.raise_for_status()

    latency = time.time() - start

    out = r.json().get("message", {}).get("content", "").strip()

    return out, latency



# #new ones handle link rerouting even if one or no hosts provided

# def path_selector(final_obj, hoplist_csv):
#     """
#     Returns only what do_rrm() needs:
#     - host1
#     - host2
#     - option_number

#     Rules:
#     - 2+ hosts: original behavior
#     - 1 host: anchor host, one pair per blocked link
#     - 0 host: one active pair per blocked link
#     """

#     print("\n running path selector")

#     def normalize_link(link_str):
#         left, right = [x.strip() for x in str(link_str).split("->")]
#         return tuple(sorted([left, right]))

#     def parse_path_links(path_str):
#         return [x.strip() for x in str(path_str).split(",") if str(x).strip()]

#     selected_macs = [str(x).upper() for x in final_obj.get("final_macs", [])]
#     blocked_links = [
#         normalize_link(str(x).strip())
#         for x in final_obj.get("final_links", [])
#         if str(x).strip()
#     ]

#     if not blocked_links:
#         return []

#     df = pd.read_csv(
#         hoplist_csv,
#         header=None,
#         names=["host1", "host2", "option_number", "hop_count", "src_mac", "dst_mac", "path"]
#     )

#     df["src_mac"] = df["src_mac"].astype(str).str.upper()
#     df["dst_mac"] = df["dst_mac"].astype(str).str.upper()
#     df["option_number"] = df["option_number"].astype(int)

#     df["pair_key"] = df.apply(
#         lambda r: tuple(sorted([str(r["host1"]), str(r["host2"])])),
#         axis=1
#     )

#     df["norm_path_links"] = df["path"].apply(
#         lambda p: [normalize_link(x) for x in parse_path_links(p)]
#     )

#     # route_history directly loaded here
#     activity_map = {}
#     try:
#         rh = pd.read_csv("route_history.csv")

#         rh["pair_key"] = rh.apply(
#             lambda r: tuple(sorted([str(r["host_a"]), str(r["host_b"])])),
#             axis=1
#         )

#         def activity_score(hist):
#             vals = []
#             for x in str(hist).split(","):
#                 x = x.strip()
#                 if not x:
#                     continue
#                 try:
#                     vals.append(int(x))
#                 except:
#                     vals.append(0)
#             return sum(1 for v in vals if v != 0)

#         rh["activity_score"] = rh["history"].apply(activity_score)
#         activity_map = dict(zip(rh["pair_key"], rh["activity_score"]))

#     except Exception as e:
#         print("[WARN] could not read route history:", e)

#     def blocked_used(norm_links):
#         return sum(1 for lk in norm_links if lk in blocked_links)

#     def choose_best_option(pair_df):
#         pair_df = pair_df.copy()
#         pair_df["blocked_used"] = pair_df["norm_path_links"].apply(blocked_used)

#         safe_df = pair_df[pair_df["blocked_used"] == 0].copy()
#         if not safe_df.empty:
#             safe_df = safe_df.sort_values(["hop_count", "option_number"])
#             return safe_df.iloc[0]

#         pair_df = pair_df.sort_values(["blocked_used", "hop_count", "option_number"])
#         return pair_df.iloc[0]

#     # --------------------------------------------------
#     # MODE A: 2+ hosts
#     # --------------------------------------------------
#     if len(selected_macs) >= 2:
#         selected_macs_set = set(selected_macs)

#         pair_df = df[
#             (df["src_mac"].isin(selected_macs_set)) &
#             (df["dst_mac"].isin(selected_macs_set))
#         ].copy()

#         if pair_df.empty:
#             return []

#         pair_df["blocked_used"] = pair_df["norm_path_links"].apply(blocked_used)
#         pair_df = pair_df.sort_values(
#             ["pair_key", "blocked_used", "hop_count", "option_number"]
#         )

#         best_df = pair_df.drop_duplicates(subset=["pair_key"], keep="first")

#         return [
#             {
#                 "host1": row["host1"],
#                 "host2": row["host2"],
#                 "option_number": int(row["option_number"])
#             }
#             for _, row in best_df.iterrows()
#         ]

#     # --------------------------------------------------
#     # MODE B/C: 1 host anchor OR 0 host
#     # one pair per blocked link
#     # --------------------------------------------------
#     anchor_mac = selected_macs[0] if len(selected_macs) == 1 else None

#     chosen_pairs = set()
#     candidates = []

#     for blk in blocked_links:
#         link_df = df[df["norm_path_links"].apply(lambda links: blk in links)].copy()

#         if link_df.empty:
#             continue

#         # prefer anchor host if one exists
#         if anchor_mac:
#             anchor_df = link_df[
#                 (link_df["src_mac"] == anchor_mac) | (link_df["dst_mac"] == anchor_mac)
#             ].copy()

#             if not anchor_df.empty:
#                 link_df = anchor_df

#         pair_rows = []
#         for pair_key, g in link_df.groupby("pair_key"):
#             act = activity_map.get(pair_key, 0)
#             best_row = choose_best_option(g)
#             best_blocked = blocked_used(best_row["norm_path_links"])

#             pair_rows.append({
#                 "pair_key": pair_key,
#                 "activity_score": act,
#                 "best_blocked": best_blocked,
#                 "best_hop_count": int(best_row["hop_count"])
#             })

#         if not pair_rows:
#             continue

#         rank_df = pd.DataFrame(pair_rows).sort_values(
#             ["activity_score", "best_blocked", "best_hop_count"],
#             ascending=[False, True, True]
#         )

#         picked_pair = None
#         for _, rr in rank_df.iterrows():
#             if rr["pair_key"] not in chosen_pairs:
#                 picked_pair = rr["pair_key"]
#                 break

#         if picked_pair is None:
#             picked_pair = rank_df.iloc[0]["pair_key"]

#         chosen_pairs.add(picked_pair)

#         pair_df = link_df[link_df["pair_key"] == picked_pair].copy()
#         best = choose_best_option(pair_df)

#         candidates.append({
#             "host1": best["host1"],
#             "host2": best["host2"],
#             "option_number": int(best["option_number"])
#         })

#     return candidates
# # #new ones handle link rerouting even if one or no hosts provided
# def path_selector(final_obj, hoplist_csv):
#     print("\n running path selector")

#     def normalize_link(link_str):
#         left, right = [x.strip() for x in str(link_str).split("->")]
#         return tuple(sorted([left, right]))

#     def parse_path_links(path_str):
#         return [x.strip() for x in str(path_str).split(",") if str(x).strip()]

#     selected_macs = [str(x).upper() for x in final_obj.get("final_macs", [])]
#     blocked_links = [
#         normalize_link(str(x).strip())
#         for x in final_obj.get("final_links", [])
#         if str(x).strip()
#     ]

#     if not blocked_links:
#         return []

#     df = pd.read_csv(
#         hoplist_csv,
#         header=None,
#         names=["host1", "host2", "option_number", "hop_count", "src_mac", "dst_mac", "path"]
#     )

#     df["src_mac"] = df["src_mac"].astype(str).str.upper()
#     df["dst_mac"] = df["dst_mac"].astype(str).str.upper()
#     df["option_number"] = df["option_number"].astype(int)

#     df["pair_key"] = df.apply(
#         lambda r: tuple(sorted([str(r["host1"]), str(r["host2"])])),
#         axis=1
#     )

#     df["norm_path_links"] = df["path"].apply(
#         lambda p: [normalize_link(x) for x in parse_path_links(p)]
#     )

#     # load route history
#     activity_map = {}
#     try:
#         rh = pd.read_csv("route_history.csv")
#         rh["pair_key"] = rh.apply(
#             lambda r: tuple(sorted([str(r["host_a"]), str(r["host_b"])])),
#             axis=1
#         )

#         def activity_score(hist):
#             vals = []
#             for x in str(hist).split(","):
#                 x = x.strip()
#                 if not x:
#                     continue
#                 try:
#                     vals.append(int(x))
#                 except:
#                     vals.append(0)
#             return sum(1 for v in vals if v != 0)

#         rh["activity_score"] = rh["history"].apply(activity_score)
#         activity_map = dict(zip(rh["pair_key"], rh["activity_score"]))

#     except Exception as e:
#         print("[WARN] could not read route history:", e)

#     blocked_links_set = set(blocked_links)

#     def blocked_used(norm_links):
#         return sum(1 for lk in norm_links if lk in blocked_links_set)

#     # -------------------------------------------------------
#     # GLOBAL STATE: tracks how many already-chosen paths
#     # use each link. This is the core fix.
#     # -------------------------------------------------------
#     link_load = {}  # link -> count of times used by chosen paths

#     def overlap_count(norm_links):
#         return sum(link_load.get(lk, 0) for lk in norm_links)

#     def register_path(norm_links):
#         for lk in norm_links:
#             link_load[lk] = link_load.get(lk, 0) + 1

#     def score_option(row):
#         """
#         Sort key for a path option:
#         1. fewer blocked links (hard constraint)
#         2. less overlap with already-chosen paths (global fix)
#         3. fewer hops
#         4. option number (tiebreak)
#         """
#         return (
#             blocked_used(row["norm_path_links"]),
#             overlap_count(row["norm_path_links"]),
#             int(row["hop_count"]),
#             int(row["option_number"])
#         )

#     def choose_best_option_global(pair_df):
#         pair_df = pair_df.copy()
#         pair_df["score"] = pair_df.apply(score_option, axis=1)
#         pair_df = pair_df.sort_values("score")
#         return pair_df.iloc[0]

#     def path_diversity(pair_df):
#         """
#         How many options does this pair have with zero blocked links?
#         Fewer = more constrained = should go first.
#         """
#         return pair_df[pair_df.apply(
#             lambda r: blocked_used(r["norm_path_links"]) == 0, axis=1
#         )].shape[0]

#     # --------------------------------------------------
#     # MODE A: 2+ hosts
#     # --------------------------------------------------
#     if len(selected_macs) >= 2:
#         selected_macs_set = set(selected_macs)

#         pair_df = df[
#             (df["src_mac"].isin(selected_macs_set)) &
#             (df["dst_mac"].isin(selected_macs_set))
#         ].copy()

#         if pair_df.empty:
#             return []

#         # sort pairs by diversity: most constrained first
#         pair_keys = list(pair_df["pair_key"].unique())
#         pair_keys.sort(key=lambda pk: path_diversity(pair_df[pair_df["pair_key"] == pk]))

#         results = []
#         for pk in pair_keys:
#             group = pair_df[pair_df["pair_key"] == pk]
#             best = choose_best_option_global(group)
#             register_path(best["norm_path_links"])  # update link_load
#             results.append({
#                 "host1": best["host1"],
#                 "host2": best["host2"],
#                 "option_number": int(best["option_number"])
#             })

#         return results

#     # --------------------------------------------------
#     # MODE B/C: 1 host anchor OR 0 host
#     # --------------------------------------------------
#     anchor_mac = selected_macs[0] if len(selected_macs) == 1 else None

#     chosen_pairs = set()
#     candidates = []

#     for blk in blocked_links:
#         link_df = df[df["norm_path_links"].apply(lambda links: blk in links)].copy()

#         if link_df.empty:
#             continue

#         if anchor_mac:
#             anchor_df = link_df[
#                 (link_df["src_mac"] == anchor_mac) | (link_df["dst_mac"] == anchor_mac)
#             ].copy()
#             if not anchor_df.empty:
#                 link_df = anchor_df

#         # rank pairs by activity + how constrained they are
#         pair_rows = []
#         for pair_key, g in link_df.groupby("pair_key"):
#             act = activity_map.get(pair_key, 0)
#             diversity = path_diversity(g)
#             best_row = choose_best_option_global(g)

#             pair_rows.append({
#                 "pair_key": pair_key,
#                 "activity_score": act,
#                 "diversity": diversity,
#                 "best_blocked": blocked_used(best_row["norm_path_links"]),
#                 "best_overlap": overlap_count(best_row["norm_path_links"]),
#                 "best_hop_count": int(best_row["hop_count"])
#             })

#         if not pair_rows:
#             continue

#         rank_df = pd.DataFrame(pair_rows).sort_values(
#             ["diversity", "activity_score", "best_blocked", "best_overlap", "best_hop_count"],
#             ascending=[True, False, True, True, True]
#         )

#         picked_pair = None
#         for _, rr in rank_df.iterrows():
#             if rr["pair_key"] not in chosen_pairs:
#                 picked_pair = rr["pair_key"]
#                 break

#         if picked_pair is None:
#             picked_pair = rank_df.iloc[0]["pair_key"]

#         chosen_pairs.add(picked_pair)

#         group = link_df[link_df["pair_key"] == picked_pair].copy()
#         best = choose_best_option_global(group)
#         register_path(best["norm_path_links"])  # update link_load

#         candidates.append({
#             "host1": best["host1"],
#             "host2": best["host2"],
#             "option_number": int(best["option_number"])
#         })

#     return candidates
# # new module handles repetitive paths as well. global solution provider.
# ''' New path selector:  Greedy algorithm — yes, globally established, textbook CS
# Link state / resource reservation — yes, used in OSPF, RSVP-TE (traffic engineering protocols)
# Constrained Shortest Path First (CSPF) — this is the closest named algorithm to what we're doing. It's used in MPLS traffic engineering. It picks shortest paths while respecting constraints (in our case, blocked links + load)'''

# # update 3: ensure variety if same routes are selected
# def path_selector(final_obj, hoplist_csv):
#     print("\n running path selector")

#     def normalize_link(link_str):
#         left, right = [x.strip() for x in str(link_str).split("->")]
#         return tuple(sorted([left, right]))

#     def parse_path_links(path_str):
#         return [x.strip() for x in str(path_str).split(",") if str(x).strip()]

#     selected_macs = [str(x).upper() for x in final_obj.get("final_macs", [])]
#     blocked_links = [
#         normalize_link(str(x).strip())
#         for x in final_obj.get("final_links", [])
#         if str(x).strip()
#     ]

#     if not blocked_links:
#         return []

#     df = pd.read_csv(
#         hoplist_csv,
#         header=None,
#         names=["host1", "host2", "option_number", "hop_count", "src_mac", "dst_mac", "path"]
#     )

#     df["src_mac"] = df["src_mac"].astype(str).str.upper()
#     df["dst_mac"] = df["dst_mac"].astype(str).str.upper()
#     df["option_number"] = df["option_number"].astype(int)

#     df["pair_key"] = df.apply(
#         lambda r: tuple(sorted([str(r["host1"]), str(r["host2"])])),
#         axis=1
#     )

#     df["norm_path_links"] = df["path"].apply(
#         lambda p: [normalize_link(x) for x in parse_path_links(p)]
#     )

#     # load route history
#     activity_map = {}
#     try:
#         rh = pd.read_csv("route_history.csv")
#         rh["pair_key"] = rh.apply(
#             lambda r: tuple(sorted([str(r["host_a"]), str(r["host_b"])])),
#             axis=1
#         )

#         def activity_score(hist):
#             vals = []
#             for x in str(hist).split(","):
#                 x = x.strip()
#                 if not x:
#                     continue
#                 try:
#                     vals.append(int(x))
#                 except:
#                     vals.append(0)
#             return sum(1 for v in vals if v != 0)

#         rh["activity_score"] = rh["history"].apply(activity_score)
#         activity_map = dict(zip(rh["pair_key"], rh["activity_score"]))

#     except Exception as e:
#         print("[WARN] could not read route history:", e)

#     blocked_links_set = set(blocked_links)

#     def blocked_used(norm_links):
#         return sum(1 for lk in norm_links if lk in blocked_links_set)

#     # global link reservation
#     link_load = {}

#     def overlap_count(norm_links):
#         return sum(link_load.get(lk, 0) for lk in norm_links)

#     def register_path(norm_links):
#         for lk in norm_links:
#             link_load[lk] = link_load.get(lk, 0) + 1

#     def score_option(row):
#         return (
#             blocked_used(row["norm_path_links"]),
#             overlap_count(row["norm_path_links"]),
#             int(row["hop_count"]),
#             int(row["option_number"])
#         )

#     def choose_best_option_global(pair_df):
#         """
#         Strict preference order:
#         1. zero blocked + zero overlap
#         2. zero blocked + minimum overlap
#         3. minimum blocked + zero overlap
#         4. global fallback by score
#         """
#         pair_df = pair_df.copy()

#         # stage 1: no blocked links AND no overlap
#         stage1 = pair_df[
#             pair_df["norm_path_links"].apply(
#                 lambda links: blocked_used(links) == 0 and overlap_count(links) == 0
#             )
#         ]
#         if not stage1.empty:
#             stage1["score"] = stage1.apply(score_option, axis=1)
#             return stage1.sort_values("score").iloc[0]

#         # stage 2: no blocked links, allow overlap only if necessary
#         stage2 = pair_df[
#             pair_df["norm_path_links"].apply(
#                 lambda links: blocked_used(links) == 0
#             )
#         ]
#         if not stage2.empty:
#             stage2["score"] = stage2.apply(score_option, axis=1)
#             return stage2.sort_values("score").iloc[0]

#         # stage 3: allow blocked links, but still prefer zero overlap
#         stage3 = pair_df[
#             pair_df["norm_path_links"].apply(
#                 lambda links: overlap_count(links) == 0
#             )
#         ]
#         if not stage3.empty:
#             stage3["score"] = stage3.apply(score_option, axis=1)
#             return stage3.sort_values("score").iloc[0]

#         # final fallback: unavoidable reuse
#         pair_df["score"] = pair_df.apply(score_option, axis=1)
#         return pair_df.sort_values("score").iloc[0]

#     def path_diversity(pair_df):
#         """
#         Count how many options are both:
#         - zero blocked
#         - zero overlap with already chosen paths
#         fewer = more constrained = choose earlier
#         """
#         return pair_df[pair_df["norm_path_links"].apply(
#             lambda links: blocked_used(links) == 0 and overlap_count(links) == 0
#         )].shape[0]

#     # --------------------------------------------------
#     # MODE A: 2+ hosts
#     # --------------------------------------------------
#     if len(selected_macs) >= 2:
#         selected_macs_set = set(selected_macs)

#         pair_df = df[
#             (df["src_mac"].isin(selected_macs_set)) &
#             (df["dst_mac"].isin(selected_macs_set))
#         ].copy()

#         if pair_df.empty:
#             return []

#         pair_keys = list(pair_df["pair_key"].unique())
#         pair_keys.sort(key=lambda pk: (
#             path_diversity(pair_df[pair_df["pair_key"] == pk]),
#             pair_df[pair_df["pair_key"] == pk]["hop_count"].min()
#         ))

#         results = []
#         for pk in pair_keys:
#             group = pair_df[pair_df["pair_key"] == pk]
#             best = choose_best_option_global(group)
#             register_path(best["norm_path_links"])
#             results.append({
#                 "host1": best["host1"],
#                 "host2": best["host2"],
#                 "option_number": int(best["option_number"])
#             })

#         return results

#     # --------------------------------------------------
#     # MODE B/C: 1 host anchor OR 0 host
#     # --------------------------------------------------
#     anchor_mac = selected_macs[0] if len(selected_macs) == 1 else None

#     chosen_pairs = set()
#     candidates = []

#     for blk in blocked_links:
#         link_df = df[df["norm_path_links"].apply(lambda links: blk in links)].copy()

#         if link_df.empty:
#             continue

#         if anchor_mac:
#             anchor_df = link_df[
#                 (link_df["src_mac"] == anchor_mac) | (link_df["dst_mac"] == anchor_mac)
#             ].copy()
#             if not anchor_df.empty:
#                 link_df = anchor_df

#         pair_rows = []
#         for pair_key, g in link_df.groupby("pair_key"):
#             act = activity_map.get(pair_key, 0)
#             best_row = choose_best_option_global(g)

#             pair_rows.append({
#                 "pair_key": pair_key,
#                 "activity_score": act,
#                 "diversity": path_diversity(g),
#                 "best_blocked": blocked_used(best_row["norm_path_links"]),
#                 "best_overlap": overlap_count(best_row["norm_path_links"]),
#                 "best_hop_count": int(best_row["hop_count"])
#             })

#         if not pair_rows:
#             continue

#         rank_df = pd.DataFrame(pair_rows).sort_values(
#             ["diversity", "best_overlap", "best_blocked", "activity_score", "best_hop_count"],
#             ascending=[True, True, True, False, True]
#         )

#         picked_pair = None
#         for _, rr in rank_df.iterrows():
#             if rr["pair_key"] not in chosen_pairs:
#                 picked_pair = rr["pair_key"]
#                 break

#         if picked_pair is None:
#             picked_pair = rank_df.iloc[0]["pair_key"]

#         chosen_pairs.add(picked_pair)

#         group = link_df[link_df["pair_key"] == picked_pair].copy()
#         best = choose_best_option_global(group)
#         register_path(best["norm_path_links"])

#         candidates.append({
#             "host1": best["host1"],
#             "host2": best["host2"],
#             "option_number": int(best["option_number"])
#         })

#     return candidates
# # update3: ensure variety if same paths are chosen
# update 3.1 ; generate global solution + flow pairing
#flow:
import itertools
import requests


import itertools
import requests


def get_onos_active_pairs(final_obj,
                          topology_file="topology_s10.txt",
                          onos_url="http://localhost:8181/onos/v1/flows",
                          auth=("onos", "rocks")):
    """
    Returns active MAC pairs only.

    Output example:
    [
        {
            "host1": "h2",
            "host2": "h39",
            "src_mac": "00:00:00:00:00:02",
            "dst_mac": "00:00:00:00:00:27"
        }
    ]

    If no ONOS active pair is found, returns [].
    """

    selected_macs = [str(m).upper() for m in final_obj.get("final_macs", [])]

    # topology_s10.txt is comma-separated:
    # h2, 10.0.0.2/24, 00:00:00:00:00:02
    mac_to_host = {}

    with open(topology_file, "r") as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            parts = [x.strip() for x in line.split(",")]

            if len(parts) >= 3 and parts[0].startswith("h"):
                mac_to_host[parts[2].upper()] = parts[0]

    try:
        flows = requests.get(onos_url, auth=auth, timeout=3).json().get("flows", [])
    except Exception as e:
        print("[WARN] Could not read ONOS flows:", e)
        return []

    active_pairs = []

    for a, b in itertools.combinations(selected_macs, 2):
        found = False

        for flow in flows:
            src, dst = None, None

            for c in flow.get("selector", {}).get("criteria", []):
                if c.get("type") == "ETH_SRC":
                    src = str(c.get("mac", "")).upper()
                elif c.get("type") == "ETH_DST":
                    dst = str(c.get("mac", "")).upper()

            direct = src == a and dst == b
            reverse = src == b and dst == a

            if direct or reverse:
                packets = int(flow.get("packets", 0))
                bytes_ = int(flow.get("bytes", 0))

                if packets > 0 or bytes_ > 0:
                    found = True
                    break

        if found:
            active_pairs.append({
                "host1": mac_to_host.get(a, a),
                "host2": mac_to_host.get(b, b),
                "src_mac": a,
                "dst_mac": b
            })

    # new
    print("[DEBUG] flow device:", flow.get("deviceId"))
    print("[DEBUG] state:", flow.get("state"))
    print("[DEBUG] packets:", flow.get("packets"))
    print("[DEBUG] criteria:", flow.get("selector", {}).get("criteria", []))
    # new

    print("[INFO] active MAC pairs from ONOS:")
    for p in active_pairs:
        print(f"  {p['host1']}({p['src_mac']}) <-> {p['host2']}({p['dst_mac']})")

    return active_pairs
#flow picking

def get_onos_active_pairs(final_obj=None, topology_file="topology_s10.txt"):
    import requests

    url = "http://localhost:8181/onos/v1/flows"
    r = requests.get(url, auth=("onos", "rocks"), timeout=5)
    data = r.json()

    active_pairs = []
    seen = set()

    for flow in data.get("flows", []):
        state = flow.get("state")
        packets = int(flow.get("packets", 0))

        if state != "ADDED":
            continue

        if packets <= 0:
            continue

        criteria = flow.get("selector", {}).get("criteria", [])

        src_mac = None
        dst_mac = None
        eth_type = None

        for c in criteria:
            ctype = c.get("type")

            if ctype == "ETH_TYPE":
                eth_type = c.get("ethType")

            elif ctype == "ETH_SRC":
                src_mac = c.get("mac") or c.get("value")

            elif ctype == "ETH_DST":
                dst_mac = c.get("mac") or c.get("value")

        # Skip ARP-only flows
        if eth_type == "0x806" and not src_mac and not dst_mac:
            continue

        # Keep only flows where both MACs exist
        if src_mac and dst_mac:
            src_mac = src_mac.upper()
            dst_mac = dst_mac.upper()

            key = tuple(sorted([src_mac, dst_mac]))

            if key not in seen:
                seen.add(key)
                active_pairs.append({
                    "src_mac": src_mac,
                    "dst_mac": dst_mac,
                    "packets": packets,
                    "device": flow.get("deviceId")
                })

    print("[INFO] active MAC pairs from ONOS:")
    for p in active_pairs:
        print(f"   {p['src_mac']} <-> {p['dst_mac']} packets={p['packets']} device={p['device']}")

    return active_pairs


# def path_selector(final_obj, hoplist_csv, max_blocked_use=2):
#     print("\n running path selector")

#     def norm_link(s):
#         a, b = [x.strip() for x in str(s).split("->")]
#         return tuple(sorted([a, b]))

#     def path_links(s):
#         return [x.strip() for x in str(s).split(",") if x.strip()]

#     def hnum(h):
#         return int(str(h).lower().replace("h", ""))

#     def order_hosts(a, b):
#         a, b = str(a), str(b)
#         return (a, b) if hnum(a) <= hnum(b) else (b, a)

#     def pair_key(a, b):
#         return tuple(sorted([str(a), str(b)], key=hnum))

#     macs = [str(x).upper() for x in final_obj.get("final_macs", [])]
#     blocked = [norm_link(x) for x in final_obj.get("final_links", []) if str(x).strip()]
#     if not blocked:
#         return []

#     blocked_set = set(blocked)

#     df = pd.read_csv(
#         hoplist_csv,
#         header=None,
#         names=["host1", "host2", "option_number", "hop_count", "src_mac", "dst_mac", "path"]
#     )

#     df["src_mac"] = df["src_mac"].astype(str).str.upper()
#     df["dst_mac"] = df["dst_mac"].astype(str).str.upper()
#     df["option_number"] = df["option_number"].astype(int)
#     df["hop_count"] = df["hop_count"].astype(int)
#     df["pair_key"] = df.apply(lambda r: pair_key(r["host1"], r["host2"]), axis=1)
#     df["norm_path_links"] = df["path"].apply(lambda p: [norm_link(x) for x in path_links(p)])

#     activity = {}
#     try:
#         rh = pd.read_csv("route_history.csv")
#         rh["pair_key"] = rh.apply(lambda r: pair_key(r["host_a"], r["host_b"]), axis=1)

#         def act_score(hist):
#             vals = []
#             for x in str(hist).split(","):
#                 try:
#                     vals.append(int(x.strip()))
#                 except:
#                     vals.append(0)
#             return sum(v != 0 for v in vals)

#         rh["activity_score"] = rh["history"].apply(act_score)
#         activity = dict(zip(rh["pair_key"], rh["activity_score"]))
#     except Exception as e:
#         print("[WARN] could not read route history:", e)

#     link_load, blocked_load, path_load = {}, {}, {}

#     def sig(links):
#         return tuple(sorted(links))

#     def blocked_used(links):
#         return sum(lk in blocked_set for lk in links)

#     def blocked_overuse(links):
#         return sum(lk in blocked_set and blocked_load.get(lk, 0) >= max_blocked_use for lk in links)

#     def overlap(links):
#         return sum(link_load.get(lk, 0) for lk in links)

#     def same_path(links):
#         return path_load.get(sig(links), 0)

#     def register(links):
#         for lk in links:
#             link_load[lk] = link_load.get(lk, 0) + 1
#             if lk in blocked_set:
#                 blocked_load[lk] = blocked_load.get(lk, 0) + 1
#         path_load[sig(links)] = path_load.get(sig(links), 0) + 1

#     def score(row):
#         links = row["norm_path_links"]
#         return (
#             blocked_overuse(links),
#             blocked_used(links),
#             same_path(links),
#             overlap(links),
#             int(row["hop_count"]),
#             int(row["option_number"])
#         )

#     def best_option(g):
#         g = g.copy()

#         stages = [
#             g[g["norm_path_links"].apply(lambda x: blocked_used(x) == 0 and overlap(x) == 0 and same_path(x) == 0)],
#             g[g["norm_path_links"].apply(lambda x: blocked_used(x) == 0)],
#             g[g["norm_path_links"].apply(lambda x: blocked_overuse(x) == 0 and overlap(x) == 0)],
#             g
#         ]

#         for st in stages:
#             if not st.empty:
#                 st = st.copy()
#                 st["score"] = st.apply(score, axis=1)
#                 return st.sort_values("score").iloc[0]

#     def diversity(g):
#         return g[g["norm_path_links"].apply(
#             lambda x: blocked_used(x) == 0 and overlap(x) == 0 and same_path(x) == 0
#         )].shape[0]

#     def pack(row):
#         h1, h2 = order_hosts(row["host1"], row["host2"])
#         return {"host1": h1, "host2": h2, "option_number": int(row["option_number"])}

#     def sort_results(rows):
#         return sorted(rows, key=lambda r: (hnum(r["host1"]), hnum(r["host2"])))

#     # MODE A: 2+ hosts passed | using active flow
#     if len(macs) >= 2:
#         active_pairs = get_onos_active_pairs(final_obj, topology_file="topology_s10.txt")

#         # no flow do nothing but thanks for information | new
#         if not active_pairs:
#             print("[INFO] no ONOS active pair found; skipping RRM")
#             return []
#         # no flow do nothing but thanks for information | new

#         if active_pairs:
#             allowed = {tuple(sorted([p["src_mac"], p["dst_mac"]])) for p in active_pairs}
#             pair_df = df[df.apply(lambda r: tuple(sorted([r["src_mac"], r["dst_mac"]])) in allowed, axis=1)].copy()
#             print("[INFO] using ONOS active pairs only")
#         else:
#             pair_df = df[df["src_mac"].isin(macs) & df["dst_mac"].isin(macs)].copy()
#             print("[WARN] no ONOS active pair found, using default combinations")

#         if pair_df.empty:
#             return []

#         keys = list(pair_df["pair_key"].unique())
#         keys.sort(key=lambda pk: (
#             diversity(pair_df[pair_df["pair_key"] == pk]),
#             pair_df[pair_df["pair_key"] == pk]["hop_count"].min(),
#             hnum(pk[0]), hnum(pk[1])
#         ))

#         out = []
#         for pk in keys:
#             best = best_option(pair_df[pair_df["pair_key"] == pk])
#             register(best["norm_path_links"])
#             out.append(pack(best))

#         return sort_results(out)

#     # MODE B/C: one anchor host or only congested links
#     anchor = macs[0] if len(macs) == 1 else None
#     chosen, out = set(), []

#     for blk in blocked:
#         link_df = df[df["norm_path_links"].apply(lambda x: blk in x)].copy()
#         if link_df.empty:
#             continue

#         if anchor:
#             tmp = link_df[(link_df["src_mac"] == anchor) | (link_df["dst_mac"] == anchor)].copy()
#             if not tmp.empty:
#                 link_df = tmp

#         rows = []
#         for pk, g in link_df.groupby("pair_key"):
#             b = best_option(g)
#             rows.append({
#                 "pair_key": pk,
#                 "diversity": diversity(g),
#                 "overuse": blocked_overuse(b["norm_path_links"]),
#                 "overlap": overlap(b["norm_path_links"]),
#                 "blocked": blocked_used(b["norm_path_links"]),
#                 "same_path": same_path(b["norm_path_links"]),
#                 "activity": activity.get(pk, 0),
#                 "hop": int(b["hop_count"])
#             })

#         if not rows:
#             continue

#         rank = pd.DataFrame(rows).sort_values(
#             ["diversity", "overuse", "overlap", "blocked", "same_path", "activity", "hop"],
#             ascending=[True, True, True, True, True, False, True]
#         )

#         picked = next((r["pair_key"] for _, r in rank.iterrows() if r["pair_key"] not in chosen), rank.iloc[0]["pair_key"])
#         chosen.add(picked)

#         best = best_option(link_df[link_df["pair_key"] == picked])
#         register(best["norm_path_links"])
#         out.append(pack(best))

#     return sort_results(out)
# # update 3.1



# def path_selector(final_obj, hoplist_csv, max_blocked_use=2):
#     print("\n running path selector")

#     def norm_link(s):
#         a, b = [x.strip() for x in str(s).split("->")]
#         return tuple(sorted([a, b]))

#     def path_links(s):
#         return [x.strip() for x in str(s).split(",") if x.strip()]

#     def hnum(h):
#         return int(str(h).lower().replace("h", ""))

#     def order_hosts(a, b):
#         a, b = str(a), str(b)
#         return (a, b) if hnum(a) <= hnum(b) else (b, a)

#     def pair_key(a, b):
#         return tuple(sorted([str(a), str(b)], key=hnum))

#     macs = [str(x).upper() for x in final_obj.get("final_macs", [])]
#     blocked = [norm_link(x) for x in final_obj.get("final_links", []) if str(x).strip()]
#     if not blocked:
#         return []

#     blocked_set = set(blocked)

#     # ============================================================
#     # Get active ONOS flows first
#     # ============================================================
#     active_pairs = get_onos_active_pairs(final_obj, topology_file="topology_s10.txt")
#     if not active_pairs:
#         print("[INFO] no ONOS active pair found; skipping RRM")
#         return []

#     def mac_pair_tuple(a, b):
#         return tuple(sorted([str(a).upper(), str(b).upper()]))

#     allowed_all = {
#         mac_pair_tuple(p["src_mac"], p["dst_mac"])
#         for p in active_pairs
#     }

#     active_mac_set = set()
#     for p in active_pairs:
#         active_mac_set.add(str(p["src_mac"]).upper())
#         active_mac_set.add(str(p["dst_mac"]).upper())

#     passed_set = set(macs)
#     passed_active = passed_set & active_mac_set

#     if macs and not passed_active:
#         print("[WARN] none of the passed hosts are active; using default active-flow distribution")


#     # df = pd.read_csv(
#     #     hoplist_csv,
#     #     header=None,
#     #     names=["host1", "host2", "option_number", "hop_count", "src_mac", "dst_mac", "path"]
#     # )

#     # df["src_mac"] = df["src_mac"].astype(str).str.upper()
#     # df["dst_mac"] = df["dst_mac"].astype(str).str.upper()
#     # df["option_number"] = df["option_number"].astype(int)
#     # df["hop_count"] = df["hop_count"].astype(int)
#     # df["pair_key"] = df.apply(lambda r: pair_key(r["host1"], r["host2"]), axis=1)
#     # df["norm_path_links"] = df["path"].apply(lambda p: [norm_link(x) for x in path_links(p)])


#     # flow based solution # newly added
#     # ============================================================
#     # Read hoplist and immediately keep only active flow pairs
#     # ============================================================
#     df = pd.read_csv(
#         hoplist_csv,
#         header=None,
#         names=["host1", "host2", "option_number", "hop_count", "src_mac", "dst_mac", "path"],
#         usecols=[0, 1, 2, 3, 4, 5, 6]
#     )

#     df["src_mac"] = df["src_mac"].astype(str).str.upper()
#     df["dst_mac"] = df["dst_mac"].astype(str).str.upper()

#     df["mac_pair"] = df.apply(
#         lambda r: mac_pair_tuple(r["src_mac"], r["dst_mac"]),
#         axis=1
#     )

#     df = df[df["mac_pair"].isin(allowed_all)].copy()

#     if df.empty:
#         print("[INFO] no hoplist routes found for active ONOS flows; skipping RRM")
#         return []

#     df["option_number"] = df["option_number"].astype(int)
#     df["hop_count"] = df["hop_count"].astype(int)

#     # Exclude option 0 from RRM path selection.
#     # option 0 = default/current/no-mutation path, so it should not be selected as an RRM candidate.
#     df = df[df["option_number"] != 0].copy()

#     if df.empty:
#         print("[INFO] no non-zero route options available after excluding option 0; skipping RRM")
#         return []

#     df["pair_key"] = df.apply(lambda r: pair_key(r["host1"], r["host2"]), axis=1)

#     # Only now normalize path links, after active-flow filtering
#     df["norm_path_links"] = df["path"].apply(
#         lambda p: [norm_link(x) for x in path_links(p)]
#     )
#     ##ends


#     activity = {}
#     try:
#         rh = pd.read_csv("route_history.csv")
#         rh["pair_key"] = rh.apply(lambda r: pair_key(r["host_a"], r["host_b"]), axis=1)

#         def act_score(hist):
#             vals = []
#             for x in str(hist).split(","):
#                 try:
#                     vals.append(int(x.strip()))
#                 except:
#                     vals.append(0)
#             return sum(v != 0 for v in vals)

#         rh["activity_score"] = rh["history"].apply(act_score)
#         activity = dict(zip(rh["pair_key"], rh["activity_score"]))
#     except Exception as e:
#         print("[WARN] could not read route history:", e)

#     link_load, blocked_load, path_load = {}, {}, {}

#     def sig(links):
#         return tuple(sorted(links))

#     def blocked_used(links):
#         return sum(lk in blocked_set for lk in links)

#     def blocked_overuse(links):
#         return sum(lk in blocked_set and blocked_load.get(lk, 0) >= max_blocked_use for lk in links)

#     def overlap(links):
#         return sum(link_load.get(lk, 0) for lk in links)

#     def same_path(links):
#         return path_load.get(sig(links), 0)

#     def register(links):
#         for lk in links:
#             link_load[lk] = link_load.get(lk, 0) + 1
#             if lk in blocked_set:
#                 blocked_load[lk] = blocked_load.get(lk, 0) + 1
#         path_load[sig(links)] = path_load.get(sig(links), 0) + 1

#     def score(row):
#         links = row["norm_path_links"]
#         return (
#             blocked_overuse(links),
#             blocked_used(links),
#             same_path(links),
#             overlap(links),
#             int(row["hop_count"]),
#             int(row["option_number"])
#         )

#     def best_option(g):
#         g = g.copy()

#         stages = [
#             g[g["norm_path_links"].apply(lambda x: blocked_used(x) == 0 and overlap(x) == 0 and same_path(x) == 0)],
#             g[g["norm_path_links"].apply(lambda x: blocked_used(x) == 0)],
#             g[g["norm_path_links"].apply(lambda x: blocked_overuse(x) == 0 and overlap(x) == 0)],
#             g
#         ]

#         for st in stages:
#             if not st.empty:
#                 st = st.copy()
#                 st["score"] = st.apply(score, axis=1)
#                 return st.sort_values("score").iloc[0]

#     def diversity(g):
#         return g[g["norm_path_links"].apply(
#             lambda x: blocked_used(x) == 0 and overlap(x) == 0 and same_path(x) == 0
#         )].shape[0]

#     def pack(row):
#         h1, h2 = order_hosts(row["host1"], row["host2"])
#         return {"host1": h1, "host2": h2, "option_number": int(row["option_number"])}

#     def sort_results(rows):
#         return sorted(rows, key=lambda r: (hnum(r["host1"]), hnum(r["host2"])))


#     # MODE A: 2+ hosts passed | using active flow
#     #already considered active pair
#     # if len(macs) >= 2:
#     #     active_pairs = get_onos_active_pairs(final_obj, topology_file="topology_s10.txt")

#     #     # no flow do nothing but thanks for information | new
#     #     if not active_pairs:
#     #         print("[INFO] no ONOS active pair found; skipping RRM")
#     #         return []
#     #     # no flow do nothing but thanks for information | new

#     #     if active_pairs:
#     #         allowed = {tuple(sorted([p["src_mac"], p["dst_mac"]])) for p in active_pairs}
#     #         pair_df = df[df.apply(lambda r: tuple(sorted([r["src_mac"], r["dst_mac"]])) in allowed, axis=1)].copy()
#     #         print("[INFO] using ONOS active pairs only")
#     #     else:
#     #         pair_df = df[df["src_mac"].isin(macs) & df["dst_mac"].isin(macs)].copy()
#     #         print("[WARN] no ONOS active pair found, using default combinations")

#     #     if pair_df.empty:
#     #         return []

#     #     keys = list(pair_df["pair_key"].unique())
#     #     keys.sort(key=lambda pk: (
#     #         diversity(pair_df[pair_df["pair_key"] == pk]),
#     #         pair_df[pair_df["pair_key"] == pk]["hop_count"].min(),
#     #         hnum(pk[0]), hnum(pk[1])
#     #     ))

#     #     out = []
#     #     for pk in keys:
#     #         best = best_option(pair_df[pair_df["pair_key"] == pk])
#     #         register(best["norm_path_links"])
#     #         out.append(pack(best))

#     #     return sort_results(out)

#     # MODE A: 2+ hosts passed | already filtered by active flows
#     if len(macs) >= 2:
#         if passed_active:
#             pair_df = df[
#                 (df["src_mac"].isin(passed_active)) |
#                 (df["dst_mac"].isin(passed_active))
#             ].copy()

#             if pair_df.empty:
#                 print("[WARN] passed active hosts not found in hoplist; using default active-flow distribution")
#                 pair_df = df.copy()
#             else:
#                 print("[INFO] using active flows involving passed active hosts")
#         else:
#             print("[INFO] using default active-flow distribution")
#             pair_df = df.copy()

#         if pair_df.empty:
#             return []

#         keys = list(pair_df["pair_key"].unique())
#         keys.sort(key=lambda pk: (
#             diversity(pair_df[pair_df["pair_key"] == pk]),
#             pair_df[pair_df["pair_key"] == pk]["hop_count"].min(),
#             hnum(pk[0]),
#             hnum(pk[1])
#         ))

#         out = []
#         for pk in keys:
#             best = best_option(pair_df[pair_df["pair_key"] == pk])
#             if best is None:
#                 continue
#             register(best["norm_path_links"])
#             out.append(pack(best))

#         return sort_results(out)

#     # # MODE B/C: one anchor host or only congested links
#     # anchor = macs[0] if len(macs) == 1 else None
#     # chosen, out = set(), []

#     # for blk in blocked:
#     #     link_df = df[df["norm_path_links"].apply(lambda x: blk in x)].copy()
#     #     if link_df.empty:
#     #         continue

#     #     # if anchor: # newly removed
#     #     if anchor and anchor in active_mac_set:
#     #         tmp = link_df[(link_df["src_mac"] == anchor) | (link_df["dst_mac"] == anchor)].copy()
#     #         if not tmp.empty:
#     #             link_df = tmp

#     #     rows = []
#     #     for pk, g in link_df.groupby("pair_key"):
#     #         b = best_option(g)
#     #         rows.append({
#     #             "pair_key": pk,
#     #             "diversity": diversity(g),
#     #             "overuse": blocked_overuse(b["norm_path_links"]),
#     #             "overlap": overlap(b["norm_path_links"]),
#     #             "blocked": blocked_used(b["norm_path_links"]),
#     #             "same_path": same_path(b["norm_path_links"]),
#     #             "activity": activity.get(pk, 0),
#     #             "hop": int(b["hop_count"])
#     #         })

#     #     if not rows:
#     #         continue

#     #     rank = pd.DataFrame(rows).sort_values(
#     #         ["diversity", "overuse", "overlap", "blocked", "same_path", "activity", "hop"],
#     #         ascending=[True, True, True, True, True, False, True]
#     #     )

#     #     picked = next((r["pair_key"] for _, r in rank.iterrows() if r["pair_key"] not in chosen), rank.iloc[0]["pair_key"])
#     #     chosen.add(picked)

#     #     best = best_option(link_df[link_df["pair_key"] == picked])
#     #     register(best["norm_path_links"])
#     #     out.append(pack(best))

#     # return sort_results(out)

#     # MODE B/C: one anchor host or only congested links
#     anchor = macs[0] if len(macs) == 1 else None
#     chosen, out = set(), []
#     MAX_ACTIVE_FLOWS_TOTAL = 4

#     # Active pairs whose candidate routes contain ANY congested link
#     affected_df = df[df["norm_path_links"].apply(
#         lambda links: any(blk in links for blk in blocked)
#     )].copy()

#     if affected_df.empty:
#         print("[INFO] no active flow route options touch any congested link")
#         return []

#     # If one active anchor host is provided, prioritize its affected flows
#     if anchor and anchor in active_mac_set:
#         tmp = affected_df[
#             (affected_df["src_mac"] == anchor) |
#             (affected_df["dst_mac"] == anchor)
#         ].copy()

#         if not tmp.empty:
#             print(f"[INFO] using affected active flows involving anchor {anchor}")
#             affected_df = tmp
#         else:
#             print(f"[WARN] active anchor {anchor} does not touch congested links; using all affected active flows")

#     rows = []
#     for pk, g in affected_df.groupby("pair_key"):
#         b = best_option(g)
#         if b is None:
#             continue

#         rows.append({
#             "pair_key": pk,
#             "diversity": diversity(g),
#             "overuse": blocked_overuse(b["norm_path_links"]),
#             "overlap": overlap(b["norm_path_links"]),
#             "blocked": blocked_used(b["norm_path_links"]),
#             "same_path": same_path(b["norm_path_links"]),
#             "activity": activity.get(pk, 0),
#             "hop": int(b["hop_count"])
#         })

#     if not rows:
#         return []

#     rank = pd.DataFrame(rows).sort_values(
#         ["diversity", "overuse", "overlap", "blocked", "same_path", "activity", "hop"],
#         ascending=[True, True, True, True, True, False, True]
#     )

#     for _, r in rank.iterrows():
#         pk = r["pair_key"]

#         if pk in chosen:
#             continue

#         best = best_option(affected_df[affected_df["pair_key"] == pk])
#         if best is None:
#             continue

#         chosen.add(pk)
#         register(best["norm_path_links"])
#         out.append(pack(best))

#         if len(out) >= MAX_ACTIVE_FLOWS_TOTAL:
#             break

#     return sort_results(out)
# # update 3.2

# ##update 3.3 limit allowed shuffle numbers and allowed overlaps | link by link | host by host
# def path_selector(final_obj, hoplist_csv, max_blocked_use=0):
#     print("\n running path selector")

#     def norm_link(s):
#         a, b = [x.strip() for x in str(s).split("->")]
#         return tuple(sorted([a, b]))

#     def path_links(s):
#         return [x.strip() for x in str(s).split(",") if x.strip()]

#     def hnum(h):
#         return int(str(h).lower().replace("h", ""))

#     def order_hosts(a, b):
#         a, b = str(a), str(b)
#         return (a, b) if hnum(a) <= hnum(b) else (b, a)

#     def pair_key(a, b):
#         return tuple(sorted([str(a), str(b)], key=hnum))

#     macs = [str(x).upper() for x in final_obj.get("final_macs", [])]
#     blocked = [norm_link(x) for x in final_obj.get("final_links", []) if str(x).strip()]
#     if not blocked:
#         return []

#     blocked_set = set(blocked)

#     # ============================================================
#     # Get active ONOS flows first
#     # ============================================================
#     active_pairs = get_onos_active_pairs(final_obj, topology_file="topology_s10.txt")
#     if not active_pairs:
#         print("[INFO] no ONOS active pair found; skipping RRM")
#         return []

#     def mac_pair_tuple(a, b):
#         return tuple(sorted([str(a).upper(), str(b).upper()]))

#     allowed_all = {
#         mac_pair_tuple(p["src_mac"], p["dst_mac"])
#         for p in active_pairs
#     }

#     active_mac_set = set()
#     for p in active_pairs:
#         active_mac_set.add(str(p["src_mac"]).upper())
#         active_mac_set.add(str(p["dst_mac"]).upper())

#     passed_set = set(macs)
#     passed_active = passed_set & active_mac_set

#     if macs and not passed_active:
#         print("[WARN] none of the passed hosts are active; using default active-flow distribution")

#     # flow based solution # newly added
#     # ============================================================
#     # Read hoplist and immediately keep only active flow pairs
#     # ============================================================
#     df = pd.read_csv(
#         hoplist_csv,
#         header=None,
#         names=["host1", "host2", "option_number", "hop_count", "src_mac", "dst_mac", "path"],
#         usecols=[0, 1, 2, 3, 4, 5, 6]
#     )

#     df["src_mac"] = df["src_mac"].astype(str).str.upper()
#     df["dst_mac"] = df["dst_mac"].astype(str).str.upper()

#     df["mac_pair"] = df.apply(
#         lambda r: mac_pair_tuple(r["src_mac"], r["dst_mac"]),
#         axis=1
#     )

#     df = df[df["mac_pair"].isin(allowed_all)].copy()

#     if df.empty:
#         print("[INFO] no hoplist routes found for active ONOS flows; skipping RRM")
#         return []

#     df["option_number"] = df["option_number"].astype(int)
#     df["hop_count"] = df["hop_count"].astype(int)

#     # Exclude option 0 from RRM path selection.
#     # option 0 = default/current/no-mutation path, so it should not be selected as an RRM candidate.
#     df = df[df["option_number"] != 0].copy()

#     if df.empty:
#         print("[INFO] no non-zero route options available after excluding option 0; skipping RRM")
#         return []

#     df["pair_key"] = df.apply(lambda r: pair_key(r["host1"], r["host2"]), axis=1)

#     # Only now normalize path links, after active-flow filtering
#     df["norm_path_links"] = df["path"].apply(
#         lambda p: [norm_link(x) for x in path_links(p)]
#     )
#     ##ends


#     activity = {}
#     try:
#         rh = pd.read_csv("route_history.csv")
#         rh["pair_key"] = rh.apply(lambda r: pair_key(r["host_a"], r["host_b"]), axis=1)

#         def act_score(hist):
#             vals = []
#             for x in str(hist).split(","):
#                 try:
#                     vals.append(int(x.strip()))
#                 except:
#                     vals.append(0)
#             return sum(v != 0 for v in vals)

#         rh["activity_score"] = rh["history"].apply(act_score)
#         activity = dict(zip(rh["pair_key"], rh["activity_score"]))
#     except Exception as e:
#         print("[WARN] could not read route history:", e)

#     link_load, blocked_load, path_load = {}, {}, {}

#     def sig(links):
#         return tuple(sorted(links))

#     def blocked_used(links):
#         return sum(lk in blocked_set for lk in links)

#     def blocked_overuse(links):
#         return sum(lk in blocked_set and blocked_load.get(lk, 0) >= max_blocked_use for lk in links)

#     def overlap(links):
#         return sum(link_load.get(lk, 0) for lk in links)

#     def same_path(links):
#         return path_load.get(sig(links), 0)

#     def register(links):
#         for lk in links:
#             link_load[lk] = link_load.get(lk, 0) + 1
#             if lk in blocked_set:
#                 blocked_load[lk] = blocked_load.get(lk, 0) + 1
#         path_load[sig(links)] = path_load.get(sig(links), 0) + 1

#     def score(row):
#         links = row["norm_path_links"]
#         return (
#             blocked_overuse(links),
#             blocked_used(links),
#             same_path(links),
#             overlap(links),
#             int(row["hop_count"]),
#             int(row["option_number"])
#         )

#     def best_option(g):
#         g = g.copy()

#         stages = [
#             g[g["norm_path_links"].apply(lambda x: blocked_used(x) == 0 and overlap(x) == 0 and same_path(x) == 0)],
#             g[g["norm_path_links"].apply(lambda x: blocked_used(x) == 0)],
#             g[g["norm_path_links"].apply(lambda x: blocked_overuse(x) == 0 and overlap(x) == 0)],
#             g
#         ]

#         for st in stages:
#             if not st.empty:
#                 st = st.copy()
#                 st["score"] = st.apply(score, axis=1)
#                 return st.sort_values("score").iloc[0]

#     def diversity(g):
#         return g[g["norm_path_links"].apply(
#             lambda x: blocked_used(x) == 0 and overlap(x) == 0 and same_path(x) == 0
#         )].shape[0]

#     def pack(row):
#         h1, h2 = order_hosts(row["host1"], row["host2"])
#         return {"host1": h1, "host2": h2, "option_number": int(row["option_number"])}

#     def sort_results(rows):
#         return sorted(rows, key=lambda r: (hnum(r["host1"]), hnum(r["host2"])))

#     # MODE A: 2+ hosts passed | already filtered by active flows
#     if len(macs) >= 2:
#         if passed_active:
#             pair_df = df[
#                 (df["src_mac"].isin(passed_active)) |
#                 (df["dst_mac"].isin(passed_active))
#             ].copy()

#             if pair_df.empty:
#                 print("[WARN] passed active hosts not found in hoplist; using default active-flow distribution")
#                 pair_df = df.copy()
#             else:
#                 print("[INFO] using active flows involving passed active hosts")
#         else:
#             print("[INFO] using default active-flow distribution")
#             pair_df = df.copy()

#         if pair_df.empty:
#             return []

#         #newly added
#         max_blocked_use = max(1, pair_df["pair_key"].nunique() // 2) #newly

#         keys = list(pair_df["pair_key"].unique())
#         keys.sort(key=lambda pk: (
#             diversity(pair_df[pair_df["pair_key"] == pk]),
#             pair_df[pair_df["pair_key"] == pk]["hop_count"].min(),
#             hnum(pk[0]),
#             hnum(pk[1])
#         ))

#         out = []
#         for pk in keys:
#             best = best_option(pair_df[pair_df["pair_key"] == pk])
#             if best is None:
#                 continue
#             register(best["norm_path_links"])
#             out.append(pack(best))

#         return sort_results(out)

#     # # MODE B/C: one anchor host or only congested links
#     # anchor = macs[0] if len(macs) == 1 else None
#     # chosen, out = set(), []
#     # # MAX_ACTIVE_FLOWS_TOTAL = 4

#     # # Active pairs whose candidate routes contain ANY congested link
#     # affected_df = df[df["norm_path_links"].apply(
#     #     lambda links: any(blk in links for blk in blocked)
#     # )].copy()

#     # # newly added latest
#     # flow_count = affected_df["pair_key"].nunique()     # newly added latest
#     # MAX_ACTIVE_FLOWS_TOTAL = max(1, (flow_count + 1) // 2)     # newly added latest

#     # if affected_df.empty:
#     #     print("[INFO] no active flow route options touch any congested link")
#     #     return []

#     # # If one active anchor host is provided, prioritize its affected flows
#     # if anchor and anchor in active_mac_set:
#     #     tmp = affected_df[
#     #         (affected_df["src_mac"] == anchor) |
#     #         (affected_df["dst_mac"] == anchor)
#     #     ].copy()

#     #     if not tmp.empty:
#     #         print(f"[INFO] using affected active flows involving anchor {anchor}")
#     #         affected_df = tmp
#     #     else:
#     #         print(f"[WARN] active anchor {anchor} does not touch congested links; using all affected active flows")

#     # rows = []
#     # for pk, g in affected_df.groupby("pair_key"):
#     #     b = best_option(g)
#     #     if b is None:
#     #         continue

#     #     rows.append({
#     #         "pair_key": pk,
#     #         "diversity": diversity(g),
#     #         "overuse": blocked_overuse(b["norm_path_links"]),
#     #         "overlap": overlap(b["norm_path_links"]),
#     #         "blocked": blocked_used(b["norm_path_links"]),
#     #         "same_path": same_path(b["norm_path_links"]),
#     #         "activity": activity.get(pk, 0),
#     #         "hop": int(b["hop_count"])
#     #     })

#     # if not rows:
#     #     return []

#     # rank = pd.DataFrame(rows).sort_values(
#     #     ["diversity", "overuse", "overlap", "blocked", "same_path", "activity", "hop"],
#     #     ascending=[True, True, True, True, True, False, True]
#     # )

#     # for _, r in rank.iterrows():
#     #     pk = r["pair_key"]

#     #     if pk in chosen:
#     #         continue

#     #     best = best_option(affected_df[affected_df["pair_key"] == pk])
#     #     if best is None:
#     #         continue

#     #     chosen.add(pk)
#     #     register(best["norm_path_links"])
#     #     out.append(pack(best))

#     #     if len(out) >= MAX_ACTIVE_FLOWS_TOTAL:
#     #         break

#     # return sort_results(out)


#     # MODE B/C: one anchor host or only congested links
#     anchor = macs[0] if len(macs) == 1 else None
#     chosen, out = set(), []

#     # ------------------------------------------------------------
#     # Step 1: find affected flow pairs
#     # Affected = any candidate/current route touches a congested link
#     # ------------------------------------------------------------
#     affected_pairs = df[df["norm_path_links"].apply(
#         lambda links: any(blk in links for blk in blocked)
#     )]["pair_key"].unique()

#     # Step 2: keep ALL candidate routes for those affected pairs
#     affected_df = df[df["pair_key"].isin(affected_pairs)].copy()

#     if affected_df.empty:
#         print("[INFO] no active flow route options touch any congested link")
#         return []

#     # ------------------------------------------------------------
#     # Optional anchor filtering
#     # ------------------------------------------------------------
#     if anchor and anchor in active_mac_set:
#         tmp = affected_df[
#             (affected_df["src_mac"] == anchor) |
#             (affected_df["dst_mac"] == anchor)
#         ].copy()

#         if not tmp.empty:
#             print(f"[INFO] using affected active flows involving anchor {anchor}")
#             affected_df = tmp
#         else:
#             print(f"[WARN] active anchor {anchor} does not touch congested links; using all affected active flows")

#     # ------------------------------------------------------------
#     # Bad-link reuse cap: only 1/4 of affected flows may reuse bad link
#     # ------------------------------------------------------------
#     flow_count = affected_df["pair_key"].nunique()
#     BAD_LINK_REUSE_CAP = max(1, flow_count // 4)

#     print(f"[INFO] affected flows={flow_count}, bad-link reuse cap={BAD_LINK_REUSE_CAP}")

#     bad_link_use_count = defaultdict(int)

#     def within_bad_link_reuse_cap(path_links):
#         return all(
#             bad_link_use_count[blk] < BAD_LINK_REUSE_CAP
#             for blk in blocked
#             if blk in path_links
#         )

#     def register_bad_link_use(path_links):
#         for blk in blocked:
#             if blk in path_links:
#                 bad_link_use_count[blk] += 1

#     # ------------------------------------------------------------
#     # Build flow-level ranking
#     # ------------------------------------------------------------
#     rows = []

#     for pk, g in affected_df.groupby("pair_key"):

#         # Prefer clean paths for ranking
#         clean_g = g[g["norm_path_links"].apply(
#             lambda links: blocked_used(links) == 0
#         )].copy()

#         candidate_g = clean_g if not clean_g.empty else g.copy()

#         b = best_option(candidate_g)
#         if b is None:
#             continue

#         rows.append({
#             "pair_key": pk,
#             "diversity": diversity(g),
#             "overuse": blocked_overuse(b["norm_path_links"]),
#             "overlap": overlap(b["norm_path_links"]),
#             "blocked": blocked_used(b["norm_path_links"]),
#             "same_path": same_path(b["norm_path_links"]),
#             "activity": activity.get(pk, 0),
#             "hop": int(b["hop_count"])
#         })

#     if not rows:
#         return []

#     rank = pd.DataFrame(rows).sort_values(
#         ["blocked", "overuse", "overlap", "same_path", "diversity", "activity", "hop"],
#         ascending=[True, True, True, True, True, False, True]
#     )

#     # ------------------------------------------------------------
#     # Select route for each affected flow
#     # ------------------------------------------------------------
#     for _, r in rank.iterrows():
#         pk = r["pair_key"]

#         if pk in chosen:
#             continue

#         g = affected_df[affected_df["pair_key"] == pk]

#         # First try paths that fully avoid bad/congested links
#         clean_g = g[g["norm_path_links"].apply(
#             lambda links: blocked_used(links) == 0
#         )].copy()

#         if not clean_g.empty:
#             candidate_g = clean_g
#         else:
#             # Only if no clean path exists, allow bad-link reuse up to 1/4
#             candidate_g = g[g["norm_path_links"].apply(
#                 within_bad_link_reuse_cap
#             )].copy()

#             if candidate_g.empty:
#                 print(f"[WARN] no clean/capped path for {pk}")
#                 continue

#         best = best_option(candidate_g)
#         if best is None:
#             continue

#         chosen.add(pk)
#         register(best["norm_path_links"])
#         register_bad_link_use(best["norm_path_links"])
#         out.append(pack(best))

#     return sort_results(out)


##update 3.3 limit allowed shuffle numbers and allowed overlaps | link by link | host by host

def parse_topology_hosts(topology_file):
    """
    Reads host entries like:
    h1, 10.0.0.1/24, 00:00:00:00:00:01

    Returns:
    mac_to_host = {
        "00:00:00:00:00:01": "h1",
        ...
    }
    """
    mac_to_host = {}

    with open(topology_file, "r") as f:
        for raw in f:
            line = raw.strip()

            if not line or line.startswith("#"):
                continue

            parts = [p.strip() for p in line.split(",")]

            if len(parts) == 3 and parts[0].startswith("h") and "/" in parts[1] and ":" in parts[2]:
                host = parts[0]
                mac = parts[2].upper()
                mac_to_host[mac] = host

    return mac_to_host


MAC_TO_HOST = parse_topology_hosts(TOPOLOGY_FILE)


def resolve_hosts_from_macs(macs):
    hosts = []

    for mac in macs:
        host = MAC_TO_HOST.get(mac.upper())
        if host:
            hosts.append(host)
        else:
            print(f"[WARN] MAC not found in topology: {mac}")

    return hosts


def build_ip_octets_for_hosts(hosts):
    """
    Example mapping:
    h1 -> 10
    h2 -> 20
    h3 -> 30
    """
    octets = []

    for h in hosts:
        try:
            num = int(h[1:])
            octet = str(num * 10)
            octets.append(octet)
        except Exception:
            print(f"[WARN] Could not derive octet for host {h}")
            octets.append(str(random.randint(10, 200)))

    return octets

def do_ip_shuffle(macs, ip_manager):
    print("[IP SHUFFLE] Target MACs:", macs)

    hosts = resolve_hosts_from_macs(macs)

    hosts = [h for h in hosts if h != "h1"]

    if not hosts:
        print("[IP SHUFFLE] No hosts resolved from MACs")
        return

    current_ips = ip_manager.get_current_ips()

    used_ips = set()
    for ip in current_ips.values():
        if ip is not None:
            used_ips.add(int(str(ip).split(".")[-1]))

    # free old IPs of selected hosts so they may change safely
    for h in hosts:
        old_ip = current_ips.get(h)
        if old_ip is not None:
            used_ips.discard(int(str(old_ip).split(".")[-1]))

    available_ips = [i for i in range(1, 256) if i not in used_ips]

    if len(available_ips) < len(hosts):
        print("[IP SHUFFLE] Not enough free IPs")
        return

    new_ips = random.sample(available_ips, len(hosts))
    shuffled_map = dict(zip(hosts, new_ips))

    host_arg = ",".join(hosts)
    ips_arg = ",".join(map(str, new_ips))

    print("[IP SHUFFLE] Calling endpoint:")
    print(f'  host="{host_arg}"')
    print(f'  ips="{ips_arg}"')

    ip_shuffle_endpoint(
        host=host_arg,
        ips=ips_arg,
        interval=15,
        no_block_pid=True
    )

    # push every host into deque every round
    for host in all_hosts:
        if host in shuffled_map:
            ip_manager.update_host_queue(host, shuffled_map[host])
        else:
            last_ip = ip_manager.current_ips.get(host)
            if last_ip is not None:
                ip_manager.update_host_queue(host, last_ip)

    ip_manager.save_to_csv()

    print("[IP SHUFFLE] Updated history:")
    print(ip_manager.get_all_host_ips())

    return shuffled_map #new

# def do_rrm(links, candidate_paths):
# def do_rrm(links, candidate_paths, route_manager): # new 

#     """
#     Calls:
#     route_shuffle_endpoint(
#         specific_multiple=True,
#         hosts="h1,h2;h1,h7",
#         opt="3;4"
#     )
#     """
#     print("[RRM] Avoid links:", links)

#     if not candidate_paths:
#         print("[RRM] No candidate safe path found")
#         return

#     print("[RRM] Candidate safe paths:")
#     for p in candidate_paths:
#         print(p)

#     host_pairs = []
#     opt_list = []

#     for chosen in candidate_paths:
#         host1 = chosen["host1"]
#         host2 = chosen["host2"]
#         opt = str(chosen["option_number"])

#         route_manager.update_pair(host1, host2, opt) # new

#         host_pairs.append(f"{host1},{host2}")
#         opt_list.append(opt)

#     hosts_arg = ";".join(host_pairs)
#     opt_arg = ";".join(opt_list)

#     print("[RRM] Calling endpoint:")
#     print(f'  hosts="{hosts_arg}"')
#     print(f'  opt="{opt_arg}"')

#     route_shuffle_endpoint(
#         specific_multiple=True,
#         hosts=hosts_arg,
#         opt=opt_arg
#     )

#     # new
#     route_manager.save_to_csv()
#     print("[RRM] Updated route history:")
#     # new

#     return candidate_paths # new


def do_rrm(links, candidate_paths, route_manager): # new 

    """
    Calls:
    route_shuffle_endpoint(
        specific_multiple=True,
        hosts="h1,h2;h1,h7",
        opt="3;4"
    )
    """
    print("[RRM] Avoid links:", links)

    if not candidate_paths:
        print("[RRM] No candidate safe path found")
        return

    print("[RRM] Candidate safe paths:")
    for p in candidate_paths:
        print(p)

    host_pairs = []
    opt_list = []

    # for chosen in candidate_paths:
    #     host1 = chosen["host1"]
    #     host2 = chosen["host2"]
    #     opt = str(chosen["option_number"])

    #     route_manager.update_pair(host1, host2, opt) # new

    #     host_pairs.append(f"{host1},{host2}")
    #     opt_list.append(opt)

    # This list stores all routes selected in this ONE RRM cycle. #new 2
    # Example:
    #   [("h2", "h34", 2), ("h3", "h33", 4)]
    selected_routes = []

    for chosen in candidate_paths:
        host1 = chosen["host1"]
        host2 = chosen["host2"]
        opt = int(chosen["option_number"])

        # Store selected route for route_history.csv update
        selected_routes.append((host1, host2, opt))

        # Build arguments for route_shuffle_endpoint()
        host_pairs.append(f"{host1},{host2}")
        opt_list.append(str(opt))

    # IMPORTANT:
    # Update route history ONCE per RRM cycle.
    # Selected pairs get their option number.
    # All other pairs get 0.
    route_manager.update_cycle(selected_routes) # new 2

    hosts_arg = ";".join(host_pairs)
    opt_arg = ";".join(opt_list)

    print("[RRM] Calling endpoint:")
    print(f'  hosts="{hosts_arg}"')
    print(f'  opt="{opt_arg}"')

    route_shuffle_endpoint(
        specific_multiple=True,
        hosts=hosts_arg,
        opt=opt_arg
    )

    # new
    route_manager.save_to_csv()
    print("[RRM] Updated route history:")
    # new

    return candidate_paths # new version handles the others not updated candidates with 0 | to reduce route dispatch conflict

# def dispatch_mitigation(final_obj, hoplist_csv):
# def dispatch_mitigation(final_obj, hoplist_csv, ip_manager):
def dispatch_mitigation(final_obj, hoplist_csv, ip_manager, route_manager):
    decision = final_obj.get("final_decision", "do_nothing")
    macs = final_obj.get("final_macs", [])
    links = final_obj.get("final_links", [])

    print("[DECISION]", decision)
    print("MACs:", macs)
    print("Links:", links)

    candidate_paths = []
    ip_result = None
    route_result = None

    if decision in ["rrm", "both"]:
        # candidate_paths = path_selector(final_obj, hoplist_csv)
        candidate_paths = path_selector(final_obj, "hop_list.csv", max_blocked_use=0) #new

    if decision == "do_nothing":
        print("[ACTION] No action taken")

    # elif decision == "ip":
    #     do_ip_shuffle(macs)
    elif decision == "ip":
        # do_ip_shuffle(macs, ip_manager)
        ip_result = do_ip_shuffle(macs, ip_manager) # new

    elif decision == "rrm":
        # do_rrm(links, candidate_paths)
        # do_rrm(links, candidate_paths , route_manager)  
        route_result = do_rrm(links, candidate_paths, route_manager) # new


    elif decision == "both":
        # do_ip_shuffle(macs)
        # do_ip_shuffle(macs, ip_manager)
        # do_rrm(links, candidate_paths)
        # do_rrm(links, candidate_paths , route_manager) # 
        ip_result = do_ip_shuffle(macs, ip_manager) # new
        route_result = do_rrm(links, candidate_paths, route_manager) # new

    else:
        print("[ERROR] Unknown decision:", decision)

    return ip_result, route_result




# new | take k steps 
def wait_for_next_k_ts(_prepare, csv_file, decision_ts, k=1):
    while True:
        df = _prepare(csv_file)
        ts = sorted(df["timestamp"].unique())
        future = [t for t in ts if t > decision_ts]

        if len(future) >= k:
            return future[:k]

        time.sleep(2)

# #average last 5 instead of only last point!!
# def validate_effect(scene, final_obj, decision_ts, host_csv=HOST_CSV, link_csv=LINK_CSV):
#     def _prepare(csv_file):
#         df = pd.read_csv(csv_file)
#         df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
#         return df.dropna(subset=["timestamp"]).copy()

#     def mean2(vals):
#         return float(sum(vals) / len(vals)) if vals else 0.0

#     def weighted_mean(vals):
#         if not vals:
#             return 0.0
#         weights = list(range(1, len(vals) + 1))   # older gets less, recent gets more
#         wsum = sum(weights)
#         return float(sum(w * x for w, x in zip(weights, vals)) / wsum)

#     def selected_score_from_values(before_pps, before_mbps, after_pps_mean, after_mbps_mean, is_link=False):
#         red_pps = (before_pps - after_pps_mean) / max(before_pps, 1e-9)
#         red_mbps = (before_mbps - after_mbps_mean) / max(before_mbps, 1e-9)

#         raw = max(red_pps, red_mbps)

#         if is_link:
#             # links usually improve less sharply, so soften expectation
#             return raw * 1.35
#         else:
#             return raw
        
#     # def other_candidate_score_from_values(before_pps, before_mbps, after_pps_mean, after_mbps_mean, is_link=False):
#     #     rise_pps = (after_pps_mean - before_pps) / max(before_pps, 1e-9)
#     #     rise_mbps = (after_mbps_mean - before_mbps) / max(before_mbps, 1e-9)
#     #     rise = max(rise_pps, rise_mbps)

#     #     if rise < 0:
#     #         gain = abs(rise)
#     #         return gain * (1.15 if is_link else 1.0)

#     #     tolerance = 0.20 if is_link else 0.10
#     #     if rise <= tolerance:
#     #         return 0.0

#     #     excess = rise - tolerance
#     #     penalty = excess * (0.5 if is_link else 1.0)
#     #     return -penalty
#     # # new above

#     # newly added
#     def other_candidate_score_from_values(
#         before_pps,
#         before_mbps,
#         after_pps_mean,
#         after_mbps_mean,
#         is_link=False,
#         decision="",
#         threshold_mbps=9.0
#     ):
#         if is_link and decision == "rrm":
#             # For RRM, traffic redistribution is expected.
#             # Penalize other links only if they become congested.
#             if after_mbps_mean < threshold_mbps:
#                 return 0.0

#             overload = (after_mbps_mean - threshold_mbps) / threshold_mbps
#             return max(-1.0, -overload)

#         # Default behavior for IP, both, or host-side validation:
#         rise_pps = (after_pps_mean - before_pps) / max(before_pps, 1e-9)
#         rise_mbps = (after_mbps_mean - before_mbps) / max(before_mbps, 1e-9)
#         rise = max(rise_pps, rise_mbps)

#         if rise < 0:
#             gain = abs(rise)
#             return gain * (1.15 if is_link else 1.0)

#         tolerance = 0.20 if is_link else 0.10
#         if rise <= tolerance:
#             return 0.0

#         excess = rise - tolerance
#         penalty = excess * (0.5 if is_link else 1.0)
#         return -penalty   
#     #nds 


#     decision_ts = pd.to_datetime(decision_ts)
#     # wait_for_next_two_ts(_prepare, host_csv, decision_ts)
#     next_two_host = wait_for_next_k_ts(_prepare, host_csv, decision_ts,k=2)
#     next_two_link = wait_for_next_k_ts(_prepare, link_csv, decision_ts,k=2)
#     # next_two_host = wait_for_next_k_ts(_prepare, host_csv, decision_ts,k=1)
#     # next_two_link = wait_for_next_k_ts(_prepare, link_csv, decision_ts,k=1)
    

#     host_df = _prepare(host_csv)
#     link_df = _prepare(link_csv)

#     final_macs = [str(x).upper() for x in final_obj.get("final_macs", [])]
#     final_links = [str(x) for x in final_obj.get("final_links", [])]

#     decision = final_obj.get("final_decision", "") # newly shifted

#     candidate_host_stats = scene.get("flagged_host_stats", [])
#     candidate_link_stats = scene.get("flagged_link_stats", [])

#     host_candidate_map = {
#         str(x.get("mac", "")).upper(): x
#         for x in candidate_host_stats if x.get("mac")
#     }
#     link_candidate_map = {
#         str(x.get("link_id", "")): x
#         for x in candidate_link_stats if x.get("link_id")
#     }

#     candidate_macs = list(host_candidate_map.keys())
#     candidate_links = list(link_candidate_map.keys())

#     selected_macs_set = set(final_macs)
#     selected_links_set = set(final_links)

#     candidate_macs_set = set(candidate_macs)
#     candidate_links_set = set(candidate_links)

#     other_candidate_macs = sorted(candidate_macs_set - selected_macs_set)
#     other_candidate_links = sorted(candidate_links_set - selected_links_set)

#     selected_host_scores = []
#     selected_link_scores = []
#     other_candidate_host_scores = []
#     other_candidate_link_scores = []

#     host_trace_selected = []
#     host_trace_other = []
#     link_trace_selected = []
#     link_trace_other = []

#     # ---------------- Selected hosts ----------------
#     for macu in final_macs:
#         cand = host_candidate_map.get(macu)

#         after_rows = host_df[
#             (host_df["host_mac"].astype(str).str.upper() == macu) &
#             (host_df["timestamp"].isin(next_two_host))
#         ].sort_values("timestamp")

#         if cand is None or after_rows.empty:
#             continue

#         before_pps = float(
#             weighted_mean(cand["tx_pps_trend"]) +
#             weighted_mean(cand["rx_pps_trend"])
#         )
#         before_mbps = float(
#             weighted_mean(cand["tx_kbps_trend"]) +
#             weighted_mean(cand["rx_kbps_trend"])
#         ) / 1000.0

#         after_pps_list = (
#             after_rows["rx_pps"].astype(float).values +
#             after_rows["tx_pps"].astype(float).values
#         ).tolist()
#         after_mbps_list = (
#             after_rows["rx_mbps"].astype(float).values +
#             after_rows["tx_mbps"].astype(float).values
#         ).tolist()

#         # after_pps_mean = mean2(after_pps_list)
#         # after_mbps_mean = mean2(after_mbps_list)
#         after_pps_mean = weighted_mean(after_pps_list) # new
#         after_mbps_mean = weighted_mean(after_mbps_list) # new
        

#         # score = selected_score_from_values(before_pps, before_mbps, after_pps_mean, after_mbps_mean)
#         score = selected_score_from_values(before_pps, before_mbps, after_pps_mean, after_mbps_mean, is_link=False)
#         selected_host_scores.append(score)

#         host_trace_selected.append({
#             "mac": macu,
#             "before": {
#                 "pps": round(before_pps, 4),
#                 "mbps": round(before_mbps, 4)
#             },
#             "after_points": {
#                 "pps": [round(x, 4) for x in after_pps_list],
#                 "mbps": [round(x, 4) for x in after_mbps_list]
#             },
#             "score": round(score, 4)
#         })

#     # ---------------- Selected links ----------------
#     for link_id in final_links:
#         cand = link_candidate_map.get(link_id)

#         after_rows = link_df[
#             (link_df["link_id"].astype(str) == link_id) &
#             (link_df["timestamp"].isin(next_two_link))
#         ].sort_values("timestamp")

#         if cand is None or after_rows.empty:
#             continue

#         before_pps = float(
#             weighted_mean(cand["tx_pps_trend"]) +
#             weighted_mean(cand["rx_pps_trend"])
#         )
#         before_mbps = float(
#             weighted_mean(cand["tx_kbps_trend"]) +
#             weighted_mean(cand["rx_kbps_trend"])
#         ) / 1000.0

#         after_pps_list = (
#             after_rows["rx_pps"].astype(float).values +
#             after_rows["tx_pps"].astype(float).values
#         ).tolist()
#         after_mbps_list = (
#             after_rows["rx_mbps"].astype(float).values +
#             after_rows["tx_mbps"].astype(float).values
#         ).tolist()

#         # after_pps_mean = mean2(after_pps_list)
#         # after_mbps_mean = mean2(after_mbps_list)
#         after_pps_mean = weighted_mean(after_pps_list) # new
#         after_mbps_mean = weighted_mean(after_mbps_list) # new

#         # score = selected_score_from_values(before_pps, before_mbps, after_pps_mean, after_mbps_mean)
#         score = selected_score_from_values(before_pps, before_mbps, after_pps_mean, after_mbps_mean, is_link=True) # new
#         selected_link_scores.append(score)

#         link_trace_selected.append({
#             "link_id": link_id,
#             "before": {
#                 "pps": round(before_pps, 4),
#                 "mbps": round(before_mbps, 4)
#             },
#             "after_points": {
#                 "pps": [round(x, 4) for x in after_pps_list],
#                 "mbps": [round(x, 4) for x in after_mbps_list]
#             },
#             "score": round(score, 4)
#         })

#     # ---------------- Other candidate hosts ----------------
#     for macu in other_candidate_macs:
#         cand = host_candidate_map.get(macu)

#         after_rows = host_df[
#             (host_df["host_mac"].astype(str).str.upper() == macu) &
#             (host_df["timestamp"].isin(next_two_host))
#         ].sort_values("timestamp")

#         if cand is None or after_rows.empty:
#             continue

#         before_pps = float(
#             weighted_mean(cand["tx_pps_trend"]) +
#             weighted_mean(cand["rx_pps_trend"])
#         )
#         before_mbps = float(
#             weighted_mean(cand["tx_kbps_trend"]) +
#             weighted_mean(cand["rx_kbps_trend"])
#         ) / 1000.0

#         after_pps_list = (
#             after_rows["rx_pps"].astype(float).values +
#             after_rows["tx_pps"].astype(float).values
#         ).tolist()
#         after_mbps_list = (
#             after_rows["rx_mbps"].astype(float).values +
#             after_rows["tx_mbps"].astype(float).values
#         ).tolist()

#         # after_pps_mean = mean2(after_pps_list)
#         # after_mbps_mean = mean2(after_mbps_list)
#         after_pps_mean = weighted_mean(after_pps_list)
#         after_mbps_mean = weighted_mean(after_mbps_list)

#         # score = other_candidate_score_from_values(before_pps, before_mbps, after_pps_mean, after_mbps_mean)
#         # score = other_candidate_score_from_values(before_pps, before_mbps, after_pps_mean, after_mbps_mean, is_link=False) # new
#         score = other_candidate_score_from_values(before_pps,before_mbps,after_pps_mean,after_mbps_mean,is_link=False,decision=decision) #newly added
#         other_candidate_host_scores.append(score)

#         host_trace_other.append({
#             "mac": macu,
#             "before": {
#                 "pps": round(before_pps, 4),
#                 "mbps": round(before_mbps, 4)
#             },
#             "after_points": {
#                 "pps": [round(x, 4) for x in after_pps_list],
#                 "mbps": [round(x, 4) for x in after_mbps_list]
#             },
#             "score": round(score, 4)
#         })

#     # ---------------- Other candidate links ----------------
#     for link_id in other_candidate_links:
#         cand = link_candidate_map.get(link_id)

#         after_rows = link_df[
#             (link_df["link_id"].astype(str) == link_id) &
#             (link_df["timestamp"].isin(next_two_link))
#         ].sort_values("timestamp")

#         if cand is None or after_rows.empty:
#             continue

#         before_pps = float(
#             weighted_mean(cand["tx_pps_trend"]) +
#             weighted_mean(cand["rx_pps_trend"])
#         )
#         before_mbps = float(
#             weighted_mean(cand["tx_kbps_trend"]) +
#             weighted_mean(cand["rx_kbps_trend"])
#         ) / 1000.0

#         after_pps_list = (
#             after_rows["rx_pps"].astype(float).values +
#             after_rows["tx_pps"].astype(float).values
#         ).tolist()
#         after_mbps_list = (
#             after_rows["rx_mbps"].astype(float).values +
#             after_rows["tx_mbps"].astype(float).values
#         ).tolist()

#         # after_pps_mean = mean2(after_pps_list)
#         # after_mbps_mean = mean2(after_mbps_list)
#         after_pps_mean = weighted_mean(after_pps_list)
#         after_mbps_mean = weighted_mean(after_mbps_list)

#         # score = other_candidate_score_from_values(before_pps, before_mbps, after_pps_mean, after_mbps_mean)
#         # score = other_candidate_score_from_values(before_pps, before_mbps, after_pps_mean, after_mbps_mean, is_link=True) # new
#         score = other_candidate_score_from_values(before_pps,before_mbps,after_pps_mean,after_mbps_mean,is_link=True,decision=decision) # newly added
#         other_candidate_link_scores.append(score)

#         link_trace_other.append({
#             "link_id": link_id,
#             "before": {
#                 "pps": round(before_pps, 4),
#                 "mbps": round(before_mbps, 4)
#             },
#             "after_points": {
#                 "pps": [round(x, 4) for x in after_pps_list],
#                 "mbps": [round(x, 4) for x in after_mbps_list]
#             },
#             "score": round(score, 4)
#         })
#     # selected_scores = selected_host_scores + selected_link_scores
#     # other_candidate_scores = other_candidate_host_scores + other_candidate_link_scores

#     # selected_score = mean2(selected_scores)
#     # other_candidate_score = mean2(other_candidate_scores)

#     # decision = final_obj.get("final_decision", "")

#     # if decision == "do_nothing":
#     #     final_score = 0.0
#     #     label = "neutral"
#     #     result = "no mitigation applied"

#     # else:
#     #     # selected targets are the main signal
#     #     # other candidates only provide a small adjustment
#     #     final_score = selected_score + 0.25 * other_candidate_score

#     #     if final_score >= 0.70:
#     #         label = "good"
#     #     elif final_score >= 0.20:
#     #         label = "neutral"
#     #     else:
#     #         label = "bad"

#     #newly added to be just to rrm 
#     # decision = final_obj.get("final_decision", "")

#     if decision == "do_nothing":
#         # For do_nothing, there are no selected mitigation targets.
#         # So judge whether all candidate hosts/links stayed stable.
#         selected_score = 0.0

#         all_candidate_scores = (
#             other_candidate_host_scores +
#             other_candidate_link_scores
#         )

#         other_candidate_score = mean2(all_candidate_scores)

#         # If conditions improved or stayed stable, do_nothing is acceptable.
#         # If candidate conditions worsened, do_nothing should be penalized.
#         final_score = other_candidate_score

#         if final_score >= 0.20:
#             label = "good"
#         elif final_score >= -0.10:
#             label = "neutral"
#         else:
#             label = "bad"

#     elif decision == "rrm":
#         # RRM should mainly be judged by selected congested-link relief.
#         # Host values are only a secondary stability signal.
#         selected_link_score = mean2(selected_link_scores)
#         selected_host_score = mean2(selected_host_scores)

#         other_link_score = mean2(other_candidate_link_scores)
#         other_host_score = mean2(other_candidate_host_scores)

#         selected_score = (
#             0.85 * selected_link_score +
#             0.15 * selected_host_score
#         )

#         other_candidate_score = (
#             0.85 * other_link_score +
#             0.15 * other_host_score
#         )

#         final_score = selected_score + 0.25 * other_candidate_score

#         if selected_link_score >= 0.70 and final_score >= 0.70:
#             label = "good"
#         elif selected_link_score >= 0.40:
#             label = "neutral"
#         else:
#             label = "bad"

#     elif decision == "ip":
#         # IP mutation should mainly be judged by selected host relief.
#         selected_host_score = mean2(selected_host_scores)
#         selected_link_score = mean2(selected_link_scores)

#         other_host_score = mean2(other_candidate_host_scores)
#         other_link_score = mean2(other_candidate_link_scores)

#         selected_score = (
#             0.85 * selected_host_score +
#             0.15 * selected_link_score
#         )

#         other_candidate_score = (
#             0.85 * other_host_score +
#             0.15 * other_link_score
#         )

#         final_score = selected_score + 0.25 * other_candidate_score

#         if selected_host_score >= 0.70 and final_score >= 0.70:
#             label = "good"
#         elif selected_host_score >= 0.40:
#             label = "neutral"
#         else:
#             label = "bad"

#     elif decision == "both":
#         selected_score = mean2(selected_host_scores + selected_link_scores)
#         other_candidate_score = mean2(other_candidate_host_scores + other_candidate_link_scores)

#         final_score = selected_score + 0.25 * other_candidate_score

#         if final_score >= 0.70:
#             label = "good"
#         elif final_score >= 0.30:
#             label = "neutral"
#         else:
#             label = "bad"

#     else:
#         selected_score = mean2(selected_host_scores + selected_link_scores)
#         other_candidate_score = mean2(other_candidate_host_scores + other_candidate_link_scores)

#         final_score = selected_score + 0.25 * other_candidate_score

#         if final_score >= 0.70:
#             label = "good"
#         elif final_score >= 0.20:
#             label = "neutral"
#         else:
#             label = "bad"
#     # ends

#     if decision == "ip":
#         result = "ip_shuffle improved the selected targets" if label == "good" else "ip_shuffle gave limited or weak improvement"
#     elif decision == "rrm":
#         result = "route_mutation improved the selected targets" if label == "good" else "route_mutation gave limited or weak improvement"
#     elif decision == "both":
#         result = "combined mitigation improved the selected targets" if label == "good" else "combined mitigation gave limited or weak improvement"
#     elif decision == "do_nothing":
#         result = ("no mitigation was applied; system remained stable"
#             if label in ["good", "neutral"]
#             else "no mitigation was applied, but the condition worsened")
#     else:
#         result = "unknown decision"

#     # old code cont.
#     return {
#         "label": label,
#         "result": result,
#         "score": round(final_score, 4),
#         "selected_score": round(selected_score, 4),
#         "other_candidate_score": round(other_candidate_score, 4),
#         "validation_trace": {
#             "selected_hosts": host_trace_selected,
#             "selected_links": link_trace_selected,
#             "other_candidate_hosts": host_trace_other,
#             "other_candidate_links": link_trace_other
#         }
#     }

# #average last 5 instead of only last point!!


#average last 5 instead of only last point!!
def validate_effect(scene, final_obj, decision_ts, host_csv=HOST_CSV, link_csv=LINK_CSV):
    # ---------------- Small helpers for final validation ----------------
    HOST_PPS_TH = 1000.0
    LINK_MBPS_TH = 9.0       # 9000 kbps = 9 Mbps
    IP_DROP_TH = 0.30        # 30% host PPS drop
    RRM_DROP_TH = 0.10       # 10% link-load drop

    #csv loading
    def _prepare(csv_file):
        df = pd.read_csv(csv_file)
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        return df.dropna(subset=["timestamp"]).copy()

    def mean2(vals):
        return float(sum(vals) / len(vals)) if vals else 0.0

    def weighted_mean(vals):
        if not vals:
            return 0.0
        weights = list(range(1, len(vals) + 1))   # older gets less, recent gets more
        wsum = sum(weights)
        return float(sum(w * x for w, x in zip(weights, vals)) / wsum)

    decision_ts = pd.to_datetime(decision_ts)
    next_two_host = wait_for_next_k_ts(_prepare, host_csv, decision_ts,k=2)
    next_two_link = wait_for_next_k_ts(_prepare, link_csv, decision_ts,k=2)
    # dataframe loading
    host_df = _prepare(host_csv)
    link_df = _prepare(link_csv)

    # extraaction of decision
    final_macs = [str(x).upper() for x in final_obj.get("final_macs", [])]
    final_links = [str(x) for x in final_obj.get("final_links", [])]
    decision = final_obj.get("final_decision", "") # newly shifted

    # candidate maps
    candidate_host_stats = scene.get("flagged_host_stats", [])
    candidate_link_stats = scene.get("flagged_link_stats", [])

    host_candidate_map = {
        str(x.get("mac", "")).upper(): x
        for x in candidate_host_stats if x.get("mac")
    }
    link_candidate_map = {
        str(x.get("link_id", "")): x
        for x in candidate_link_stats if x.get("link_id")
    }

    # selected other candidate separation

    candidate_macs = list(host_candidate_map.keys())
    candidate_links = list(link_candidate_map.keys())

    selected_macs_set = set(final_macs)
    selected_links_set = set(final_links)

    candidate_macs_set = set(candidate_macs)
    candidate_links_set = set(candidate_links)

    other_candidate_macs = sorted(candidate_macs_set - selected_macs_set)
    other_candidate_links = sorted(candidate_links_set - selected_links_set)

    selected_host_scores = []
    selected_link_scores = []
    other_candidate_host_scores = []
    other_candidate_link_scores = []

    # trace lists

    host_trace_selected = []
    host_trace_other = []
    link_trace_selected = []
    link_trace_other = []

    # ---------------- Compact trace builder ----------------
    def build_host_trace(macs, out_list):
        for macu in macs:
            cand = host_candidate_map.get(macu)
            after_rows = host_df[
                (host_df["host_mac"].astype(str).str.upper() == macu) &
                (host_df["timestamp"].isin(next_two_host))
            ].sort_values("timestamp")

            if cand is None or after_rows.empty:
                continue

            before_tx_pps = float(weighted_mean(cand["tx_pps_trend"]))
            before_rx_pps = float(weighted_mean(cand["rx_pps_trend"]))
            before_tx_mbps = float(weighted_mean(cand["tx_kbps_trend"])) / 1000.0
            before_rx_mbps = float(weighted_mean(cand["rx_kbps_trend"])) / 1000.0

            after_tx_pps = after_rows["tx_pps"].astype(float).tolist()
            after_rx_pps = after_rows["rx_pps"].astype(float).tolist()
            after_tx_mbps = after_rows["tx_mbps"].astype(float).tolist()
            after_rx_mbps = after_rows["rx_mbps"].astype(float).tolist()

            out_list.append({
                "mac": macu,
                "before": {
                    "tx_pps": round(before_tx_pps, 4),
                    "rx_pps": round(before_rx_pps, 4),
                    "pps": round(before_tx_pps + before_rx_pps, 4),
                    "mbps": round(before_tx_mbps + before_rx_mbps, 4)
                },
                "after_points": {
                    "tx_pps": [round(x, 4) for x in after_tx_pps],
                    "rx_pps": [round(x, 4) for x in after_rx_pps],
                    "pps": [round(a + b, 4) for a, b in zip(after_tx_pps, after_rx_pps)],
                    "mbps": [round(a + b, 4) for a, b in zip(after_tx_mbps, after_rx_mbps)]
                }
            })


    # def build_link_trace(links, out_list):
    #     for link_id in links:
    #         cand = link_candidate_map.get(link_id)
    #         after_rows = link_df[
    #             (link_df["link_id"].astype(str) == link_id) &
    #             (link_df["timestamp"].isin(next_two_link))
    #         ].sort_values("timestamp")

    #         if cand is None or after_rows.empty:
    #             continue

    #         before_tx_mbps = float(weighted_mean(cand["tx_kbps_trend"])) / 1000.0
    #         before_rx_mbps = float(weighted_mean(cand["rx_kbps_trend"])) / 1000.0

    #         after_tx_mbps = after_rows["tx_mbps"].astype(float).tolist()
    #         after_rx_mbps = after_rows["rx_mbps"].astype(float).tolist()

    #         out_list.append({
    #             "link_id": link_id,
    #             "before": {
    #                 "mbps": round(before_tx_mbps + before_rx_mbps, 4)
    #             },
    #             "after_points": {
    #                 "mbps": [round(a + b, 4) for a, b in zip(after_tx_mbps, after_rx_mbps)]
    #             }
    #         })

    # def build_link_trace(links, out_list):
    #     for link_id in links:
    #         cand = link_candidate_map.get(link_id)
    #         after_rows = link_df[
    #             (link_df["link_id"].astype(str) == link_id) &
    #             (link_df["timestamp"].isin(next_two_link))
    #         ].sort_values("timestamp")

    #         if cand is None or after_rows.empty:
    #             continue

    #         before_tx_mbps = float(weighted_mean(cand["tx_kbps_trend"])) / 1000.0
    #         before_rx_mbps = float(weighted_mean(cand["rx_kbps_trend"])) / 1000.0

    #         after_tx_mbps = after_rows["tx_mbps"].astype(float).tolist()
    #         after_rx_mbps = after_rows["rx_mbps"].astype(float).tolist()

    #         out_list.append({
    #             "link_id": link_id,
    #             "before": {
    #                 "mbps": round(max(before_tx_mbps, before_rx_mbps), 4)
    #             },
    #             "after_points": {
    #                 "mbps": [
    #                     round(max(a, b), 4)
    #                     for a, b in zip(after_tx_mbps, after_rx_mbps)
    #                 ]
    #             }
    #         })

    def build_link_trace(links, out_list):
        for link_id in links:
            cand = link_candidate_map.get(link_id)
            after_rows = link_df[
                (link_df["link_id"].astype(str) == link_id) &
                (link_df["timestamp"].isin(next_two_link))
            ].sort_values("timestamp")

            if cand is None or after_rows.empty:
                continue

            # For RRM, use peak of the recent window as the pre-mitigation load.
            # This captures the actual congestion that triggered route mutation.
            before_tx_mbps = float(max(cand["tx_kbps_trend"][-5:])) / 1000.0
            before_rx_mbps = float(max(cand["rx_kbps_trend"][-5:])) / 1000.0

            after_tx_mbps = after_rows["tx_mbps"].astype(float).tolist()
            after_rx_mbps = after_rows["rx_mbps"].astype(float).tolist()

            out_list.append({
                "link_id": link_id,
                "before": {
                    "mbps": round(max(before_tx_mbps, before_rx_mbps), 4)
                },
                "after_points": {
                    "mbps": [
                        round(max(a, b), 4)
                        for a, b in zip(after_tx_mbps, after_rx_mbps)
                    ]
                }
            })

    build_host_trace(final_macs, host_trace_selected)
    build_link_trace(final_links, link_trace_selected)
    build_host_trace(other_candidate_macs, host_trace_other)
    build_link_trace(other_candidate_links, link_trace_other)


    # ---------------- Decision-level validation ----------------

    def last_val(item, metric):
        vals = item.get("after_points", {}).get(metric, [])
        return vals[-1] if vals else 0.0

    def drop_ratio(before, after):
        return (before - after) / max(before, 1e-9)

    if decision == "do_nothing":
        host_bad = any(
            last_val(x, "tx_pps") >= HOST_PPS_TH or
            last_val(x, "rx_pps") >= HOST_PPS_TH
            for x in host_trace_other
        )

        link_bad = any(
            last_val(x, "mbps") >= LINK_MBPS_TH
            for x in link_trace_other
        )

        label = "bad" if host_bad or link_bad else "good"
        selected_score = 0.0
        other_candidate_score = -1.0 if label == "bad" else 1.0
        final_score = other_candidate_score


    elif decision == "ip":
        # drops = [
        #     drop_ratio(x["before"]["tx_pps"], last_val(x, "tx_pps"))
        #     for x in host_trace_selected
        #     if x.get("before", {}).get("tx_pps", 0.0) > 0
        # ]
        drops = [
            drop_ratio(x["before"]["rx_pps"], last_val(x, "rx_pps"))
            for x in host_trace_selected
            if x.get("before", {}).get("rx_pps", 0.0) > 0
        ]

        selected_score = mean2(drops)

        other_host_bad = any(
            last_val(x, "tx_pps") >= HOST_PPS_TH or
            last_val(x, "rx_pps") >= HOST_PPS_TH
            for x in host_trace_other
        )

        other_candidate_score = -1.0 if other_host_bad else 0.0
        final_score = selected_score + 0.25 * other_candidate_score

        if selected_score > 0 and not other_host_bad:
            label = "good"
        elif selected_score > 0:
            label = "neutral"
        else:
            label = "bad"


    elif decision == "rrm":
        drops = []

        for x in link_trace_selected:
            before = x.get("before", {}).get("mbps", 0.0)
            after = last_val(x, "mbps")

            # Score RRM only if the selected link was congested before.
            if before >= LINK_MBPS_TH:
                drops.append(drop_ratio(before, after))

        selected_score = mean2(drops)

        # Penalize only if another candidate link crosses 9 Mbps after RRM.
        other_link_bad = any(
            last_val(x, "mbps") >= LINK_MBPS_TH
            for x in link_trace_other
        )

        other_candidate_score = -1.0 if other_link_bad else 0.0
        final_score = selected_score + 0.25 * other_candidate_score

        if selected_score > 0 and not other_link_bad:
            label = "good"
        elif selected_score > 0:
            label = "neutral"
        else:
            label = "bad"


    else:
        selected_score = 0.0
        other_candidate_score = 0.0
        final_score = 0.0
        label = "bad"

    if decision == "ip":
        result = "ip_shuffle improved the selected targets" if label == "good" else "ip_shuffle gave limited or weak improvement"
    elif decision == "rrm":
        result = "route_mutation improved the selected targets" if label == "good" else "route_mutation gave limited or weak improvement"
    # elif decision == "both":
    #     result = "combined mitigation improved the selected targets" if label == "good" else "combined mitigation gave limited or weak improvement"
    elif decision == "do_nothing":
        result = ("no mitigation was applied; system remained stable"
            if label in ["good", "neutral"]
            else "no mitigation was applied, but the condition worsened")
    else:
        result = "unknown decision"


    return {
        "label": label,
        "result": result,
        "score": round(final_score, 4),
        "selected_score": round(selected_score, 4),
        "other_candidate_score": round(other_candidate_score, 4),
        "validation_trace": {
            "selected_hosts": host_trace_selected,
            "selected_links": link_trace_selected,
            "other_candidate_hosts": host_trace_other,
            "other_candidate_links": link_trace_other
        }
    }
#average last 5 instead of only last point!!

    
# new compatible to validate_effect
# def make_example(scene, final_obj, validation_out):
def make_example(scene, final_obj, validation_out, ip_result, route_result): #new
    # new
    ip_str = ""
    if ip_result:
        ip_str = ", ".join([f"{h}->{ip}" for h, ip in ip_result.items()])

    route_str = ""
    if route_result:
        route_str = ", ".join([
            f"{r['host1']}-{r['host2']}:{r['option_number']}"
            for r in route_result
        ])
    # new

    return {
        "mtd_action": {
            "ip_changes": ip_str,
            "route_changes": route_str
        }, # new 
        "outcome": {
            "result": validation_out["result"],
            "label": validation_out["label"],
            "score": validation_out["score"],
            "selected_score": validation_out["selected_score"],
            "other_candidate_score": validation_out["other_candidate_score"]
        },
        "validation_trace": validation_out.get("validation_trace", {}),
        "candidates": {
            "host_stats": scene.get("flagged_host_stats", []),
            "link_stats": scene.get("flagged_link_stats", [])
        },
        "decision": {
            "final_decision": final_obj.get("final_decision"),
            "final_macs": final_obj.get("final_macs", []),
            "final_links": final_obj.get("final_links", [])
        }
    }


def save_example(example, filename=EXAMPLES_JSONL):
    with open(filename, "a", encoding="utf-8") as f:
        f.write(json.dumps(example) + "\n")


def json_check(prompt):
    out, latency = call_cloud_llm(prompt)

    try:
        json.loads(out)   # just check validity
        return out, latency
    except:
        print("[RETRY] invalid JSON, calling again...")
        out, latency = call_cloud_llm(prompt)
        return out, latency


def build_llm_history_summary(examples_jsonl=EXAMPLES_JSONL, n=5):
    if not os.path.exists(examples_jsonl):
        return ""

    rows = []
    try:
        with open(examples_jsonl, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except Exception as e:
        print("[WARN] could not read examples:", e)
        return ""

    if not rows:
        return ""

    recent = rows[-n:]

    compact = []
    for r in recent:
        compact.append({
            "decision": r.get("decision", {}),
            "mtd_action": r.get("mtd_action", {}),
            "outcome": r.get("outcome", {})
        })

    prompt = f"""
You are analyzing the recent history of an SDN mitigation system.

You are given the last {n} decision records. Each record contains:
- decision: what was decided (final_decision, final_macs, final_links)
- mtd_action: what action was actually executed (ip_changes, route_changes)
- outcome: what happened after (label, score, result)

Your job:
- Summarize what patterns you see across these decisions.
- Note which MACs and links keep appearing.
- Note whether actions are working (good), neutral, or failing (bad).
- Clearly state which specific decision and action gave a good outcome if any.
- Note if the same action is being repeated without improvement.
- Keep your summary concise and factual, in MAC and link ID language only.
- Do not use host names like h2 or h39.

Return ONLY valid JSON in this exact schema:
{{
  "pattern": "short description of overall pattern",
  "repeated_macs": ["MAC_ADDRESS"],
  "repeated_links": ["LINK_ID"],
  "working": "what decision/action gave good outcome and why",
  "not_working": "what is not working if anything",
}}

Data:
{json.dumps(compact, ensure_ascii=False)}

Return JSON only.
""".strip()
#   "suggestion": "what the next decision should consider"
    try:
        out, latency = call_cloud_llm(prompt)
        print(f"[HISTORY SUMMARY] latency={latency:.2f}s")
        parsed = json.loads(out)
        return json.dumps(parsed, ensure_ascii=False)
    except Exception as e:
        print("[WARN] history summary failed:", e)
        return ""


# # # static
# def build_llm_history_summary(examples_jsonl=EXAMPLES_JSONL, n=5):
#     if not os.path.exists(examples_jsonl):
#         return ""

#     rows = []
#     try:
#         with open(examples_jsonl, "r", encoding="utf-8") as f:
#             for line in f:
#                 line = line.strip()
#                 if not line:
#                     continue
#                 try:
#                     rows.append(json.loads(line))
#                 except Exception:
#                     continue
#     except Exception as e:
#         print("[WARN] could not read examples:", e)
#         return ""

#     if not rows:
#         return ""

#     recent = rows[-n:]
#     recent_operations = []

#     for r in recent:
#         decision = r.get("decision", {})
#         outcome = r.get("outcome", {})

#         recent_operations.append({
#             "decision": decision.get("final_decision", "unknown"),
#             "macs": decision.get("final_macs", []),
#             "links": decision.get("final_links", []),
#             "outcome": outcome.get("label", "unknown")
#         })

#     summary = {
#         "recent_operations": recent_operations,
#         "guidance": (
#             "Avoid repeating recent decisions on the same MACs or links "
#             "unless current telemetry clearly requires the same action."
#         )
#     }

#     return json.dumps(summary, ensure_ascii=False)



from google import genai
from google.genai import types

GEMINI_API_KEY = "AIzaSyDMYt8DsH_MIIs1ta18Wvj3iCr6B-0BlxM"
GEMINI_MODEL_NAME = "gemini-2.5-flash"

client = genai.Client(api_key=GEMINI_API_KEY)


def call_gemini(prompt):
    start = time.time()

    response = client.models.generate_content(
        model=GEMINI_MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction="Return ONLY valid JSON. No text.",
            temperature=0,
            top_p=0.9,
            response_mime_type="application/json",
        ),
    )

    latency = time.time() - start

    out = response.text.strip() if response.text else ""

    return out, latency

