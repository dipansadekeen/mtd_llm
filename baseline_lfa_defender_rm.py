#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LFADefender-style Reactive Rerouting Baseline.

Run:
python3 baseline_lfadefender_reroute.py --threshold-mbps 10 --pair-count 10 --dry-run

Real run:
python3 baseline_lfadefender_reroute.py --threshold-mbps 10 --pair-count 10

What it does:
1. Reads active host pairs from ONOS flows.
2. Reads congested links from link_stats_onos.csv.
3. Checks which active host pairs may use congested links.
4. Selects an alternate route avoiding congested links.
5. Calls route_shuffle_endpoint().
"""

import argparse
import time
import pandas as pd
import requests
from requests.auth import HTTPBasicAuth

try:
    from route_mutate_endpoint import route_shuffle_endpoint
except Exception as e:
    print(f"[LFA] ERROR importing route_shuffle_endpoint: {e}")
    route_shuffle_endpoint = None

try:
    from mtd_utils import RouteHistoryManager, all_hosts
except Exception:
    RouteHistoryManager = None
    all_hosts = []


# ============================================================
# ONOS active host pairs
# ============================================================

def mac_to_host(mac):
    try:
        last_hex = str(mac).strip().split(":")[-1]
        return f"h{int(last_hex, 16)}"
    except Exception:
        return None


def get_active_onos_host_pairs(
    onos_url="http://localhost:8181",
    username="onos",
    password="rocks",
    min_packets=1
):
    url = f"{onos_url}/onos/v1/flows"

    try:
        r = requests.get(url, auth=HTTPBasicAuth(username, password), timeout=5)
        r.raise_for_status()
        flows = r.json().get("flows", [])
    except Exception as e:
        print(f"[LFA] Could not fetch ONOS flows: {e}")
        return []

    pairs = set()

    for flow in flows:
        if flow.get("state") != "ADDED":
            continue

        if int(flow.get("packets", 0) or 0) < min_packets:
            continue

        src_mac = None
        dst_mac = None

        for c in flow.get("selector", {}).get("criteria", []):
            if c.get("type") == "ETH_SRC":
                src_mac = c.get("mac")
            elif c.get("type") == "ETH_DST":
                dst_mac = c.get("mac")

        if not src_mac or not dst_mac:
            continue

        h1 = mac_to_host(src_mac)
        h2 = mac_to_host(dst_mac)

        if h1 and h2 and h1 != h2:
            pairs.add(tuple(sorted([h1, h2])))

    pairs = sorted(pairs)

    print(f"[LFA] Active host pairs found: {len(pairs)}")
    for p in pairs:
        print(f"   active_pair={p[0]} <-> {p[1]}")

    return pairs


# ============================================================
# Link parsing
# ============================================================

def dpid_to_switch(device_id):
    dev = str(device_id).strip()
    if dev.startswith("of:"):
        try:
            return f"s{int(dev.replace('of:', ''), 16)}"
        except Exception:
            return dev
    return dev


# def parse_onos_link_id(link_id):
#     """
#     Example:
#     of:0000000000000001:2 -> of:0000000000000002:1

#     returns:
#     ('s1', 's2')
#     """
#     if "->" not in str(link_id):
#         return None

#     left, right = [x.strip() for x in str(link_id).split("->", 1)]

#     def endpoint_to_switch(ep):
#         parts = ep.split(":")
#         if len(parts) < 3:
#             return ep
#         return dpid_to_switch(f"{parts[0]}:{parts[1]}")

#     return tuple(sorted([endpoint_to_switch(left), endpoint_to_switch(right)]))


# def normalize_switch_link(link_str):
#     if "->" not in str(link_str):
#         return None

#     a, b = str(link_str).replace(" ", "").split("->", 1)
#     return tuple(sorted([a, b]))


# def parse_path_links(path_str):
#     links = []
#     for item in str(path_str).split(","):
#         lk = normalize_switch_link(item.strip())
#         if lk:
#             links.append(lk)
#     return links

# ============================================================
# Link parsing
# ============================================================

def normalize_onos_endpoint(ep):
    """
    Keep ONOS endpoint at port-level.

    Example:
        of:000000000000000b:2

    Meaning:
        switch b, port 2
    """
    return str(ep).strip().replace(" ", "")


