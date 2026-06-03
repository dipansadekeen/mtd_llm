# import pulp
# import requests
# import pandas as pd
# from requests.auth import HTTPBasicAuth
# def path_selector(final_obj, hoplist_csv, max_blocked_use=2,
#                   link_stats_csv="link_stats_onos.csv",
#                   threshold_mbps=9.0, link_capacity_mbps=10.0,
#                   onos_url="http://localhost:8181",
#                   onos_user="onos", onos_pass="rocks",
#                   min_packets=1):
#     """
#     Congestion-aware minimum-disruption path selector.
 
#     Replaces the previous greedy blocked-link selector with a global ILP that
#     minimises the number of pairs rerouted (= writes to path_match_log.txt)
#     while guaranteeing every congested link drops below threshold_mbps.
 
#     All flows default to option-0 (shortest path) via ONOS reactive forwarding
#     expiry, so current-state tracking is unnecessary.
 
#     Parameters keep backward compatibility; new ones have safe defaults.
#     """
#     print("\n[path_selector] Congestion-aware minimum-disruption ILP")
 
#     # ------------------------------------------------------------------ #
#     # helpers                                                              #
#     # ------------------------------------------------------------------ #
#     def _dpid_sw(device_id):
#         dev = str(device_id).strip()
#         if dev.startswith("of:"):
#             try:
#                 return f"s{int(dev.replace('of:',''), 16)}"
#             except Exception:
#                 return dev
#         return dev
 
#     def _norm(link_str):
#         """ONOS link string → sorted switch-level tuple, strip port."""
#         s = str(link_str).strip()
#         if "->" not in s:
#             return None
#         left, right = [x.strip() for x in s.split("->", 1)]
#         def _ep(e):
#             parts = e.strip().split(":")
#             return _dpid_sw(f"{parts[0]}:{parts[1]}") if len(parts) >= 3 else e.strip()
#         return tuple(sorted([_ep(left), _ep(right)]))
 
#     def _path_links(path_str):
#         links = []
#         for item in str(path_str).split(","):
#             item = item.strip()
#             if item and "->" in item:
#                 lk = _norm(item)
#                 if lk:
#                     links.append(lk)
#         return links
 
#     # ------------------------------------------------------------------ #
#     # Step 1 – normalise congested links from final_obj                   #
#     # ------------------------------------------------------------------ #
#     raw_links = final_obj.get("final_links", [])
#     if not raw_links:
#         print("[path_selector] No final_links — nothing to do.")
#         return []
 
#     congested = set()
#     for lk in raw_links:
#         n = _norm(str(lk).strip())
#         if n:
#             congested.add(n)
#     print(f"[path_selector] Congested links: {congested}")
 
#     # ------------------------------------------------------------------ #
#     # Step 2 – current link loads from link_stats_onos.csv                #
#     # ------------------------------------------------------------------ #
#     link_loads = {}
#     try:
#         ls = pd.read_csv(link_stats_csv)
#         if "timestamp" in ls.columns:
#             ls["timestamp"] = pd.to_datetime(ls["timestamp"], errors="coerce")
#             ls = ls.dropna(subset=["timestamp"])
#             ls = ls.sort_values("timestamp").groupby("link_id").tail(1)
#         for _, row in ls.iterrows():
#             lk = _norm(str(row["link_id"]))
#             if lk:
#                 link_loads[lk] = max(float(row.get("rx_mbps", 0) or 0),
#                                      float(row.get("tx_mbps", 0) or 0))
#     except Exception as e:
#         print(f"[path_selector] Cannot read {link_stats_csv}: {e}")
 
#     for l in congested:
#         print(f"[path_selector]   {l}: {link_loads.get(l, 0):.3f} Mbps "
#               f"({'CONGESTED' if link_loads.get(l,0) > threshold_mbps else 'ok'})")
 
