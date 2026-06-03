#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Jafarian-style Efficient Random Route Mutation using ACTIVE ONOS host pairs.

Main idea:
1. Read active host-to-host flows from ONOS /onos/v1/flows.
2. Convert ETH_SRC / ETH_DST MACs to Mininet host names.
3. Select only currently active host pairs.
4. For each active pair, read candidate paths from hop_list.csv.
5. Score route options using:
   - congested link count
   - hop limit
   - recent route reuse
   - overlap with already selected routes
   - max path load
   - hop count
6. Randomly select among top feasible options.
7. Call route_shuffle_endpoint().

This follows the flow-based route mutation idea: route mutation is applied to active flows, not all host pairs.
"""
# solver version : https://chatgpt.com/s/t_69f1416745288191849a3f45e8cfb55d
import argparse
import random
import time
import pandas as pd
import requests
from requests.auth import HTTPBasicAuth

try:
    from route_mutate_endpoint import route_shuffle_endpoint
except Exception as e:
    print(f"[JAFARIAN] ERROR: Could not import route_shuffle_endpoint: {e}")
    route_shuffle_endpoint = None

try:
    from mtd_utils import RouteHistoryManager, all_hosts
except Exception:
    RouteHistoryManager = None
    all_hosts = []


# ============================================================
# ONOS active host-pair detection
# ============================================================

def mac_to_host(mac):
    """
    Convert Mininet-style MAC to host name.

    Example:
        00:00:00:00:00:01 -> h1
        00:00:00:00:00:28 -> h40
        00:00:00:00:00:1A -> h26
    """
    try:
        last_hex = str(mac).strip().split(":")[-1]
        return f"h{int(last_hex, 16)}"
    except Exception:
        return None


def get_active_onos_host_pairs(
    onos_url="http://localhost:8181",
    username="onos",
    password="rocks",
    min_packets=1,
    use_increasing_bytes=False,
    sample_gap=2
):
    """
    Return active host pairs from ONOS.

    Default mode:
        Active if packets > min_packets.

    Optional better mode:
        use_increasing_bytes=True
        Active if byte counter increases between two samples.
    """

    def fetch_flows():
        url = f"{onos_url}/onos/v1/flows"
        r = requests.get(
            url,
            auth=HTTPBasicAuth(username, password),
            timeout=5
        )
        r.raise_for_status()
        return r.json().get("flows", [])

    def extract_pairs_from_flows(flows, prev_bytes=None):
        pairs = set()
        current_bytes = {}

        for flow in flows:
            if flow.get("state") != "ADDED":
                continue

            packets = int(flow.get("packets", 0) or 0)
            bytes_count = int(flow.get("bytes", 0) or 0)

            if packets < min_packets:
                continue

            flow_id = str(flow.get("id", ""))
            criteria = flow.get("selector", {}).get("criteria", [])

            src_mac = None
            dst_mac = None

            for c in criteria:
                if c.get("type") == "ETH_SRC":
                    src_mac = c.get("mac")
                elif c.get("type") == "ETH_DST":
                    dst_mac = c.get("mac")

            if not src_mac or not dst_mac:
                continue

            h1 = mac_to_host(src_mac)
            h2 = mac_to_host(dst_mac)

            if not h1 or not h2 or h1 == h2:
                continue

            pair = tuple(sorted([h1, h2]))
            current_bytes[flow_id] = bytes_count

            if prev_bytes is None:
                pairs.add(pair)
            else:
                old_bytes = prev_bytes.get(flow_id, None)
                if old_bytes is not None and bytes_count > old_bytes:
                    pairs.add(pair)

        return sorted(pairs), current_bytes

    try:
        flows1 = fetch_flows()

        if not use_increasing_bytes:
            pairs, _ = extract_pairs_from_flows(flows1, prev_bytes=None)
        else:
            _, bytes1 = extract_pairs_from_flows(flows1, prev_bytes=None)
            time.sleep(sample_gap)
            flows2 = fetch_flows()
            pairs, _ = extract_pairs_from_flows(flows2, prev_bytes=bytes1)

    except Exception as e:
        print(f"[JAFARIAN] Could not fetch ONOS active flows: {e}")
        return []

    print(f"[JAFARIAN] Active ONOS host pairs found: {len(pairs)}")
    for p in pairs:
        print(f"   active_pair = {p[0]} <-> {p[1]}")

    return pairs


# ============================================================
# Link normalization and mapping
# ============================================================

def dpid_to_switch(device_id):
    dev = str(device_id).strip()

    if dev.startswith("of:"):
        hex_part = dev.replace("of:", "")
        try:
            return f"s{int(hex_part, 16)}"
        except Exception:
            return dev

    return dev


def normalize_switch_link(link_str):
    link_str = str(link_str).strip().replace(" ", "")

    if "->" not in link_str:
        return None

    a, b = link_str.split("->", 1)
    a = a.strip()
    b = b.strip()

    if not a or not b:
        return None

    return tuple(sorted([a, b]))


def parse_onos_link_id(link_id):
    link_id = str(link_id).strip()

    if "->" not in link_id:
        return None

    left, right = [x.strip() for x in link_id.split("->", 1)]

    def endpoint_to_switch(endpoint):
        parts = endpoint.strip().split(":")
        if len(parts) < 3:
            return endpoint

        device_id = f"{parts[0]}:{parts[1]}"
        return dpid_to_switch(device_id)

    s_left = endpoint_to_switch(left)
    s_right = endpoint_to_switch(right)

    return tuple(sorted([s_left, s_right]))


def load_link_load_map(link_stats_csv, load_metric="max_mbps"):
    link_loads = {}
    onos_link_map = {}

    try:
        df = pd.read_csv(link_stats_csv)
    except Exception as e:
        print(f"[JAFARIAN] Could not read {link_stats_csv}: {e}")
        return link_loads, onos_link_map

    if "link_id" not in df.columns:
        print(f"[JAFARIAN] {link_stats_csv} missing link_id column.")
        return link_loads, onos_link_map

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp"])
        df = df.sort_values("timestamp").groupby("link_id").tail(1)

    for _, row in df.iterrows():
        link_id = row["link_id"]
        sw_pair = parse_onos_link_id(link_id)

        if sw_pair is None:
            continue

        rx_mbps = float(row.get("rx_mbps", 0) or 0)
        tx_mbps = float(row.get("tx_mbps", 0) or 0)
        rx_pps = float(row.get("rx_pps", 0) or 0)
        tx_pps = float(row.get("tx_pps", 0) or 0)

        if load_metric == "rx_mbps":
            load = rx_mbps
        elif load_metric == "tx_mbps":
            load = tx_mbps
        elif load_metric == "max_pps":
            load = max(rx_pps, tx_pps)
        else:
            load = max(rx_mbps, tx_mbps)

        link_loads[sw_pair] = load
        onos_link_map[sw_pair] = str(link_id)

    print(f"[JAFARIAN] Loaded {len(link_loads)} ONOS link-load entries.")
    return link_loads, onos_link_map


# ============================================================
# hop_list and route history helpers
# ============================================================

def parse_path_links(path_str):
    links = []

    for item in str(path_str).split(","):
        item = item.strip()
        if not item:
            continue

        lk = normalize_switch_link(item)
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
    df["src_mac"] = df["src_mac"].astype(str).str.upper()
    df["dst_mac"] = df["dst_mac"].astype(str).str.upper()

    df["pair_key"] = df.apply(
        lambda r: tuple(sorted([str(r["host1"]), str(r["host2"])])),
        axis=1
    )

    df["norm_links"] = df["path"].apply(parse_path_links)

    print(f"[JAFARIAN] Loaded hop_list entries: {len(df)}")
    return df


def load_recent_route_map(route_history_csv):
    recent = {}

    try:
        rh = pd.read_csv(route_history_csv)
    except Exception as e:
        print(f"[JAFARIAN] Could not read route history: {e}")
        return recent

    if "host_a" not in rh.columns or "host_b" not in rh.columns:
        print("[JAFARIAN] route_history missing host_a/host_b. Skipping recent-route penalty.")
        return recent

    for _, row in rh.iterrows():
        pair_key = tuple(sorted([str(row["host_a"]), str(row["host_b"])]))
        opt = None

        if "current_option" in rh.columns:
            opt = row.get("current_option")
        elif "option_number" in rh.columns:
            opt = row.get("option_number")
        elif "history" in rh.columns:
            vals = []
            for x in str(row.get("history", "")).split(","):
                x = x.strip()
                if x:
                    vals.append(x)
            if vals:
                opt = vals[-1]

        if opt is not None and str(opt).strip():
            recent[pair_key] = str(opt).strip()

    print(f"[JAFARIAN] Loaded recent route history for {len(recent)} pairs.")
    return recent


def build_protected_pairs(df, protected_dst="h40"):
    pairs = set()

    for _, row in df.iterrows():
        h1 = str(row["host1"])
        h2 = str(row["host2"])

        if protected_dst in [h1, h2]:
            pairs.add(tuple(sorted([h1, h2])))

    return sorted(pairs)


# ============================================================
# Jafarian-style route scoring
# ============================================================

def score_option(
    row,
    recent_route_map,
    reserved_links,
    link_loads,
    max_hops=None,
    load_threshold_mbps=None
):
    pair_key = row["pair_key"]
    option_number = int(row["option_number"])
    hop_count = int(row["hop_count"])
    links = row["norm_links"]

    recent = recent_route_map.get(pair_key)
    reuse_previous = 1 if recent is not None and str(option_number) == str(recent) else 0

    hop_violation = 1 if max_hops is not None and hop_count > max_hops else 0

    overlap = sum(reserved_links.get(lk, 0) for lk in links)

    path_loads = [float(link_loads.get(lk, 0.0)) for lk in links]
    max_path_load = max(path_loads) if path_loads else 0.0

    if load_threshold_mbps is not None:
        high_load_count = sum(1 for load in path_loads if load >= float(load_threshold_mbps))
    else:
        high_load_count = 0

    return (
        high_load_count,
        hop_violation,
        reuse_previous,
        overlap,
        round(max_path_load, 6),
        hop_count,
        option_number
    )


def choose_option_for_pair(
    pair_df,
    recent_route_map,
    reserved_links,
    link_loads,
    max_hops=None,
    load_threshold_mbps=None,
    top_k_random_pool=3
):
    scored = []

    for _, row in pair_df.iterrows():
        score = score_option(
            row=row,
            recent_route_map=recent_route_map,
            reserved_links=reserved_links,
            link_loads=link_loads,
            max_hops=max_hops,
            load_threshold_mbps=load_threshold_mbps
        )
        scored.append((score, row))

    if not scored:
        return None, None

    scored.sort(key=lambda x: x[0])

    # clean = [(s, r) for s, r in scored if s[0] == 0 and s[1] == 0]

    # pool_source = clean if clean else scored
    clean = [(s, r) for s, r in scored if s[0] == 0 and s[1] == 0]

    if not clean:
        print("[JAFARIAN] No route satisfies load and hop constraints for this pair.")
        return None, None

    pool_source = clean
    pool = pool_source[:max(1, int(top_k_random_pool))]

    chosen_score, chosen_row = random.choice(pool)
    return chosen_row, chosen_score


def reserve_links(row, reserved_links):
    for lk in row["norm_links"]:
        reserved_links[lk] = reserved_links.get(lk, 0) + 1


def pair_sort_key(pair_key, recent_route_map):
    has_history = 1 if pair_key in recent_route_map else 0
    return (has_history, pair_key)


# ============================================================
# Candidate generation and endpoint application
# ============================================================

def select_jafarian_candidates(
    hoplist_csv="hop_list.csv",
    route_history_csv="route_history.csv",
    link_stats_csv="link_stats_onos.csv",
    protected_dst="h40",
    pair_count_per_cycle=10,
    max_hops=6,
    load_threshold_mbps=None,
    top_k_random_pool=3,
    seed=None,
    onos_url="http://localhost:8181",
    onos_user="onos",
    onos_pass="rocks",
    min_packets=1,
    use_increasing_bytes=False,
    sample_gap=2,
    fallback_to_h40=True
):
    if seed is not None:
        random.seed(seed)

    df = load_hoplist(hoplist_csv)
    recent_route_map = load_recent_route_map(route_history_csv)
    link_loads, _ = load_link_load_map(link_stats_csv)

    # active_pairs = get_active_onos_host_pairs(
    #     onos_url=onos_url,
    #     username=onos_user,
    #     password=onos_pass,
    #     min_packets=min_packets,
    #     use_increasing_bytes=use_increasing_bytes,
    #     sample_gap=sample_gap
    # )
    active_pairs = get_active_onos_host_pairs(
        onos_url=onos_url,
        username=onos_user,
        password=onos_pass,
        min_packets=min_packets,
        use_increasing_bytes=use_increasing_bytes,
        sample_gap=sample_gap
    )

    valid_hop_pairs = set(df["pair_key"].tolist())

    protected_pairs = []
    missing_pairs = []

    for pair in active_pairs:
        if pair in valid_hop_pairs:
            protected_pairs.append(pair)
        else:
            missing_pairs.append(pair)

    if missing_pairs:
        print("[JAFARIAN] Active ONOS pairs missing from hop_list.csv:")
        for p in missing_pairs:
            print(f"   missing: {p[0]} <-> {p[1]}")

    # if not protected_pairs and fallback_to_h40:
    #     print("[JAFARIAN] No active ONOS pairs matched hop_list.csv. Falling back to h40 pairs.")
    #     protected_pairs = build_protected_pairs(df, protected_dst=protected_dst)
    if not protected_pairs:
        print("[JAFARIAN] No active ONOS pairs matched hop_list.csv.")
        print("[JAFARIAN] Jafarian baseline will NOT fall back to fixed h40 pairs.")
        return []
    
    protected_pairs = sorted(
        protected_pairs,
        key=lambda pk: pair_sort_key(pk, recent_route_map)
    )

    selected = []
    reserved_links = {}

    print("\n[JAFARIAN] Active-flow Efficient RRM baseline")
    print(f"[JAFARIAN] candidate_pairs={len(protected_pairs)}")
    print(f"[JAFARIAN] pair_count_per_cycle={pair_count_per_cycle}")
    print(f"[JAFARIAN] max_hops={max_hops}")
    print(f"[JAFARIAN] load_threshold_mbps={load_threshold_mbps}")
    print(f"[JAFARIAN] top_k_random_pool={top_k_random_pool}")

    for pair_key in protected_pairs:
        if len(selected) >= int(pair_count_per_cycle):
            break

        pair_df = df[df["pair_key"] == pair_key].copy()

        chosen_row, chosen_score = choose_option_for_pair(
            pair_df=pair_df,
            recent_route_map=recent_route_map,
            reserved_links=reserved_links,
            link_loads=link_loads,
            max_hops=max_hops,
            load_threshold_mbps=load_threshold_mbps,
            top_k_random_pool=top_k_random_pool
        )

        if chosen_row is None:
            continue

        reserve_links(chosen_row, reserved_links)

        host1 = str(chosen_row["host1"])
        host2 = str(chosen_row["host2"])
        option_number = int(chosen_row["option_number"])

        candidate = {
            "host1": host1,
            "host2": host2,
            "option_number": option_number
        }

        selected.append(candidate)

        print(
            f"[JAFARIAN] pair={host1}<->{host2} "
            f"chosen_opt={option_number} "
            f"score={chosen_score} "
            f"links={chosen_row['norm_links']}"
        )

    print(f"[JAFARIAN] selected={len(selected)} candidates")
    return selected


def apply_candidates_with_endpoint(candidates, update_route_history=True):
    if not candidates:
        print("[JAFARIAN] No candidates to apply.")
        return None

    if route_shuffle_endpoint is None:
        print("[JAFARIAN] route_shuffle_endpoint unavailable. Cannot apply routes.")
        return None

    host_pairs = []
    opt_list = []

    route_manager = None

    if update_route_history and RouteHistoryManager is not None:
        try:
            route_manager = RouteHistoryManager(all_hosts, queue_size=10)
            route_manager.load_from_csv()
            print("[JAFARIAN] RouteHistoryManager loaded.")
        except Exception as e:
            print(f"[JAFARIAN] Could not initialize/load route manager: {e}")
            route_manager = None

    for c in candidates:
        h1 = str(c["host1"])
        h2 = str(c["host2"])
        opt = str(c["option_number"])

        host_pairs.append(f"{h1},{h2}")
        opt_list.append(opt)

        if route_manager is not None:
            print(f"[JAFARIAN] Updating history: {h1}-{h2} -> opt {opt}")
            route_manager.update_pair(h1, h2, opt)

    hosts_arg = ";".join(host_pairs)
    opt_arg = ";".join(opt_list)

    if route_manager is not None:
        try:
            route_manager.save_to_csv()
            print("[JAFARIAN] route_history.csv saved before route endpoint.")
        except Exception as e:
            print(f"[JAFARIAN] Failed to save route_history.csv: {e}")

    print("[JAFARIAN] Calling route endpoint:")
    print(f'  hosts="{hosts_arg}"')
    print(f'  opt="{opt_arg}"')

    result = route_shuffle_endpoint(
        specific_multiple=True,
        hosts=hosts_arg,
        opt=opt_arg
    )

    print("[JAFARIAN] Route endpoint finished.")

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
    parser.add_argument("--protected-dst", default="h40")

    parser.add_argument("--pair-count", type=int, default=10)
    parser.add_argument("--max-hops", type=int, default=6)
    parser.add_argument("--load-threshold-mbps", type=float, default=None)
    parser.add_argument("--top-k-random-pool", type=int, default=3)
    parser.add_argument("--seed", type=int, default=None)

    parser.add_argument("--onos-url", default="http://localhost:8181")
    parser.add_argument("--onos-user", default="onos")
    parser.add_argument("--onos-pass", default="rocks")
    parser.add_argument("--min-packets", type=int, default=1)

    parser.add_argument(
        "--use-increasing-bytes",
        action="store_true",
        help="Use two ONOS samples and count only pairs whose byte counter increases."
    )
    parser.add_argument("--sample-gap", type=int, default=2)

    parser.add_argument(
        "--no-fallback-h40",
        action="store_true",
        help="Do not fall back to h40 pairs if no active ONOS pairs are found."
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print selected candidates. Do not call route endpoint."
    )

    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval", type=int, default=20)

    args = parser.parse_args()

    while True:
        candidates = select_jafarian_candidates(
            hoplist_csv=args.hoplist,
            route_history_csv=args.route_history,
            link_stats_csv=args.link_stats,
            protected_dst=args.protected_dst,
            pair_count_per_cycle=args.pair_count,
            max_hops=args.max_hops,
            load_threshold_mbps=args.load_threshold_mbps,
            top_k_random_pool=args.top_k_random_pool,
            seed=args.seed,
            onos_url=args.onos_url,
            onos_user=args.onos_user,
            onos_pass=args.onos_pass,
            min_packets=args.min_packets,
            use_increasing_bytes=args.use_increasing_bytes,
            sample_gap=args.sample_gap,
            fallback_to_h40=not args.no_fallback_h40
        )

        print("[JAFARIAN] Candidates:", candidates)

        if not args.dry_run:
            apply_candidates_with_endpoint(candidates)

        if not args.loop:
            break

        time.sleep(args.interval)


if __name__ == "__main__":
    main()