def parse_onos_link_id(link_id):
    """
    Normalize link_stats_onos.csv link_id.

    Input:
        of:000000000000000b:2 -> of:000000000000000c:2

    Output:
        ('of:000000000000000b:2', 'of:000000000000000c:2')
    """
    if "->" not in str(link_id):
        return None

    left, right = [
        normalize_onos_endpoint(x)
        for x in str(link_id).split("->", 1)
    ]

    return tuple(sorted([left, right]))


def normalize_switch_link(link_str):
    """
    Normalize hop_list.csv path link.

    Input:
        of:000000000000000b:2 -> of:000000000000000c:2

    Output:
        ('of:000000000000000b:2', 'of:000000000000000c:2')
    """
    if "->" not in str(link_str):
        return None

    left, right = [
        normalize_onos_endpoint(x)
        for x in str(link_str).split("->", 1)
    ]

    return tuple(sorted([left, right]))


def parse_path_links(path_str):
    links = []
    for item in str(path_str).split(","):
        lk = normalize_switch_link(item.strip())
        if lk:
            links.append(lk)
    return links


# ============================================================
# CSV loading
# ============================================================

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

    print(f"[LFA] Loaded hop_list entries: {len(df)}")
    return df


def load_recent_route_map(route_history_csv):
    recent = {}

    try:
        rh = pd.read_csv(route_history_csv)
    except Exception as e:
        print(f"[LFA] Could not read route_history.csv: {e}")
        return recent

    if "host_a" not in rh.columns or "host_b" not in rh.columns:
        print("[LFA] route_history missing host_a/host_b.")
        return recent

    for _, row in rh.iterrows():
        pair = tuple(sorted([str(row["host_a"]), str(row["host_b"])]))

        opt = None

        if "current_option" in rh.columns:
            opt = row.get("current_option")
        elif "option_number" in rh.columns:
            opt = row.get("option_number")
        elif "history" in rh.columns:
            vals = [
                x.strip()
                for x in str(row.get("history", "")).split(",")
                if x.strip()
            ]
            if vals:
                opt = vals[-1]

        if opt is not None and str(opt).strip():
            recent[pair] = int(float(opt))

    print(f"[LFA] Loaded route history for {len(recent)} pairs.")
    return recent


def load_link_loads_and_congested(
    link_stats_csv,
    threshold_mbps=10.0,
    metric="max_mbps"
):
    link_loads = {}
    congested_links = set()

    try:
        df = pd.read_csv(link_stats_csv)
    except Exception as e:
        print(f"[LFA] Could not read link_stats file: {e}")
        return link_loads, congested_links

    if "link_id" not in df.columns:
        print("[LFA] link_stats missing link_id column.")
        return link_loads, congested_links

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp"])
        df = df.sort_values("timestamp").groupby("link_id").tail(1)

    for _, row in df.iterrows():
        sw_pair = parse_onos_link_id(row["link_id"])
        if sw_pair is None:
            continue

        rx = float(row.get("rx_mbps", 0) or 0)
        tx = float(row.get("tx_mbps", 0) or 0)

        if metric == "rx_mbps":
            load = rx
        elif metric == "tx_mbps":
            load = tx
        else:
            load = max(rx, tx)

        link_loads[sw_pair] = load

        if load >= float(threshold_mbps):
            congested_links.add(sw_pair)

    print(f"[LFA] Loaded link loads: {len(link_loads)}")
    print(f"[LFA] Congested links >= {threshold_mbps} Mbps: {len(congested_links)}")

    for lk in sorted(congested_links):
        print(f"   congested={lk}, load={link_loads.get(lk)} Mbps")

    return link_loads, congested_links


# ============================================================
# LFADefender-style rerouting logic
# ============================================================

def get_current_route_row(pair_df, pair_key, recent_route_map):
    """
    Determine current route from route_history.
    If no history exists, use lowest option number as assumed current route.
    """
    current_opt = recent_route_map.get(pair_key)

    if current_opt is not None:
        match = pair_df[pair_df["option_number"] == int(current_opt)]
        if not match.empty:
            return match.iloc[0]

    pair_df = pair_df.sort_values(["option_number"])
    return pair_df.iloc[0] if not pair_df.empty else None


def path_crosses_congested(row, congested_links):
    links = set(row["norm_links"])
    return bool(links.intersection(congested_links))