#     # ------------------------------------------------------------------ #
#     # Step 3 – active ONOS pairs                                          #
#     # ------------------------------------------------------------------ #
#     def _mac_host(mac):
#         try:
#             return f"h{int(str(mac).strip().split(':')[-1], 16)}"
#         except Exception:
#             return None
 
#     active_pairs = []
#     try:
#         r = requests.get(f"{onos_url}/onos/v1/flows",
#                          auth=HTTPBasicAuth(onos_user, onos_pass), timeout=5)
#         r.raise_for_status()
#         seen = set()
#         for flow in r.json().get("flows", []):
#             if flow.get("state") != "ADDED":
#                 continue
#             if int(flow.get("packets", 0) or 0) < min_packets:
#                 continue
#             src = dst = None
#             for c in flow.get("selector", {}).get("criteria", []):
#                 if c.get("type") == "ETH_SRC":
#                     src = c.get("mac")
#                 elif c.get("type") == "ETH_DST":
#                     dst = c.get("mac")
#             if not src or not dst:
#                 continue
#             h1, h2 = _mac_host(src), _mac_host(dst)
#             if h1 and h2 and h1 != h2:
#                 pk = tuple(sorted([h1, h2]))
#                 if pk not in seen:
#                     seen.add(pk)
#                     active_pairs.append(pk)
#     except Exception as e:
#         print(f"[path_selector] Cannot fetch ONOS flows: {e}")
 
#     print(f"[path_selector] Active ONOS pairs: {len(active_pairs)}")
#     if not active_pairs:
#         return []
 
#     # ------------------------------------------------------------------ #
#     # Step 4 – load hop_list, find affected pairs (opt-0 on congested)    #
#     # ------------------------------------------------------------------ #
#     df = pd.read_csv(hoplist_csv, header=None,
#                      names=["host1","host2","option_number","hop_count",
#                              "src_mac","dst_mac","path"])
#     df["option_number"] = df["option_number"].astype(int)
#     df["pair_key"] = df.apply(
#         lambda r: tuple(sorted([str(r["host1"]), str(r["host2"])])), axis=1)
#     df["norm_links"] = df["path"].apply(_path_links)
 
#     valid_pks = set(df["pair_key"])
#     opt0_links = {}   # pk -> norm_links for option 0
#     affected = []
 
#     for pk in active_pairs:
#         if pk not in valid_pks:
#             continue
#         rows0 = df[(df["pair_key"] == pk) & (df["option_number"] == 0)]
#         if rows0.empty:
#             continue
#         lks = rows0.iloc[0]["norm_links"]
#         opt0_links[pk] = lks
#         if any(l in congested for l in lks):
#             affected.append(pk)
 
#     print(f"[path_selector] Affected pairs (traversing congested links): {len(affected)}")
#     if not affected:
#         return []
 
#     # ------------------------------------------------------------------ #
#     # Step 5 – equal-share demand (active pairs only)                     #
#     # ------------------------------------------------------------------ #
#     pair_demand = {}
#     for l in congested:
#         on_l = [pk for pk in affected if l in opt0_links.get(pk, [])]
#         if not on_l:
#             continue
#         share = link_loads.get(l, 0) / len(on_l)
#         for pk in on_l:
#             pair_demand[pk] = max(pair_demand.get(pk, 0), share)
 
#     for pk in affected:
#         print(f"[path_selector]   {pk[0]}<->{pk[1]} "
#               f"demand≈{pair_demand.get(pk,0):.3f} Mbps")
 
