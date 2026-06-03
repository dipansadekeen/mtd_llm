#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import random
import os
import sys
import pandas as pd
import time
from route_mutate_endpoint import route_shuffle_endpoint
from mtd_utils import RouteHistoryManager, all_hosts


def normalize_link(link_str):
    """
    Normalize ONOS link as undirected pair of endpoints.
    Example:
      'of:...2:1 -> of:...b:4'
      and reverse become the same key.
    """
    link_str = str(link_str).strip()

    if "->" not in link_str:
        return None

    a, b = [x.strip() for x in link_str.split("->", 1)]

    if not a or not b:
        return None

    return tuple(sorted([a, b]))


def parse_path_links(path_str):
    links = []

    for item in str(path_str).split(","):
        item = item.strip()
        if not item:
            continue

        lk = normalize_link(item)
        if lk:
            links.append(lk)

    return links


def load_hoplist(hoplist_csv):
    df = pd.read_csv(
        hoplist_csv,
        header=None,
        names=[
            "host1",
            "host2",
            "option_number",
            "hop_count",
            "src_mac",
            "dst_mac",
            "path"
        ]
    )

    df["host1"] = df["host1"].astype(str)
    df["host2"] = df["host2"].astype(str)
    df["option_number"] = df["option_number"].astype(int)
    df["hop_count"] = df["hop_count"].astype(float).astype(int)

    df["pair_key"] = df.apply(
        lambda r: tuple(sorted([str(r["host1"]), str(r["host2"])])),
        axis=1
    )

    df["norm_links"] = df["path"].apply(parse_path_links)

    return df


def load_link_loads(link_stats_csv, metric="max_mbps"):
    """
    Returns:
      link_loads = { normalized_link: load_value }
    """
    link_loads = {}

    try:
        df = pd.read_csv(link_stats_csv)
    except Exception as e:
        print(f"[LFADEFENDER] Could not read {link_stats_csv}: {e}")
        return link_loads

    if "link_id" not in df.columns:
        print("[LFADEFENDER] link_stats missing link_id column.")
        return link_loads

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp"])
        df = df.sort_values("timestamp").groupby("link_id").tail(1)

    for _, row in df.iterrows():
        lk = normalize_link(row["link_id"])
        if lk is None:
            continue

        rx_mbps = float(row.get("rx_mbps", 0) or 0)
        tx_mbps = float(row.get("tx_mbps", 0) or 0)
        rx_pps = float(row.get("rx_pps", 0) or 0)
        tx_pps = float(row.get("tx_pps", 0) or 0)

        if metric == "rx_mbps":
            load = rx_mbps
        elif metric == "tx_mbps":
            load = tx_mbps
        elif metric == "max_pps":
            load = max(rx_pps, tx_pps)
        else:
            load = max(rx_mbps, tx_mbps)

        link_loads[lk] = load

    print(f"[LFADEFENDER] Loaded {len(link_loads)} link-load entries.")
    return link_loads


def find_congested_links(link_loads, threshold_mbps):
    congested = {
        lk for lk, load in link_loads.items()
        if load >= float(threshold_mbps)
    }

    print(f"[LFADEFENDER] Congested links >= {threshold_mbps} Mbps: {len(congested)}")
    for lk in sorted(congested):
        print(f"  congested={lk}, load={link_loads.get(lk)}")

    return congested


def path_uses_congested_link(norm_links, congested_links):
    return any(lk in congested_links for lk in norm_links)


def max_path_load(norm_links, link_loads):
    vals = [float(link_loads.get(lk, 0.0)) for lk in norm_links]
    return max(vals) if vals else 0.0


def choose_minmax_option(pair_df, link_loads, congested_links):
    """
    LFADefender-style route choice:
      choose path with minimum maximum link utilization/load.

    Tie-breakers:
      1. fewer congested links
      2. lower max path load
      3. lower hop count
      4. lower option number
    """
    scored = []

    for _, row in pair_df.iterrows():
        links = row["norm_links"]

        congested_count = sum(1 for lk in links if lk in congested_links)
        worst_load = max_path_load(links, link_loads)
        hop_count = int(row["hop_count"])
        opt = int(row["option_number"])

        score = (
            congested_count,
            worst_load,
            hop_count,
            opt
        )

        scored.append((score, row))

    if not scored:
        return None, None

    scored.sort(key=lambda x: x[0])
    return scored[0][1], scored[0][0]