def compute_link_density_from_active_routes(df, active_pairs, recent_route_map):
    """
    Approximate LFADefender-style flow density.

    Counts how many currently active host-pair routes use each switch link.
    Higher count = higher flow density.
    """
    link_density = {}
    valid_hop_pairs = set(df["pair_key"].tolist())

    for pair_key in active_pairs:
        if pair_key not in valid_hop_pairs:
            continue

        pair_df = df[df["pair_key"] == pair_key].copy()

        current_row = get_current_route_row(
            pair_df=pair_df,
            pair_key=pair_key,
            recent_route_map=recent_route_map
        )

        if current_row is None:
            continue

        for lk in current_row["norm_links"]:
            link_density[lk] = link_density.get(lk, 0) + 1

    print(f"[LFA] Computed flow-density for {len(link_density)} links.")
    for lk, den in sorted(link_density.items(), key=lambda x: x[1], reverse=True):
        print(f"   density_link={lk}, density={den}")

    return link_density


def choose_lfa_alternate_route(
    pair_df,
    current_option,
    congested_links,
    link_loads,
    max_hops=None,
    reserved_links=None,
    link_density=None
):
    """
    Improved LFADefender-style alternate path selection:
    1. avoid congested links
    2. avoid current option
    3. avoid routes already selected in this cycle
    4. avoid high-flow-density links
    5. minimize max path load
    6. minimize hop count
    """
    if reserved_links is None:
        reserved_links = set()

    if link_density is None:
        link_density = {}

    candidates = []

    for _, row in pair_df.iterrows():
        opt = int(row["option_number"])

        if current_option is not None and opt == int(current_option):
            continue

        if max_hops is not None and int(row["hop_count"]) > int(max_hops):
            continue

        links = row["norm_links"]

        # Reject paths that still cross congested links.
        if any(lk in congested_links for lk in links):
            continue

        path_loads = [float(link_loads.get(lk, 0.0)) for lk in links]
        max_path_load = max(path_loads) if path_loads else 0.0

        overlap_count = sum(1 for lk in links if lk in reserved_links)
        density_score = sum(int(link_density.get(lk, 0)) for lk in links)

        score = (
            overlap_count,
            density_score,
            round(max_path_load, 6),
            int(row["hop_count"]),
            opt
        )

        candidates.append((score, row))

    if not candidates:
        return None, None

    candidates.sort(key=lambda x: x[0])
    return candidates[0][1], candidates[0][0]


def select_lfadefender_candidates(
    hoplist_csv="hop_list.csv",
    route_history_csv="route_history.csv",
    link_stats_csv="link_stats_onos.csv",
    threshold_mbps=10.0,
    pair_count_per_cycle=10,
    max_hops=None,
    onos_url="http://localhost:8181",
    onos_user="onos",
    onos_pass="rocks",
    min_packets=1
):
    df = load_hoplist(hoplist_csv)
    recent_route_map = load_recent_route_map(route_history_csv)

    link_loads, congested_links = load_link_loads_and_congested(
        link_stats_csv=link_stats_csv,
        threshold_mbps=threshold_mbps
    )

    if not congested_links:
        print("[LFA] No congested links detected. No rerouting needed.")
        return []

    active_pairs = get_active_onos_host_pairs(
        onos_url=onos_url,
        username=onos_user,
        password=onos_pass,
        min_packets=min_packets
    )

    if not active_pairs:
        print("[LFA] No active host pairs found. No rerouting needed.")
        return []

    link_density = compute_link_density_from_active_routes(
        df=df,
        active_pairs=active_pairs,
        recent_route_map=recent_route_map
    )

    reserved_links = set()
    selected = []
    valid_hop_pairs = set(df["pair_key"].tolist())

    print("\n[LFA] LFADefender-style affected-flow rerouting")

    for pair_key in active_pairs:
        if len(selected) >= int(pair_count_per_cycle):
            break

        if pair_key not in valid_hop_pairs:
            print(f"[LFA] Active pair missing in hop_list: {pair_key}")
            continue

        pair_df = df[df["pair_key"] == pair_key].copy()

        current_row = get_current_route_row(
            pair_df=pair_df,
            pair_key=pair_key,
            recent_route_map=recent_route_map
        )

        if current_row is None:
            print(f"[LFA] No current route row found for {pair_key}")
            continue

        current_option = int(current_row["option_number"])

        # ------------------------------------------------------------
        # Robust affected-pair check.
        # Do not rely only on route_history current_opt.
        # If ANY known option for this active pair crosses a congested link,
        # treat the active pair as affected.
        # ------------------------------------------------------------
        affected_rows = pair_df[
            pair_df["norm_links"].apply(
                lambda links: bool(set(links).intersection(congested_links))
            )
        ]

        if affected_rows.empty:
            print(
                f"[LFA] Not affected: {pair_key}; "
                f"none of its known route options cross congested links; "
                f"current_opt_assumed={current_option}"
            )
            continue

        print(
            f"[LFA] AFFECTED active pair: {pair_key}; "
            f"{len(affected_rows)} option(s) cross congested links; "
            f"current_opt_assumed={current_option}"
        )

        new_row, score = choose_lfa_alternate_route(
            pair_df=pair_df,
            current_option=current_option,
            congested_links=congested_links,
            link_loads=link_loads,
            max_hops=max_hops,
            reserved_links=reserved_links,
            link_density=link_density
        )

        if new_row is None:
            print(f"[LFA] No clean alternate route for affected pair: {pair_key}")
            continue

        candidate = {
            "host1": str(new_row["host1"]),
            "host2": str(new_row["host2"]),
            "option_number": int(new_row["option_number"])
        }

        selected.append(candidate)
        reserved_links.update(new_row["norm_links"])

        print(
            f"[LFA] SELECTED {pair_key}: "
            f"current_opt={current_option} -> new_opt={candidate['option_number']} "
            f"score={score} links={new_row['norm_links']}"
        )

    print(f"[LFA] selected={len(selected)} reroute candidates")
    return selected