#     # ------------------------------------------------------------------ #
#     # Step 6 – build viable alternate options per pair (opt > 0)          #
#     # LFADefender condition 7: residual capacity check on alternates      #
#     # ------------------------------------------------------------------ #
#     pair_options = {}   # pk -> [(opt_num, norm_links), ...]
#     for pk in affected:
#         demand = pair_demand.get(pk, 0)
#         alts = df[(df["pair_key"] == pk) & (df["option_number"] > 0)]
#         viable = []
#         for _, row in alts.iterrows():
#             opt_num = int(row["option_number"])
#             opt_lks = row["norm_links"]
#             # condition 7: no alternate link overflows capacity
#             if all(link_loads.get(l, 0) + demand <= link_capacity_mbps
#                    for l in opt_lks):
#                 viable.append((opt_num, opt_lks))
#         # sort: fewest congested links used first, then by hop count
#         viable.sort(key=lambda x: (
#             sum(1 for l in x[1] if l in congested),
#             len(x[1]), x[0]
#         ))
#         pair_options[pk] = viable
#         n_safe = sum(1 for _, ol in viable
#                      if not any(l in congested for l in ol))
#         print(f"[path_selector]   {pk[0]}<->{pk[1]}: "
#               f"{len(viable)} viable opts ({n_safe} fully safe)")
 
#     # ------------------------------------------------------------------ #
#     # Step 7 – ILP: minimize pairs rerouted                               #
#     # ------------------------------------------------------------------ #
#     def _solve(affected, pair_demand, pair_options, congested,
#                link_loads, threshold, capacity):
#         import pulp
#         prob = pulp.LpProblem("MDR", pulp.LpMinimize)
#         x = {}; y = {}
#         for pk in affected:
#             y[pk] = pulp.LpVariable(f"y_{'_'.join(pk)}", cat="Binary")
#             x[pk] = {o: pulp.LpVariable(f"x_{'_'.join(pk)}_{o}", cat="Binary")
#                      for o, _ in pair_options.get(pk, [])}
 
#         prob += pulp.lpSum(y[pk] for pk in affected)
 
#         for pk in affected:
#             if x[pk]:
#                 prob += pulp.lpSum(x[pk].values()) <= 1
#                 prob += y[pk] == pulp.lpSum(x[pk].values())
#             else:
#                 prob += y[pk] == 0
 
#         # (c) congested links must clear — threshold
#         for l in congested:
#             cur = link_loads.get(l, 0)
#             removed = pulp.lpSum(
#                 pair_demand.get(pk, 0) * y[pk]
#                 for pk in affected if l in opt0_links.get(pk, []))
#             added = pulp.lpSum(
#                 pair_demand.get(pk, 0) * x[pk][o]
#                 for pk in affected
#                 for o, ol in pair_options.get(pk, [])
#                 if l in ol and o in x[pk])
#             prob += (cur - removed + added) <= threshold
 
#         # (d) alternate links must not exceed physical capacity
#         # NOTE: threshold (9 Mbps) is detector sensitivity, NOT physical limit.
#         # Using threshold here makes ILP infeasible when pairs share alternates.
#         alt_links = set(
#             l for pk in affected
#             for _, ol in pair_options.get(pk, []) for l in ol
#             if l not in congested)
#         for l in alt_links:
#             cur = link_loads.get(l, 0)
#             added = pulp.lpSum(
#                 pair_demand.get(pk, 0) * x[pk][o]
#                 for pk in affected
#                 for o, ol in pair_options.get(pk, [])
#                 if l in ol and o in x[pk])
#             prob += (cur + added) <= capacity
 
#         status = prob.solve(pulp.PULP_CBC_CMD(msg=False))
#         if pulp.LpStatus[status] != "Optimal":
#             return None
 
#         out = []
#         for pk in affected:
#             if pulp.value(y[pk]) and pulp.value(y[pk]) > 0.5:
#                 for o, ol in pair_options.get(pk, []):
#                     if o in x[pk] and pulp.value(x[pk][o]) \
#                             and pulp.value(x[pk][o]) > 0.5:
#                         out.append({"host1": pk[0], "host2": pk[1],
#                                     "option_number": o})
#                         print(f"[path_selector] ILP: {pk[0]}<->{pk[1]} "
#                               f"opt={o} demand={pair_demand.get(pk,0):.3f} Mbps")
#                         break
#         return out
 