def select_lfadefender_candidates(
    hoplist_csv="hop_list.csv",
    link_stats_csv="link_stats_onos.csv",
    route_history_csv="route_history.csv",
    threshold_mbps=10.0,
    max_pair_count=10,
    metric="max_mbps"
):
    df = load_hoplist(hoplist_csv)
    link_loads = load_link_loads(link_stats_csv, metric=metric)
    congested_links = find_congested_links(link_loads, threshold_mbps)

    if not congested_links:
        print("[LFADEFENDER] No congested links found. No reroute needed.")
        return []

    # # Find pairs whose at least one path uses congested links.
    # affected_pairs = []

    # for pair_key, g in df.groupby("pair_key"):
    #     uses_bad = g["norm_links"].apply(
    #         lambda links: path_uses_congested_link(links, congested_links)
    #     ).any()

    #     if uses_bad:
    #         affected_pairs.append(pair_key)

    recent_route_map = load_recent_route_map(route_history_csv)
    active_pairs = get_active_onos_host_pairs()

    affected_pairs = []

    for pair_key in active_pairs:
        pair_df = df[df["pair_key"] == pair_key].copy()

        if pair_df.empty:
            continue

        current_opt = recent_route_map.get(pair_key)

        if current_opt is None:
            current_row = pair_df.sort_values("option_number").iloc[0]
        else:
            match = pair_df[pair_df["option_number"] == int(current_opt)]
            if match.empty:
                continue
            current_row = match.iloc[0]

        if path_uses_congested_link(current_row["norm_links"], congested_links):
            affected_pairs.append(pair_key)

    print(f"[LFADEFENDER] Affected pairs found: {len(affected_pairs)}")

    candidates = []

    for pair_key in affected_pairs:
        if len(candidates) >= int(max_pair_count):
            break

        pair_df = df[df["pair_key"] == pair_key].copy()

        chosen_row, score = choose_minmax_option(
            pair_df=pair_df,
            link_loads=link_loads,
            congested_links=congested_links
        )

        if chosen_row is None:
            continue

        h1 = str(chosen_row["host1"])
        h2 = str(chosen_row["host2"])
        opt = int(chosen_row["option_number"])

        candidate = {
            "host1": h1,
            "host2": h2,
            "option_number": opt
        }

        print(
            f"[LFADEFENDER] pair={h1}->{h2} "
            f"chosen_opt={opt} score={score} "
            f"links={chosen_row['norm_links']}"
        )

        candidates.append(candidate)

    print(f"[LFADEFENDER] selected={len(candidates)} candidates")
    return candidates


def apply_candidates_with_endpoint(candidates, update_route_history=True):
    if not candidates:
        print("[LFADEFENDER] No candidates to apply.")
        return None

    host_pairs = []
    opt_list = []

    route_manager = None

    if update_route_history:
        try:
            route_manager = RouteHistoryManager(all_hosts, queue_size=10)
            route_manager.load_from_csv()
            print("[LFADEFENDER] RouteHistoryManager loaded.")
        except Exception as e:
            print(f"[LFADEFENDER] Could not load route manager: {e}")
            route_manager = None

    for c in candidates:
        h1 = str(c["host1"])
        h2 = str(c["host2"])
        opt = str(c["option_number"])

        host_pairs.append(f"{h1},{h2}")
        opt_list.append(opt)

        if route_manager is not None:
            route_manager.update_pair(h1, h2, opt)

    hosts_arg = ";".join(host_pairs)
    opt_arg = ";".join(opt_list)

    if route_manager is not None:
        route_manager.save_to_csv()
        print("[LFADEFENDER] route_history.csv saved.")

    print("[LFADEFENDER] Calling route endpoint:")
    print(f'  hosts="{hosts_arg}"')
    print(f'  opt="{opt_arg}"')

    result = route_shuffle_endpoint(
        specific_multiple=True,
        hosts=hosts_arg,
        opt=opt_arg
    )

    return {
        "endpoint_result": result,
        "route_changes": candidates,
        "hosts_arg": hosts_arg,
        "opt_arg": opt_arg
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--hoplist", default="hop_list.csv")
    parser.add_argument("--link-stats", default="link_stats_onos.csv")
    parser.add_argument("--route-history", default="route_history.csv")

    parser.add_argument("--threshold-mbps", type=float, default=10.0)
    parser.add_argument("--max-pair-count", type=int, default=10)
    parser.add_argument("--metric", default="max_mbps")

    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval", type=int, default=20)


    args = parser.parse_args()

    # candidates = select_lfadefender_candidates(
    #     hoplist_csv=args.hoplist,
    #     link_stats_csv=args.link_stats,
    #     route_history_csv=args.route_history,
    #     threshold_mbps=args.threshold_mbps,
    #     max_pair_count=args.max_pair_count,
    #     metric=args.metric
    # )

    # print("\n[LFADEFENDER] Final candidates:")
    # for c in candidates:
    #     print(c)

    # if not args.dry_run:
    #     apply_candidates_with_endpoint(candidates)

    cycle = 0

    while True:
        cycle += 1
        print("\n" + "=" * 70)
        print(f"[LFADEFENDER] CYCLE {cycle}")
        print("=" * 70)

        candidates = select_lfadefender_candidates(
            hoplist_csv=args.hoplist,
            link_stats_csv=args.link_stats,
            route_history_csv=args.route_history,
            threshold_mbps=args.threshold_mbps,
            max_pair_count=args.max_pair_count,
            metric=args.metric
        )

        print("\n[LFADEFENDER] Final candidates:")
        for c in candidates:
            print(c)

        if not args.dry_run:
            apply_candidates_with_endpoint(candidates)

        if not args.loop:
            break

        print(f"\n[LFADEFENDER] Sleeping {args.interval}s...")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()