# ============================================================
# Apply endpoint
# ============================================================

def apply_candidates_with_endpoint(candidates, update_route_history=True):
    if not candidates:
        print("[LFA] No candidates to apply.")
        return None

    if route_shuffle_endpoint is None:
        print("[LFA] route_shuffle_endpoint unavailable.")
        return None

    host_pairs = []
    opt_list = []
    route_manager = None

    if update_route_history and RouteHistoryManager is not None:
        try:
            route_manager = RouteHistoryManager(all_hosts, queue_size=10)
            route_manager.load_from_csv()
            print("[LFA] RouteHistoryManager loaded.")
        except Exception as e:
            print(f"[LFA] Could not load route manager: {e}")
            route_manager = None

    for c in candidates:
        h1 = str(c["host1"])
        h2 = str(c["host2"])
        opt = str(c["option_number"])

        host_pairs.append(f"{h1},{h2}")
        opt_list.append(opt)

        if route_manager is not None:
            print(f"[LFA] Updating route history: {h1}-{h2} -> opt {opt}")
            route_manager.update_pair(h1, h2, opt)

    hosts_arg = ";".join(host_pairs)
    opt_arg = ";".join(opt_list)

    if route_manager is not None:
        try:
            route_manager.save_to_csv()
            print("[LFA] route_history.csv saved.")
        except Exception as e:
            print(f"[LFA] Failed saving route history: {e}")

    print("[LFA] Calling route endpoint:")
    print(f'   hosts="{hosts_arg}"')
    print(f'   opt="{opt_arg}"')

    result = route_shuffle_endpoint(
        specific_multiple=True,
        hosts=hosts_arg,
        opt=opt_arg
    )

    print("[LFA] Route endpoint finished.")

    return {
        "endpoint_result": result,
        "route_changes": candidates,
        "hosts_arg": hosts_arg,
        "opt_arg": opt_arg
    }


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--hoplist", default="hop_list.csv")
    parser.add_argument("--route-history", default="route_history.csv")
    parser.add_argument("--link-stats", default="link_stats_onos.csv")

    parser.add_argument("--threshold-mbps", type=float, default=10.0)
    parser.add_argument("--pair-count", type=int, default=10)
    parser.add_argument("--max-hops", type=int, default=None)

    parser.add_argument("--onos-url", default="http://localhost:8181")
    parser.add_argument("--onos-user", default="onos")
    parser.add_argument("--onos-pass", default="rocks")
    parser.add_argument("--min-packets", type=int, default=1)

    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval", type=int, default=10)

    args = parser.parse_args()

    while True:
        candidates = select_lfadefender_candidates(
            hoplist_csv=args.hoplist,
            route_history_csv=args.route_history,
            link_stats_csv=args.link_stats,
            threshold_mbps=args.threshold_mbps,
            pair_count_per_cycle=args.pair_count,
            max_hops=args.max_hops,
            onos_url=args.onos_url,
            onos_user=args.onos_user,
            onos_pass=args.onos_pass,
            min_packets=args.min_packets
        )

        print("[LFA] Candidates:", candidates)

        if not args.dry_run:
            apply_candidates_with_endpoint(candidates)

        if not args.loop:
            break

        time.sleep(args.interval)


if __name__ == "__main__":
    main()