#     print(f"[path_selector] Solving ILP: {len(affected)} pairs, "
#           f"{len(congested)} congested links, threshold={threshold_mbps} Mbps")
 
#     results = _solve(affected, pair_demand, pair_options, congested,
#                      link_loads, threshold_mbps, link_capacity_mbps)
 
#     # ------------------------------------------------------------------ #
#     # Step 8 – fallback: relax then greedy                                #
#     # ------------------------------------------------------------------ #
#     if results is None:
#         print("[path_selector] ILP infeasible — relaxing capacity constraint.")
#         results = _solve(affected, pair_demand, pair_options, congested,
#                          link_loads, threshold_mbps, link_capacity_mbps * 2)
 
#     if results is None:
#         print("[path_selector] Still infeasible — greedy fallback.")
#         sim = dict(link_loads)
#         results = []
#         for pk in sorted(affected,
#                          key=lambda pk: pair_demand.get(pk, 0), reverse=True):
#             if all(sim.get(l, 0) <= threshold_mbps for l in congested):
#                 break
#             demand = pair_demand.get(pk, 0)
#             chosen = None
#             # prefer options avoiding all congested links
#             for o, ol in pair_options.get(pk, []):
#                 if any(l in congested for l in ol):
#                     continue
#                 if all(sim.get(l, 0) + demand <= link_capacity_mbps for l in ol):
#                     chosen = (o, ol); break
#             # fallback: any viable option
#             if chosen is None:
#                 for o, ol in pair_options.get(pk, []):
#                     if all(sim.get(l, 0) + demand <= link_capacity_mbps for l in ol):
#                         chosen = (o, ol); break
#             if chosen is None:
#                 continue
#             o, ol = chosen
#             for l in congested:
#                 if l in opt0_links.get(pk, []):
#                     sim[l] = max(0.0, sim[l] - demand)
#             for l in ol:
#                 sim[l] = sim.get(l, 0) + demand
#             results.append({"host1": pk[0], "host2": pk[1], "option_number": o})
#             print(f"[path_selector] Greedy: {pk[0]}<->{pk[1]} opt={o}")
 
#     print(f"[path_selector] Done: {len(results)} pairs rerouted "
#           f"(of {len(affected)} affected).")
#     return results
# # update 3.1 (replaced with congestion-aware ILP)


# new_codes
import pulp

from datetime import datetime
import pandas as pd
import numpy as np
from datetime import timedelta
import requests
from langchain_ollama import ChatOllama
import json
import time
import os
from requests.auth import HTTPBasicAuth

def path_selector(final_obj, hoplist_csv, max_blocked_use=2,
                  link_stats_csv="link_stats_onos.csv",
                  threshold_mbps=9.0, link_capacity_mbps=100.0,
                  onos_url="http://localhost:8181",
                  onos_user="onos", onos_pass="rocks",
                  min_packets=1):
    """
    Congestion-aware minimum-disruption path selector.
 
    Replaces the previous greedy blocked-link selector with a global ILP that
    minimises the number of pairs rerouted (= writes to path_match_log.txt)
    while guaranteeing every congested link drops below threshold_mbps.
 
    All flows default to option-0 (shortest path) via ONOS reactive forwarding
    expiry, so current-state tracking is unnecessary.
 
    Parameters keep backward compatibility; new ones have safe defaults.
    """
    # print("\n[path_selector] Congestion-aware minimum-disruption RM") #commented for report
 
    # ------------------------------------------------------------------ #
    # helpers                                                              #
    # ------------------------------------------------------------------ #
    def _dpid_sw(device_id):
        dev = str(device_id).strip()
        if dev.startswith("of:"):
            try:
                return f"s{int(dev.replace('of:',''), 16)}"
            except Exception:
                return dev
        return dev
 
    def _norm(link_str):
        """ONOS link string → sorted switch-level tuple, strip port."""
        s = str(link_str).strip()
        if "->" not in s:
            return None
        left, right = [x.strip() for x in s.split("->", 1)]
        def _ep(e):
            parts = e.strip().split(":")
            return _dpid_sw(f"{parts[0]}:{parts[1]}") if len(parts) >= 3 else e.strip()
        return tuple(sorted([_ep(left), _ep(right)]))
 
    def _path_links(path_str):
        links = []
        for item in str(path_str).split(","):
            item = item.strip()
            if item and "->" in item:
                lk = _norm(item)
                if lk:
                    links.append(lk)
        return links
 
    # ------------------------------------------------------------------ #
    # Step 1 – normalise congested links from final_obj                   #
    # ------------------------------------------------------------------ #
    raw_links = final_obj.get("final_links", [])
    if not raw_links:
        # print("[path_selector] No final_links")
        return []
 
    congested = set()
    for lk in raw_links:
        n = _norm(str(lk).strip())
        if n:
            congested.add(n)
    print(f"[path_selector] Congested links: {congested}")
 
    # ------------------------------------------------------------------ #
    # Step 2 – current link loads from link_stats_onos.csv                #
    # ------------------------------------------------------------------ #
    link_loads = {}
    try:
        ls = pd.read_csv(link_stats_csv)
        if "timestamp" in ls.columns:
            ls["timestamp"] = pd.to_datetime(ls["timestamp"], errors="coerce")
            ls = ls.dropna(subset=["timestamp"])
            ls = ls.sort_values("timestamp").groupby("link_id").tail(1)
        for _, row in ls.iterrows():
            lk = _norm(str(row["link_id"]))
            if lk:
                link_loads[lk] = max(float(row.get("rx_mbps", 0) or 0),
                                     float(row.get("tx_mbps", 0) or 0))
    except Exception as e:
        print(f"[path_selector] Cannot read {link_stats_csv}: {e}")
 
    for l in congested:
        print(f"[path_selector]   {l}: {link_loads.get(l, 0):.3f} Mbps "
              f"({'CONGESTED' if link_loads.get(l,0) > threshold_mbps else 'ok'})")
 
    # ------------------------------------------------------------------ #
    # Step 3 – active ONOS pairs                                          #
    # ------------------------------------------------------------------ #
    def _mac_host(mac):
        try:
            return f"h{int(str(mac).strip().split(':')[-1], 16)}"
        except Exception:
            return None
 
    active_pairs = []
    try:
        r = requests.get(f"{onos_url}/onos/v1/flows",
                         auth=HTTPBasicAuth(onos_user, onos_pass), timeout=5)
        r.raise_for_status()
        seen = set()
        for flow in r.json().get("flows", []):
            if flow.get("state") != "ADDED":
                continue
            if int(flow.get("packets", 0) or 0) < min_packets:
                continue
            src = dst = None
            for c in flow.get("selector", {}).get("criteria", []):
                if c.get("type") == "ETH_SRC":
                    src = c.get("mac")
                elif c.get("type") == "ETH_DST":
                    dst = c.get("mac")
            if not src or not dst:
                continue
            h1, h2 = _mac_host(src), _mac_host(dst)
            if h1 and h2 and h1 != h2:
                pk = tuple(sorted([h1, h2]))
                if pk not in seen:
                    seen.add(pk)
                    active_pairs.append(pk)
    except Exception as e:
        print(f"[path_selector] Cannot fetch controller flows: {e}")
 
    print(f"[path_selector] Active flow pairs: {len(active_pairs)}")
    if not active_pairs:
        return []
 
    # ------------------------------------------------------------------ #
    # Step 4 – load hop_list, find affected pairs (opt-0 on congested)    #
    # ------------------------------------------------------------------ #
    df = pd.read_csv(hoplist_csv, header=None,
                     names=["host1","host2","option_number","hop_count",
                             "src_mac","dst_mac","path"])
    df["option_number"] = df["option_number"].astype(int)
    df["pair_key"] = df.apply(
        lambda r: tuple(sorted([str(r["host1"]), str(r["host2"])])), axis=1)
    df["norm_links"] = df["path"].apply(_path_links)
 
    valid_pks = set(df["pair_key"])
    opt0_links = {}   # pk -> norm_links for option 0
    affected = []
 
    for pk in active_pairs:
        if pk not in valid_pks:
            continue
        rows0 = df[(df["pair_key"] == pk) & (df["option_number"] == 0)]
        if rows0.empty:
            continue
        lks = rows0.iloc[0]["norm_links"]
        opt0_links[pk] = lks
        if any(l in congested for l in lks):
            affected.append(pk)
 
    print(f"[path_selector] Affected pairs: {len(affected)}")
    if not affected:
        return []
 
    # ------------------------------------------------------------------ #
    # Step 5 – equal-share demand (active pairs only)                     #
    # ------------------------------------------------------------------ #
    pair_demand = {}
    for l in congested:
        on_l = [pk for pk in affected if l in opt0_links.get(pk, [])]
        if not on_l:
            continue
        share = link_loads.get(l, 0) / len(on_l)
        for pk in on_l:
            pair_demand[pk] = max(pair_demand.get(pk, 0), share)
 
    for pk in affected:
        print(f"[path_selector]   {pk[0]}<->{pk[1]} "
              f"demand≈{pair_demand.get(pk,0):.3f} Mbps")
 
    # ------------------------------------------------------------------ #
    # Step 6 – build viable alternate options per pair (opt > 0)          #
    # LFADefender condition 7: residual capacity check on alternates      #
    # ------------------------------------------------------------------ #
    pair_options = {}   # pk -> [(opt_num, norm_links), ...]
    for pk in affected:
        demand = pair_demand.get(pk, 0)
        alts = df[(df["pair_key"] == pk) & (df["option_number"] > 0)]
        viable = []
        for _, row in alts.iterrows():
            opt_num = int(row["option_number"])
            opt_lks = row["norm_links"]
            # condition 7: no alternate link overflows capacity
            if all(link_loads.get(l, 0) + demand <= link_capacity_mbps
                   for l in opt_lks):
                viable.append((opt_num, opt_lks))
        # sort: fewest congested links used first, then by hop count
        viable.sort(key=lambda x: (
            sum(1 for l in x[1] if l in congested),
            len(x[1]), x[0]
        ))
        pair_options[pk] = viable
        n_safe = sum(1 for _, ol in viable
                     if not any(l in congested for l in ol))
        print(f"[path_selector]   {pk[0]}<->{pk[1]}: "f"{len(viable)} viable opts ({n_safe} fully safe)") 
 
    # ------------------------------------------------------------------ #
    # Step 7 – ILP: minimize pairs rerouted                               #
    # ------------------------------------------------------------------ #
    def _solve(affected, pair_demand, pair_options, congested,
               link_loads, threshold, capacity):
        import pulp
        prob = pulp.LpProblem("MDR", pulp.LpMinimize)
        x = {}; y = {}
        for pk in affected:
            y[pk] = pulp.LpVariable(f"y_{'_'.join(pk)}", cat="Binary")
            x[pk] = {o: pulp.LpVariable(f"x_{'_'.join(pk)}_{o}", cat="Binary")
                     for o, _ in pair_options.get(pk, [])}
 
        prob += pulp.lpSum(y[pk] for pk in affected)
 
        for pk in affected:
            if x[pk]:
                prob += pulp.lpSum(x[pk].values()) <= 1
                prob += y[pk] == pulp.lpSum(x[pk].values())
            else:
                prob += y[pk] == 0
 
        # (c) congested links must clear — threshold
        for l in congested:
            cur = link_loads.get(l, 0)
            removed = pulp.lpSum(
                pair_demand.get(pk, 0) * y[pk]
                for pk in affected if l in opt0_links.get(pk, []))
            added = pulp.lpSum(
                pair_demand.get(pk, 0) * x[pk][o]
                for pk in affected
                for o, ol in pair_options.get(pk, [])
                if l in ol and o in x[pk])
            prob += (cur - removed + added) <= threshold
 
        # (d) alternate links must not exceed physical capacity
        # NOTE: threshold (9 Mbps) is detector sensitivity, NOT physical limit.
        # Using threshold here makes ILP infeasible when pairs share alternates.
        alt_links = set(
            l for pk in affected
            for _, ol in pair_options.get(pk, []) for l in ol
            if l not in congested)
        for l in alt_links:
            cur = link_loads.get(l, 0)
            added = pulp.lpSum(
                pair_demand.get(pk, 0) * x[pk][o]
                for pk in affected
                for o, ol in pair_options.get(pk, [])
                if l in ol and o in x[pk])
            prob += (cur + added) <= capacity
 
        status = prob.solve(pulp.PULP_CBC_CMD(msg=False))
        if pulp.LpStatus[status] != "Optimal":
            return None
 
        out = []
        for pk in affected:
            if pulp.value(y[pk]) and pulp.value(y[pk]) > 0.5:
                for o, ol in pair_options.get(pk, []):
                    if o in x[pk] and pulp.value(x[pk][o]) \
                            and pulp.value(x[pk][o]) > 0.5:
                        out.append({"host1": pk[0], "host2": pk[1],
                                    "option_number": o})
                        print(f"[path_selector] RM: {pk[0]}<->{pk[1]} "
                              f"opt={o} demand={pair_demand.get(pk,0):.3f} Mbps")
                        break
        return out
 
    print(f"[path_selector] Solving: {len(affected)} pairs, "
          f"{len(congested)} congested links, threshold={threshold_mbps} Mbps")
 
    results = _solve(affected, pair_demand, pair_options, congested,
                     link_loads, threshold_mbps, link_capacity_mbps)
 
    # ------------------------------------------------------------------ #
    # Step 8 – fallback: relax then greedy                                #
    # ------------------------------------------------------------------ #
    if results is None:
        print("[path_selector] RM infeasible — relaxing capacity constraint.")
        results = _solve(affected, pair_demand, pair_options, congested,
                         link_loads, threshold_mbps, link_capacity_mbps * 2)
 
    if results is None:
        print("[path_selector] Still infeasible — greedy fallback.")
        sim = dict(link_loads)
        results = []
        for pk in sorted(affected,
                         key=lambda pk: pair_demand.get(pk, 0), reverse=True):
            if all(sim.get(l, 0) <= threshold_mbps for l in congested):
                break
            demand = pair_demand.get(pk, 0)
            chosen = None
            # prefer options avoiding all congested links
            for o, ol in pair_options.get(pk, []):
                if any(l in congested for l in ol):
                    continue
                if all(sim.get(l, 0) + demand <= link_capacity_mbps for l in ol):
                    chosen = (o, ol); break
            # fallback: any viable option
            if chosen is None:
                for o, ol in pair_options.get(pk, []):
                    if all(sim.get(l, 0) + demand <= link_capacity_mbps for l in ol):
                        chosen = (o, ol); break
            if chosen is None:
                continue
            o, ol = chosen
            for l in congested:
                if l in opt0_links.get(pk, []):
                    sim[l] = max(0.0, sim[l] - demand)
            for l in ol:
                sim[l] = sim.get(l, 0) + demand
            results.append({"host1": pk[0], "host2": pk[1], "option_number": o})
            print(f"[path_selector] Greedy: {pk[0]}<->{pk[1]} opt={o}")
 
    print(f"[path_selector] Done: {len(results)} pairs rerouted "
          f"(of {len(affected)} affected).")
    return results
# update 3.1 (replaced with congestion-aware ILP)