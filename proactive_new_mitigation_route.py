# # # proactive_new_mitigation_route.py

# # import csv, pulp
# # from collections import defaultdict
# # import time


# # from route_mutate_endpoint import route_shuffle_endpoint, route_shuffle_endpoint_merge_log
# # from mtd_utils import RouteHistoryManager, all_hosts, ROUTE_HISTORY_SIZE

# # HOP_LIST_FILE = "hop_list.csv"
# # LINK_STATS_FILE = "link_stats_onos.csv"

# # CAPACITY_MBPS = 1.0
# # THETA = 0.8          # safety threshold: 80%
# # DEFAULT_DEMAND = 0.05

# # HOP_WEIGHT = 0.30
# # LOAD_WEIGHT = 1.00
# # OLD_LINK_REUSE_WEIGHT = 2.00
# # OLD_LINK_LOAD_WEIGHT = 1.00
# # OVERLOAD_WEIGHT = 100.0
# # MULTI_FLOW_OVERLAP_WEIGHT = 10.0


# # def pair_key(a, b):
# #     return tuple(sorted((a, b), key=lambda x: int(x[1:])))


# # def latest_recorded_option(xs, default=0):
# #     """
# #     In this design:
# #         latest history value = currently active route option/state
# #         0 = default route / no custom route active for this pair
# #     """
# #     if not xs:
# #         return default

# #     try:
# #         return int(xs[-1])
# #     except Exception:
# #         return default


# # # def load_link_loads():
# # #     rows = []
# # #     with open(LINK_STATS_FILE, newline="") as f:
# # #         for r in csv.DictReader(f):
# # #             # rows.append((r["timestamp"], r["link_id"].strip(), float(r["tx_mbps"])))
# # #             rows.append((r["timestamp"], r["link_id"].strip(), max(rx, tx)))
# # #     if not rows:
# # #         return {}
# # #     latest = max(r[0] for r in rows)
# # #     return {lid: mbps for ts, lid, mbps in rows if ts == latest}

# # def load_link_loads():
# #     rows = []

# #     with open(LINK_STATS_FILE, newline="") as f:
# #         for r in csv.DictReader(f):
# #             rx = float(r.get("rx_mbps", 0.0) or 0.0)
# #             tx = float(r.get("tx_mbps", 0.0) or 0.0)
# #             mbps = max(rx, tx)

# #             # rows.append((r["timestamp"], r["link_id"].strip(), mbps))
# #             norm_link = normalize_link_id(r["link_id"].strip())
# #             rows.append((r["timestamp"], norm_link, mbps))

# #     if not rows:
# #         return {}

# #     latest = max(r[0] for r in rows)

# #     return {
# #         lid: mbps
# #         for ts, lid, mbps in rows
# #         if ts == latest
# #     }

# # def dpid_to_switch(device_id):
# #     dev = str(device_id).strip()

# #     if dev.startswith("of:"):
# #         body = dev.replace("of:", "")
# #         body = body.split("/")[0]
# #         body = body.split(":")[0]
# #         return f"s{int(body, 16)}"

# #     # If already like s1/1 or s1:1, keep only switch name
# #     dev = dev.split("/")[0]
# #     dev = dev.split(":")[0]

# #     return dev


# # def normalize_link_id(link_str):
# #     """
# #     Normalize ONOS link IDs into undirected switch-pair keys.

# #     Example:
# #         of:0000000000000001/1->of:0000000000000002/2
# #         becomes ('s1', 's2')
# #     """
# #     s = str(link_str).strip()

# #     if "->" not in s:
# #         return s

# #     left, right = [x.strip() for x in s.split("->", 1)]

# #     return tuple(sorted([
# #         dpid_to_switch(left),
# #         dpid_to_switch(right),
# #     ]))



# # def load_paths():
# #     """
# #     Returns:
# #       paths[(h1,h30)][option] = {"hops": 3, "links": [...]}
# #     """
# #     paths = defaultdict(dict)

# #     with open(HOP_LIST_FILE, newline="") as f:
# #         for r in csv.reader(f):
# #             if len(r) < 7:
# #                 continue

# #             a, b = r[0].strip(), r[1].strip()
# #             opt = int(r[2])
# #             hops = float(r[3])
# #             path = r[6].strip()

# #             links = []
# #             for part in path.split(","):
# #                 part = part.strip()
# #                 # if "->" in part:
# #                 #     links.append(part)
# #                 if "->" in part:
# #                     links.append(normalize_link_id(part))

# #             paths[pair_key(a, b)][opt] = {
# #                 "hops": hops,
# #                 "links": links,
# #             }

# #     return paths


# # def recent_options(route_manager, a, b):
# #     return set(int(x) for x in route_manager.get_pair_history(a, b) if int(x) != 0)


# # def solve_route_assignment(selected_pairs, route_manager, demand=None, avoid_recent=True):
# #     """
# #     selected_pairs:
# #         [("h1","h30"), ("h1","h35")]

# #     demand:
# #         {("h1","h30"): 0.2, ...} in Mbps
# #     """

# #     current_option_map = {}
# #     current_links_map = {}

# #     demand = demand or {}
# #     paths = load_paths()
# #     link_load = load_link_loads()

# #     selected_pairs = [pair_key(a, b) for a, b in selected_pairs]

# #     if not selected_pairs:
# #         return {}

# #     feasible = {}

# #     for a, b in selected_pairs:
# #         p = pair_key(a, b)
# #         opts = list(paths.get(p, {}).keys())

# #         if not opts:
# #             raise RuntimeError(f"No path options for {p}")

# #         hist = route_manager.get_pair_history(a, b)
# #         # current = last_nonzero(hist)
# #         current = latest_recorded_option(hist, default=0)

# #         current_option_map[p] = current
# #         current_links_map[p] = set(paths[p].get(current, {}).get("links", []))

# #         recent = recent_options(route_manager, a, b)

# #         cand = []
# #         for opt in opts:
# #             if current is not None and opt == current:   # C3
# #                 continue
# #             if avoid_recent and opt in recent:           # C8
# #                 continue
# #             cand.append(opt)

# #         if not cand:
# #             raise RuntimeError(f"No feasible route option for {p}")

# #         feasible[p] = cand

# #     model = pulp.LpProblem("Route_Assignment", pulp.LpMinimize)

# #     y = {
# #         (p, opt): pulp.LpVariable(f"y_{p[0]}_{p[1]}_{opt}", cat="Binary")
# #         for p in selected_pairs
# #         for opt in feasible[p]
# #     }

# #     # overload = {
# #     #     l: pulp.LpVariable(f"overload_{i}", lowBound=0)
# #     #     for i, l in enumerate(link_load.keys())
# #     # }

# #     # overlap = {
# #     #     l: pulp.LpVariable(f"overlap_{i}", lowBound=0)
# #     #     for i, l in enumerate(link_load.keys())
# #     # }

# #     # # C1: each selected route gets exactly one valid option
# #     # for p in selected_pairs:
# #     #     model += pulp.lpSum(y[p, opt] for opt in feasible[p]) == 1

# #     # # Link constraints C4, C5, C6, C7
# #     # all_links = set(link_load.keys())

# #     # for p in selected_pairs:
# #     #     for opt in feasible[p]:
# #     #         all_links.update(paths[p][opt]["links"])

# #     # C1: each selected route gets exactly one valid option
# #     for p in selected_pairs:
# #         model += pulp.lpSum(y[p, opt] for opt in feasible[p]) == 1

# #     # Build all links first
# #     all_links = set(link_load.keys())

# #     for p in selected_pairs:
# #         all_links.update(current_links_map.get(p, set()))

# #         for opt in feasible[p]:
# #             all_links.update(paths[p][opt]["links"])

# #     overload = {
# #         l: pulp.LpVariable(f"overload_{i}", lowBound=0)
# #         for i, l in enumerate(sorted(all_links))
# #     }

# #     overlap = {
# #         l: pulp.LpVariable(f"overlap_{i}", lowBound=0)
# #         for i, l in enumerate(sorted(all_links))
# #     }

# #     # for l in all_links:
# #     #     current_load = link_load.get(l, 0.0)

# #     #     added_load = []
# #     #     used_count = []

# #     #     for p in selected_pairs:
# #     #         d = demand.get(p, DEFAULT_DEMAND)

# #     #         for opt in feasible[p]:
# #     #             if l in paths[p][opt]["links"]:
# #     #                 added_load.append(d * y[p, opt])
# #     #                 used_count.append(y[p, opt])

# #     #     final_load = current_load + pulp.lpSum(added_load)

# #     #     # C4/C5/C6: soft threshold/capacity
# #     #     model += final_load <= THETA * CAPACITY_MBPS + overload.get(
# #     #         l, pulp.LpVariable(f"overload_extra_{len(overload)}", lowBound=0)
# #     #     )

# #     #     # C7: overlap soft constraint
# #     #     if used_count:
# #     #         model += pulp.lpSum(used_count) <= 1 + overlap.get(
# #     #             l, pulp.LpVariable(f"overlap_extra_{len(overlap)}", lowBound=0)
# #     #         )

# #     for l in all_links:
# #         current_load = link_load.get(l, 0.0)

# #         removed_load = []
# #         added_load = []
# #         used_count = []

# #         for p in selected_pairs:
# #             d = demand.get(p, DEFAULT_DEMAND)

# #             # Remove selected flow demand from its current active path
# #             if l in current_links_map.get(p, set()):
# #                 removed_load.append(d)

# #             # Add selected flow demand to its newly assigned path
# #             for opt in feasible[p]:
# #                 if l in paths[p][opt]["links"]:
# #                     added_load.append(d * y[p, opt])
# #                     used_count.append(y[p, opt])

# #         final_load = (
# #             current_load
# #             - pulp.lpSum(removed_load)
# #             + pulp.lpSum(added_load)
# #         )

# #         # Capacity/safety threshold
# #         model += final_load <= THETA * CAPACITY_MBPS + overload[l]

# #         # Softly avoid putting many selected reroutes on the same link
# #         if used_count:
# #             model += pulp.lpSum(used_count) <= 1 + overlap[l]


# #     # Objective: minimize overload + overlap + hop count + current load usage
# #     # obj = []

# #     # for p in selected_pairs:
# #     #     for opt in feasible[p]:
# #     #         info = paths[p][opt]
# #     #         hop_cost = info["hops"]
# #     #         load_cost = sum(link_load.get(l, 0.0) for l in info["links"])

# #     #         obj.append((0.30 * hop_cost + 1.00 * load_cost) * y[p, opt])

# #     # obj += [100.0 * v for v in overload.values()]
# #     # obj += [10.0 * v for v in overlap.values()]

# #     # model += pulp.lpSum(obj)

# #     obj = []

# #     for p in selected_pairs:
# #         old_links = current_links_map.get(p, set())

# #         for opt in feasible[p]:
# #             info = paths[p][opt]

# #             new_links = set(info["links"])
# #             shared_old_links = new_links.intersection(old_links)

# #             hop_cost = info["hops"]

# #             # Prefer currently less-loaded new paths
# #             load_cost = sum(link_load.get(l, 0.0) for l in new_links)

# #             # Prefer new paths that reuse fewer links from the current active path
# #             old_link_reuse_ratio = len(shared_old_links) / max(1, len(old_links))

# #             # Extra penalty if reused old links are already loaded
# #             old_link_reuse_load = sum(link_load.get(l, 0.0) for l in shared_old_links)

# #             path_cost = (
# #                 HOP_WEIGHT * hop_cost
# #                 + LOAD_WEIGHT * load_cost
# #                 + OLD_LINK_REUSE_WEIGHT * old_link_reuse_ratio
# #                 + OLD_LINK_LOAD_WEIGHT * old_link_reuse_load
# #             )

# #             obj.append(path_cost * y[p, opt])

# #     obj += [OVERLOAD_WEIGHT * v for v in overload.values()]
# #     obj += [MULTI_FLOW_OVERLAP_WEIGHT * v for v in overlap.values()]

# #     model += pulp.lpSum(obj)

# #     # model.solve(pulp.PULP_CBC_CMD(msg=False))

# #     # added solver time //////////
# #     t0 = time.perf_counter()
# #     model.solve(pulp.PULP_CBC_CMD(msg=False))
# #     solver_time_s = time.perf_counter() - t0

# #     print(f"[ROUTE ILP SOLVER TIME] {solver_time_s:.6f}s | status={pulp.LpStatus[model.status]}")
# #     # added solver time //////////


# #     if pulp.LpStatus[model.status] != "Optimal":
# #         raise RuntimeError(f"Route ILP failed: {pulp.LpStatus[model.status]}")

# #     assignment = {}

# #     for p in selected_pairs:
# #         for opt in feasible[p]:
# #             if pulp.value(y[p, opt]) > 0.5:
# #                 assignment[p] = opt

# #     return assignment


# # def apply_route_assignment(route_manager, assignment):
# #     """
# #     Calls the existing route mutation endpoint and updates route history.
# #     """

# #     if not assignment:
# #         print("No route assignment.")
# #         return

# #     hosts_arg = []
# #     opts_arg = []
# #     selected_for_history = []

# #     # we got a bug, sometimes h1,h28 -opt 9 is not available but h28,h1 opt-9 exist
# #     # for (a, b), opt in assignment.items():
# #     #     hosts_arg.append(f"{a},{b}")
# #     #     opts_arg.append(str(opt))
# #     #     selected_for_history.append((a, b, opt))


# #     #///////////////////// to handle the  ||bug, sometimes h1,h28 -opt 9 is not available but h28,h1 opt-9 exist
# #     hop_rows = {
# #         (r[0].strip(), r[1].strip(), int(r[2]))
# #         for r in csv.reader(open(HOP_LIST_FILE))
# #         if len(r) >= 3
# #     }

# #     for (a, b), opt in assignment.items():
# #         hist_a, hist_b = a, b   # keep original/normalized pair for history

# #         if (a, b, opt) not in hop_rows and (b, a, opt) in hop_rows:
# #             print(f"[FLIP ROUTE APPLY] ({a},{b},{opt}) missing; using ({b},{a},{opt})")
# #             a, b = b, a

# #         hosts_arg.append(f"{a},{b}")
# #         opts_arg.append(str(opt))

# #         # keep history based on selected pair, not flipped endpoint direction
# #         selected_for_history.append((hist_a, hist_b, opt))
# #     #///////////////////// to handle the  ||bug, sometimes h1,h28 -opt 9 is not available but h28,h1 opt-9 exist

# #     # route_shuffle_endpoint(
# #     #     specific_multiple=True,
# #     #     hosts=";".join(hosts_arg),
# #     #     opt=";".join(opts_arg),
# #     # )

# #     # append logic/////// 
# #     route_shuffle_endpoint_merge_log(
# #         specific_multiple=True,
# #         hosts=";".join(hosts_arg),
# #         opt=";".join(opts_arg),
# #     )
    
# #     # route_manager.update_cycle(selected_for_history) # commented for append logic
# #     # route_manager.save_to_csv() # commented for append logic

# #     for a, b, opt in selected_for_history:
# #         route_manager.update_pair(a, b, opt)

# #     route_manager.save_to_csv()
# #     # ///////new append logic above///////

# #     print("[ROUTE ILP ASSIGNMENT]", assignment)


# # def run_route_ilp(selected_pairs):
# #     route_manager = RouteHistoryManager(all_hosts, queue_size=ROUTE_HISTORY_SIZE)
# #     route_manager.load_from_csv()

# #     try:
# #         assignment = solve_route_assignment(
# #             selected_pairs,
# #             route_manager,
# #             avoid_recent=True,
# #         )
# #     except RuntimeError as e:
# #         print("[WARN]", e)
# #         print("Retrying without recent-route restriction.")
# #         assignment = solve_route_assignment(
# #             selected_pairs,
# #             route_manager,
# #             avoid_recent=False,
# #         )

# #     apply_route_assignment(route_manager, assignment)


# # # if __name__ == "__main__":
# # #     # Example only. Replace with selected route pairs from your decision ILP.
# # #     run_route_ilp([
# # #         ("h1", "h30"),
# # #         ("h1", "h35"),
# # #     ])



# # ////

# # checkpoint
# # proactive_new_mitigation_route.py

# import csv
# import pulp
# from collections import defaultdict
# import time

# from route_mutate_endpoint import route_shuffle_endpoint, route_shuffle_endpoint_merge_log
# from mtd_utils import RouteHistoryManager, all_hosts, ROUTE_HISTORY_SIZE


# # =====================================================
# # CONFIG
# # =====================================================

# HOP_LIST_FILE = "hop_list.csv"
# LINK_STATS_FILE = "link_stats_onos.csv"
# ROUTE_OVERLAP_FILE = "onos_active_flow_route_overlap_v3.csv"

# CAPACITY_MBPS = 1.0
# THETA = 0.8

# # Fallback only.
# # Measured demand from v3 or link-load-share demand should override this.
# DEFAULT_DEMAND = 0.25

# # If a link is already above capacity, do not make it worse.
# # If it is below capacity, do not push it above capacity.
# ENFORCE_NON_WORSENING_CAPACITY = True

# # Pseudo option for "stay" if current observed ONOS route is not a hop_list option.
# STAY_OPTION = -1

# HOP_WEIGHT = 0.30
# LOAD_WEIGHT = 1.00
# OLD_LINK_REUSE_WEIGHT = 2.00
# OLD_LINK_LOAD_WEIGHT = 1.00
# OVERLOAD_WEIGHT = 100.0
# MULTI_FLOW_OVERLAP_WEIGHT = 10.0
# MUTATION_WEIGHT = 0.10

# # In-memory previous route bytes.
# # No extra CSV file is created.
# _PREV_ROUTE_BYTES = {}
# _PREV_ROUTE_TIME = {}
# _LAST_ROUTE_DEMAND = {}


# # =====================================================
# # BASIC HELPERS
# # =====================================================

# def pair_key(a, b):
#     return tuple(sorted((a, b), key=lambda x: int(str(x)[1:])))


# def latest_recorded_option(xs, default=0):
#     """
#     latest history value = currently active route option/state
#     0 = default route / no custom route active for this pair
#     """
#     if not xs:
#         return default

#     try:
#         return int(xs[-1])
#     except Exception:
#         return default


# def dpid_to_switch(device_id):
#     dev = str(device_id).strip()

#     if dev.startswith("of:"):
#         body = dev.replace("of:", "")
#         body = body.split("/")[0]
#         body = body.split(":")[0]
#         return f"s{int(body, 16)}"

#     dev = dev.split("/")[0]
#     dev = dev.split(":")[0]

#     return dev


# def normalize_link_id(link_str):
#     """
#     Normalize ONOS link IDs into undirected switch-pair keys.

#     Example:
#         of:0000000000000001:2 -> of:000000000000000c:1
#     becomes:
#         ('s1', 's12')
#     """
#     s = str(link_str).strip()

#     if "->" not in s:
#         return s

#     left, right = [x.strip() for x in s.split("->", 1)]

#     return tuple(sorted([
#         dpid_to_switch(left),
#         dpid_to_switch(right),
#     ]))


# # =====================================================
# # LOAD CURRENT LINK LOAD
# # =====================================================

# def load_link_loads():
#     """
#     Reads latest link_stats_onos.csv snapshot.

#     Returns:
#         link_load[normalized_link] = max(rx_mbps, tx_mbps)
#     """
#     rows = []

#     try:
#         with open(LINK_STATS_FILE, newline="") as f:
#             for r in csv.DictReader(f):
#                 rx = float(r.get("rx_mbps", 0.0) or 0.0)
#                 tx = float(r.get("tx_mbps", 0.0) or 0.0)
#                 mbps = max(rx, tx)

#                 norm_link = normalize_link_id(r["link_id"].strip())
#                 rows.append((r["timestamp"], norm_link, mbps))
#     except FileNotFoundError:
#         print(f"[WARN] {LINK_STATS_FILE} not found. Link loads default to 0.")
#         return {}
#     except Exception as e:
#         print(f"[WARN] Could not read {LINK_STATS_FILE}: {e}")
#         return {}

#     if not rows:
#         return {}

#     latest = max(r[0] for r in rows)

#     return {
#         lid: mbps
#         for ts, lid, mbps in rows
#         if ts == latest
#     }


# # =====================================================
# # LOAD CANDIDATE PATHS
# # =====================================================

# def load_paths():
#     """
#     Returns:
#         paths[(h1,h30)][option] = {
#             "hops": 3,
#             "links": [("s1","s11"), ...]
#         }
#     """
#     paths = defaultdict(dict)

#     with open(HOP_LIST_FILE, newline="") as f:
#         for r in csv.reader(f):
#             if len(r) < 7:
#                 continue

#             a, b = r[0].strip(), r[1].strip()
#             opt = int(r[2])
#             hops = float(r[3])
#             path = r[6].strip()

#             links = []

#             for part in path.split(","):
#                 part = part.strip()

#                 if "->" in part:
#                     links.append(normalize_link_id(part))

#             paths[pair_key(a, b)][opt] = {
#                 "hops": hops,
#                 "links": links,
#             }

#     return paths


# # =====================================================
# # ROUTE OVERLAP V3 READERS
# # =====================================================

# def parse_time_epoch(ts):
#     """
#     Parse timestamp from v3 file.
#     Example:
#         2026-07-07 20:12:25
#     """
#     try:
#         return time.mktime(time.strptime(str(ts).strip(), "%Y-%m-%d %H:%M:%S"))
#     except Exception:
#         return time.time()


# def host_pair_from_flow_name(flow):
#     """
#     Convert 'h39->h2' into normalized pair key ('h2', 'h39').
#     """
#     flow = str(flow or "").strip()

#     if "->" not in flow:
#         return None

#     a, b = [x.strip() for x in flow.split("->", 1)]

#     if not (a.startswith("h") and b.startswith("h")):
#         return None

#     try:
#         return pair_key(a, b)
#     except Exception:
#         return None


# def parse_route_link_set(row):
#     """
#     Reads active route links from onos_active_flow_route_overlap_v3.csv
#     and normalizes them to the same link keys used by hop_list/link_stats.
#     """
#     text = row.get("active_route_link_ids") or row.get("active_route_links") or ""
#     links = set()

#     for part in str(text).split(";"):
#         part = part.strip()

#         if "->" in part:
#             links.add(normalize_link_id(part))

#     return links


# def load_route_observations_from_v3():
#     """
#     Live-read onos_active_flow_route_overlap_v3.csv.

#     Returns:
#         demands[pair] = measured route demand in Mbps
#         observed_current_links[pair] = active ONOS route links

#     Demand priority:
#         1. If v3 already has route_demand_mbps, use it.
#         2. Else compute from cumulative bytes using in-memory delta:
#               corrected_bytes = bytes / active_route_link_count
#               demand_mbps = delta(corrected_bytes) * 8 / delta_time / 1e6
#         3. If no previous snapshot exists, leave demand missing.
#            Later we estimate it from current link load share.

#     No extra state CSV is created.
#     """
#     global _PREV_ROUTE_BYTES, _PREV_ROUTE_TIME, _LAST_ROUTE_DEMAND

#     demands = {}
#     observed_current_links = {}

#     try:
#         with open(ROUTE_OVERLAP_FILE, newline="") as f:
#             rows = list(csv.DictReader(f))
#     except FileNotFoundError:
#         print(f"[WARN] {ROUTE_OVERLAP_FILE} not found. Using fallback demand.")
#         return demands, observed_current_links
#     except Exception as e:
#         print(f"[WARN] Could not read {ROUTE_OVERLAP_FILE}: {e}")
#         return demands, observed_current_links

#     rows = [r for r in rows if r.get("timestamp")]

#     if not rows:
#         return demands, observed_current_links

#     latest_ts = max(r["timestamp"] for r in rows)
#     latest_epoch = parse_time_epoch(latest_ts)

#     latest_rows = [
#         r for r in rows
#         if r.get("timestamp") == latest_ts
#     ]

#     for r in latest_rows:
#         p = host_pair_from_flow_name(r.get("flow"))

#         if p is None:
#             continue

#         links = parse_route_link_set(r)

#         if links:
#             observed_current_links[p] = links

#         measured = None

#         # Trust demand if collector already writes it.
#         for col in ("route_demand_mbps", "demand_mbps"):
#             val = str(r.get(col, "")).strip()

#             if val:
#                 try:
#                     measured = float(val)
#                 except ValueError:
#                     measured = None
#                 break

#         if measured is None:
#             try:
#                 raw_bytes = float(r.get("bytes", 0.0) or 0.0)
#             except ValueError:
#                 raw_bytes = 0.0

#             try:
#                 link_count = int(float(r.get("active_route_link_count", 0) or 0))
#             except ValueError:
#                 link_count = 0

#             if link_count <= 0:
#                 link_count = max(1, len(links))

#             # IMPORTANT:
#             # v3 route bytes may be summed across route switch rules.
#             # Divide by active_route_link_count only to estimate one-copy
#             # end-to-end bytes.
#             # corrected_bytes = raw_bytes / max(1, link_count)
#             corrected_bytes = raw_bytes 

#             prev_b = _PREV_ROUTE_BYTES.get(p)
#             prev_t = _PREV_ROUTE_TIME.get(p)

#             if prev_b is not None and prev_t is not None:
#                 dt = latest_epoch - prev_t

#                 if dt > 0:
#                     delta_bytes = max(0.0, corrected_bytes - prev_b)
#                     measured = (delta_bytes * 8.0) / (dt * 1_000_000.0)

#             _PREV_ROUTE_BYTES[p] = corrected_bytes
#             _PREV_ROUTE_TIME[p] = latest_epoch

#         if measured is None:
#             measured = _LAST_ROUTE_DEMAND.get(p)

#         if measured is not None and measured > 0:
#             demands[p] = max(demands.get(p, 0.0), measured)
#             _LAST_ROUTE_DEMAND[p] = demands[p]

#     if demands:
#         pretty = ", ".join(
#             f"{p[0]}-{p[1]}={d:.4f}Mbps"
#             for p, d in sorted(demands.items())
#         )
#         print(f"[ROUTE DEMANDS FROM V3 BYTES] {pretty}")
#     else:
#         print("[WARN] No positive byte-delta route demand measured from v3 yet.")

#     return demands, observed_current_links


# def estimate_missing_demands_from_link_load(
#     selected_pairs,
#     demands,
#     observed_current_links,
#     link_load,
#     route_manager,
# ):
#     """
#     Optimistic live fallback.

#     For selected routes missing byte-derived demand, estimate demand as
#     the route's share of current load on its active links:

#         share_on_link = current_link_load / number_of_active_routes_using_link

#     Then use max share across the old path.

#     This does NOT multiply demand by number of links.
#     It estimates one route demand, then that same demand is applied to
#     every link the route uses inside the ILP.
#     """
#     paths = load_paths()
#     estimated = dict(demands)

#     # Build link -> active route users from v3 observed current links.
#     link_users = defaultdict(set)

#     for p, links in observed_current_links.items():
#         for l in links:
#             link_users[l].add(p)

#     selected_norm = [pair_key(a, b) for a, b in selected_pairs]

#     for p in selected_norm:
#         if estimated.get(p, 0.0) > 0:
#             continue

#         links = set(observed_current_links.get(p, set()))

#         # If v3 does not contain this selected pair, use route history + hop_list.
#         if not links:
#             hist = route_manager.get_pair_history(p[0], p[1])
#             current = latest_recorded_option(hist, default=0)
#             links = set(paths.get(p, {}).get(current, {}).get("links", []))

#         if not links:
#             continue

#         shares = []

#         for l in links:
#             cur_load = link_load.get(l, 0.0)

#             users = len(link_users.get(l, set()))

#             # If selected route was not observed in v3 for this link,
#             # count it as one additional user.
#             if p not in link_users.get(l, set()):
#                 users += 1

#             users = max(1, users)

#             shares.append(cur_load / users)

#         if not shares:
#             continue

#         # Use bottleneck share as safer demand estimate.
#         estimated[p] = max(shares)

#     return estimated


# # =====================================================
# # ROUTE ILP
# # =====================================================

# def recent_options(route_manager, a, b):
#     return set(int(x) for x in route_manager.get_pair_history(a, b) if int(x) != 0)


# def solve_route_assignment(
#     selected_pairs,
#     route_manager,
#     demand=None,
#     observed_current_links=None,
#     avoid_recent=True,
# ):
#     """
#     selected_pairs:
#         [("h39","h2"), ("h15","h33")]

#     demand:
#         {("h2","h39"): 0.5, ...} in Mbps

#     observed_current_links:
#         current active route links from onos_active_flow_route_overlap_v3.csv
#     """

#     current_option_map = {}
#     current_links_map = {}

#     demand = demand or {}
#     observed_current_links = observed_current_links or {}

#     paths = load_paths()
#     link_load = load_link_loads()

#     selected_pairs = [pair_key(a, b) for a, b in selected_pairs]

#     if not selected_pairs:
#         return {}

#     feasible = {}

#     for a, b in selected_pairs:
#         p = pair_key(a, b)
#         opts = list(paths.get(p, {}).keys())

#         if not opts:
#             raise RuntimeError(f"No path options for {p}")

#         hist = route_manager.get_pair_history(a, b)
#         current = latest_recorded_option(hist, default=0)

#         # Prefer current active links from ONOS v3 if available.
#         current_links = set(paths[p].get(current, {}).get("links", []))

#         if observed_current_links.get(p):
#             current_links = set(observed_current_links[p])

#         # Allow stay decision.
#         # If current option exists in hop_list, use it.
#         # Otherwise create pseudo STAY_OPTION using observed ONOS links.
#         current_choice = current if current in paths[p] else STAY_OPTION

#         if current_choice == STAY_OPTION and current_links:
#             paths[p][STAY_OPTION] = {
#                 "hops": float(len(current_links)),
#                 "links": sorted(current_links, key=str),
#             }
#             opts.append(STAY_OPTION)

#         current_option_map[p] = current_choice
#         current_links_map[p] = current_links

#         recent = recent_options(route_manager, a, b)

#         cand = []

#         for opt in opts:
#             # Do NOT remove the current option.
#             # It represents "stay".
#             if avoid_recent and opt in recent and opt != current_choice:
#                 continue

#             cand.append(opt)

#         if not cand:
#             raise RuntimeError(f"No feasible route option for {p}")

#         feasible[p] = cand

#     model = pulp.LpProblem("Route_Assignment", pulp.LpMinimize)

#     y = {
#         (p, opt): pulp.LpVariable(
#             f"y_{p[0]}_{p[1]}_{str(opt).replace('-', 'm')}",
#             cat="Binary",
#         )
#         for p in selected_pairs
#         for opt in feasible[p]
#     }

#     # C1: each selected route chooses exactly one option.
#     # That option can be a real mutation option or "stay".
#     for p in selected_pairs:
#         model += pulp.lpSum(y[p, opt] for opt in feasible[p]) == 1

#     # Include only links affected by selected routes.
#     # This avoids infeasible crashes from unrelated overloaded links.
#     all_links = set()

#     for p in selected_pairs:
#         all_links.update(current_links_map.get(p, set()))

#         for opt in feasible[p]:
#             all_links.update(paths[p][opt]["links"])

#     all_links_sorted = sorted(all_links, key=str)

#     overload = {
#         l: pulp.LpVariable(f"overload_{i}", lowBound=0)
#         for i, l in enumerate(all_links_sorted)
#     }

#     overlap = {
#         l: pulp.LpVariable(f"overlap_{i}", lowBound=0)
#         for i, l in enumerate(all_links_sorted)
#     }

#     # Link-load prediction constraints
#     for l in all_links_sorted:
#         current_load = link_load.get(l, 0.0)

#         removed_load = []
#         added_load = []
#         used_count = []

#         for p in selected_pairs:
#             d = demand.get(p, DEFAULT_DEMAND)

#             # Remove selected route demand from current active path.
#             if l in current_links_map.get(p, set()):
#                 removed_load.append(d)

#             # Add selected route demand to candidate selected path.
#             # IMPORTANT:
#             # Do NOT multiply d by number of links.
#             # A 0.5 Mbps route contributes 0.5 Mbps to each link it uses.
#             for opt in feasible[p]:
#                 if l in paths[p][opt]["links"]:
#                     added_load.append(d * y[p, opt])
#                     used_count.append(y[p, opt])

#         final_load = (
#             current_load
#             - pulp.lpSum(removed_load)
#             + pulp.lpSum(added_load)
#         )

#         # Soft safety threshold:
#         # prefer <= 0.8 Mbps, but allow up to hard limit with penalty.
#         model += final_load <= THETA * CAPACITY_MBPS + overload[l]

#         # Non-worsening hard capacity:
#         # - If current load is below 1.0, final cannot exceed 1.0.
#         # - If current load is already above 1.0, final cannot become worse.
#         if ENFORCE_NON_WORSENING_CAPACITY:
#             hard_limit = max(CAPACITY_MBPS, current_load)
#             model += final_load <= hard_limit

#         # Softly avoid placing multiple selected routes on the same new link.
#         if used_count:
#             model += pulp.lpSum(used_count) <= 1 + overlap[l]

#     obj = []

#     for p in selected_pairs:
#         old_links = current_links_map.get(p, set())
#         current_choice = current_option_map.get(p)

#         for opt in feasible[p]:
#             info = paths[p][opt]

#             new_links = set(info["links"])
#             shared_old_links = new_links.intersection(old_links)

#             hop_cost = info["hops"]

#             # Candidate path load cost.
#             # This is a path preference term, not capacity math.
#             load_cost = sum(link_load.get(l, 0.0) for l in new_links)

#             old_link_reuse_ratio = len(shared_old_links) / max(1, len(old_links))
#             old_link_reuse_load = sum(link_load.get(l, 0.0) for l in shared_old_links)

#             mutation_cost = 0.0 if opt == current_choice else MUTATION_WEIGHT

#             path_cost = (
#                 HOP_WEIGHT * hop_cost
#                 + LOAD_WEIGHT * load_cost
#                 + OLD_LINK_REUSE_WEIGHT * old_link_reuse_ratio
#                 + OLD_LINK_LOAD_WEIGHT * old_link_reuse_load
#                 + mutation_cost
#             )

#             obj.append(path_cost * y[p, opt])

#     obj += [OVERLOAD_WEIGHT * v for v in overload.values()]
#     obj += [MULTI_FLOW_OVERLAP_WEIGHT * v for v in overlap.values()]

#     model += pulp.lpSum(obj)

#     t0 = time.perf_counter()
#     model.solve(pulp.PULP_CBC_CMD(msg=False))
#     solver_time_s = time.perf_counter() - t0

#     print(
#         f"[ROUTE ILP SOLVER TIME] {solver_time_s:.6f}s | "
#         f"status={pulp.LpStatus[model.status]}"
#     )

#     if pulp.LpStatus[model.status] != "Optimal":
#         raise RuntimeError(f"Route ILP failed: {pulp.LpStatus[model.status]}")

#     assignment = {}

#     for p in selected_pairs:
#         for opt in feasible[p]:
#             if pulp.value(y[p, opt]) > 0.5:
#                 if opt == current_option_map.get(p) or opt == STAY_OPTION:
#                     print(
#                         f"[ROUTE STAY] {p} remains on current route "
#                         f"option {current_option_map.get(p)}"
#                     )
#                 else:
#                     assignment[p] = opt

#     return assignment


# # =====================================================
# # APPLY ROUTE ASSIGNMENT
# # =====================================================

# def apply_route_assignment(route_manager, assignment):
#     """
#     Calls the existing route mutation endpoint and updates route history.
#     """

#     if not assignment:
#         print("No route assignment.")
#         return

#     hosts_arg = []
#     opts_arg = []
#     selected_for_history = []

#     # Handle bug:
#     # sometimes h1,h28 opt9 is missing but h28,h1 opt9 exists.
#     hop_rows = {
#         (r[0].strip(), r[1].strip(), int(r[2]))
#         for r in csv.reader(open(HOP_LIST_FILE))
#         if len(r) >= 3
#     }

#     for (a, b), opt in assignment.items():
#         hist_a, hist_b = a, b

#         if (a, b, opt) not in hop_rows and (b, a, opt) in hop_rows:
#             print(f"[FLIP ROUTE APPLY] ({a},{b},{opt}) missing; using ({b},{a},{opt})")
#             a, b = b, a

#         hosts_arg.append(f"{a},{b}")
#         opts_arg.append(str(opt))

#         selected_for_history.append((hist_a, hist_b, opt))

#     route_shuffle_endpoint_merge_log(
#         specific_multiple=True,
#         hosts=";".join(hosts_arg),
#         opt=";".join(opts_arg),
#     )

#     for a, b, opt in selected_for_history:
#         route_manager.update_pair(a, b, opt)

#     route_manager.save_to_csv()

#     print("[ROUTE ILP ASSIGNMENT]", assignment)


# # =====================================================
# # ENTRY POINT
# # =====================================================

# def run_route_ilp(selected_pairs):
#     route_manager = RouteHistoryManager(all_hosts, queue_size=ROUTE_HISTORY_SIZE)
#     route_manager.load_from_csv()

#     # 1. Read v3 for current route links and byte-derived demand.
#     route_demands, observed_current_links = load_route_observations_from_v3()

#     # 2. Read physical current link load.
#     link_load = load_link_loads()

#     # 3. For selected routes missing byte demand, estimate demand from link-load share.
#     route_demands = estimate_missing_demands_from_link_load(
#         selected_pairs=selected_pairs,
#         demands=route_demands,
#         observed_current_links=observed_current_links,
#         link_load=link_load,
#         route_manager=route_manager,
#     )

#     selected_norm = [pair_key(a, b) for a, b in selected_pairs]

#     print("[ROUTE DEMAND USED BY ILP]", {
#         p: round(route_demands.get(p, DEFAULT_DEMAND), 4)
#         for p in selected_norm
#     })

#     try:
#         assignment = solve_route_assignment(
#             selected_pairs,
#             route_manager,
#             demand=route_demands,
#             observed_current_links=observed_current_links,
#             avoid_recent=True,
#         )
#     except RuntimeError as e:
#         print("[WARN]", e)
#         print("Retrying without recent-route restriction.")

#         try:
#             assignment = solve_route_assignment(
#                 selected_pairs,
#                 route_manager,
#                 demand=route_demands,
#                 observed_current_links=observed_current_links,
#                 avoid_recent=False,
#             )
#         except RuntimeError as e2:
#             print("[WARN] Route ILP still failed after retry:", e2)
#             print("[ROUTE ILP] Skipping route mutation this cycle.")
#             assignment = {}

#     apply_route_assignment(route_manager, assignment)


# # if __name__ == "__main__":
# #     run_route_ilp([
# #         ("h39", "h2"),
# #         ("h15", "h33"),
# #     ])


import csv, time
from collections import defaultdict
import pulp
from route_mutate_endpoint import route_shuffle_endpoint_merge_log
from mtd_utils import RouteHistoryManager, all_hosts, ROUTE_HISTORY_SIZE

HOP_LIST_FILE, LINK_STATS_FILE = "hop_list.csv", "link_stats_onos.csv"
ROUTE_OVERLAP_FILE = "onos_active_flow_route_overlap_v3.csv"

CAPACITY_MBPS = 1.0
DEFAULT_DEMAND = 0.05

DEMAND_MARGIN = 1.15
TREND_WEIGHT = 0.50

WARM_LEVEL = 0.65
HOT_LEVEL = 0.80
CRITICAL_LEVEL = 0.95

DECEPTION_WEIGHT = 10.0
RELIEF_WEIGHT = 3.0
MUTATION_WEIGHT = 0.75

WARM_WEIGHT = 2.0
HOT_WEIGHT = 15.0
CRITICAL_WEIGHT = 80.0
CAPACITY_EXCESS_WEIGHT = 150.0

MULTI_FLOW_OVERLAP_WEIGHT = 0.05
HISTORY_REUSE_WEIGHT = 1.0

_PREV_ROUTE_BYTES, _PREV_ROUTE_TIME, _LAST_ROUTE_DEMAND = {}, {}, {}


def pair_key(a, b):
    return tuple(sorted((a, b), key=lambda x: int(str(x)[1:])))


def latest_recorded_option(xs, default=0):
    try:
        return int(xs[-1]) if xs else default
    except Exception:
        return default


def dpid_to_switch(x):
    x = str(x).strip()

    if x.startswith("of:"):
        return f"s{int(x[3:].split('/')[0].split(':')[0], 16)}"

    return x.split("/")[0].split(":")[0]


def normalize_link_id(x):
    x = str(x).strip()

    if "->" not in x:
        return x

    a, b = map(str.strip, x.split("->", 1))
    return tuple(sorted((dpid_to_switch(a), dpid_to_switch(b))))


def load_link_state():
    """Return latest link load and positive one-sample load trend."""
    snapshots = defaultdict(dict)

    try:
        with open(LINK_STATS_FILE, newline="") as f:
            for r in csv.DictReader(f):
                ts = str(r.get("timestamp", "")).strip()
                if not ts:
                    continue

                rx = float(r.get("rx_mbps", 0.0) or 0.0)
                tx = float(r.get("tx_mbps", 0.0) or 0.0)
                link = normalize_link_id(r["link_id"])
                load = max(rx, tx)

                # Keep the larger direction after undirected normalization.
                snapshots[ts][link] = max(
                    snapshots[ts].get(link, 0.0), load
                )
    except Exception as e:
        print(f"[WARN] {LINK_STATS_FILE}: {e}")
        return {}, {}

    times = sorted(snapshots)
    if not times:
        return {}, {}

    latest = snapshots[times[-1]]
    previous = snapshots[times[-2]] if len(times) > 1 else {}

    trend = {
        link: max(0.0, latest.get(link, 0.0) - previous.get(link, 0.0))
        for link in set(latest) | set(previous)
    }

    return latest, trend


def load_link_loads():
    # Preserve compatibility with any other code using this function.
    return load_link_state()[0]


def load_paths():
    paths = defaultdict(dict)

    with open(HOP_LIST_FILE, newline="") as f:
        for r in csv.reader(f):
            if len(r) < 7:
                continue

            pair = pair_key(r[0].strip(), r[1].strip())
            option = int(r[2])

            links = [
                normalize_link_id(x)
                for x in r[6].split(",")
                if "->" in x
            ]

            paths[pair][option] = {
                "hops": float(r[3]),
                "links": links,
            }

    return paths


def host_pair_from_flow_name(flow):
    try:
        a, b = map(str.strip, str(flow or "").split("->", 1))

        if a.startswith("h") and b.startswith("h"):
            return pair_key(a, b)

    except Exception:
        pass

    return None


def parse_route_link_set(row):
    text = (
        row.get("active_route_link_ids")
        or row.get("active_route_links")
        or ""
    )

    return {
        normalize_link_id(x)
        for x in str(text).split(";")
        if "->" in x
    }


def load_route_observations_from_v3():
    global _PREV_ROUTE_BYTES, _PREV_ROUTE_TIME, _LAST_ROUTE_DEMAND

    demands, observed = {}, {}

    try:
        with open(ROUTE_OVERLAP_FILE, newline="") as f:
            rows = [
                r for r in csv.DictReader(f)
                if r.get("timestamp")
            ]
    except Exception as e:
        print(f"[WARN] {ROUTE_OVERLAP_FILE}: {e}")
        return demands, observed

    if not rows:
        return demands, observed

    latest = max(r["timestamp"] for r in rows)

    try:
        now = time.mktime(
            time.strptime(latest, "%Y-%m-%d %H:%M:%S")
        )
    except Exception:
        now = time.time()

    for row in (r for r in rows if r["timestamp"] == latest):
        pair = host_pair_from_flow_name(row.get("flow"))

        if not pair:
            continue

        links = parse_route_link_set(row)

        if links:
            observed[pair] = links

        measured = None

        for column in ("route_demand_mbps", "demand_mbps"):
            try:
                if str(row.get(column, "")).strip():
                    measured = float(row[column])
                    break
            except ValueError:
                pass

        if measured is None:
            try:
                current_bytes = float(row.get("bytes", 0) or 0)
            except ValueError:
                current_bytes = 0.0

            previous_bytes = _PREV_ROUTE_BYTES.get(pair)
            previous_time = _PREV_ROUTE_TIME.get(pair)

            if (
                previous_bytes is not None
                and previous_time is not None
                and now > previous_time
            ):
                measured = (
                    max(0.0, current_bytes - previous_bytes)
                    * 8
                    / ((now - previous_time) * 1_000_000)
                )

            _PREV_ROUTE_BYTES[pair] = current_bytes
            _PREV_ROUTE_TIME[pair] = now

        if measured is None:
            measured = _LAST_ROUTE_DEMAND.get(pair)

        if measured is not None and measured > 0:
            demands[pair] = max(
                demands.get(pair, 0.0),
                measured,
            )
            _LAST_ROUTE_DEMAND[pair] = demands[pair]

    return demands, observed


# def estimate_missing_demands_from_link_load(
#     selected_pairs,
#     demands,
#     observed,
#     link_load,
#     manager,
# ):
#     paths = load_paths()
#     estimated = dict(demands)
#     link_users = defaultdict(set)

#     for pair, links in observed.items():
#         for link in links:
#             link_users[link].add(pair)

#     for pair in (pair_key(*x) for x in selected_pairs):
#         if estimated.get(pair, 0) > 0:
#             continue

#         links = set(observed.get(pair, ()))

#         if not links:
#             current = latest_recorded_option(
#                 manager.get_pair_history(*pair)
#             )
#             links = set(
#                 paths.get(pair, {})
#                 .get(current, {})
#                 .get("links", ())
#             )

#         if links:
#             estimated[pair] = max(
#                 link_load.get(link, 0.0)
#                 / max(
#                     1,
#                     len(link_users[link])
#                     + (pair not in link_users[link]),
#                 )
#                 for link in links
#             )

#     return estimated

def estimate_missing_demands_from_link_load(
    selected_pairs, demands, observed, link_load, manager
):
    paths, est = load_paths(), dict(demands)
    pair_links = {}

    # Resolve the current path of every selected pair.
    for p in (pair_key(*x) for x in selected_pairs):
        links = set(observed.get(p, ()))

        if not links:
            cur = latest_recorded_option(
                manager.get_pair_history(*p)
            )
            links = set(
                paths.get(p, {})
                .get(cur, {})
                .get("links", ())
            )

        pair_links[p] = links

    # Count all observed and selected flows using each link.
    users = defaultdict(set)

    for p, links in observed.items():
        for link in links:
            users[link].add(p)

    for p, links in pair_links.items():
        for link in links:
            users[link].add(p)

    # Estimate each missing demand from its fair link-load share.
    for p, links in pair_links.items():
        if est.get(p, 0) > 0 or not links:
            continue

        est[p] = max(
            link_load.get(link, 0.0)
            / max(1, len(users[link]))
            for link in links
        )

    return est

def solve_route_assignment(
    selected_pairs,
    route_manager,
    demand=None,
    avoid_recent=True,
):
    """
    Proactive route selection:
      - predicts near-future link pressure using current load + positive trend;
      - rewards new links, rare route options, and relief from risky old links;
      - allows some pairs to stay;
      - uses only soft utilization penalties;
      - treats overlap as a very small tie-breaker.
    """
    paths = load_paths()
    link_load, link_trend = load_link_state()
    pairs = [pair_key(a, b) for a, b in selected_pairs]

    if not pairs:
        return {}

    supplied_demand = {
        pair_key(*p): max(0.0, float(v))
        for p, v in (demand or {}).items()
    }

    feasible = {}
    current_option_map = {}
    current_links_map = {}
    history_map = {}

    for p in pairs:
        opts = list(paths.get(p, {}))
        if not opts:
            raise RuntimeError(f"No path options for {p}")

        history = [
            int(x)
            for x in route_manager.get_pair_history(*p)
            if str(x).lstrip("-").isdigit()
        ]
        current = latest_recorded_option(history, default=0)
        recent = {x for x in history if x != 0}

        current_option_map[p] = current
        current_links_map[p] = set(
            paths[p].get(current, {}).get("links", ())
        )
        history_map[p] = history

        # Keep the current route available. Only recent alternatives are blocked.
        candidates = [
            opt
            for opt in opts
            if not (
                avoid_recent
                and opt in recent
                and opt != current
            )
        ]

        if not candidates:
            raise RuntimeError(f"No feasible route option for {p}")

        feasible[p] = candidates

    # Estimate missing pair demand from the selected pairs' current-link shares.
    link_users = defaultdict(set)
    for p, links in current_links_map.items():
        for link in links:
            link_users[link].add(p)

    predicted_demand = {}
    for p in pairs:
        estimate = supplied_demand.get(p)

        if estimate is None:
            shares = [
                link_load.get(link, 0.0)
                / max(1, len(link_users[link]))
                for link in current_links_map[p]
            ]
            estimate = max([DEFAULT_DEMAND] + shares)

        predicted_demand[p] = DEMAND_MARGIN * max(
            DEFAULT_DEMAND, estimate
        )

    print(
        "[PREDICTED ROUTE DEMAND]",
        {p: round(predicted_demand[p], 4) for p in pairs},
    )

    model = pulp.LpProblem(
        "Proactive_Route_Deception",
        pulp.LpMaximize,
    )

    y = {
        (p, opt): pulp.LpVariable(
            f"y_{p[0]}_{p[1]}_{opt}", cat="Binary"
        )
        for p in pairs
        for opt in feasible[p]
    }

    for p in pairs:
        model += pulp.lpSum(y[p, opt] for opt in feasible[p]) == 1

    all_links = set(link_load)
    for p in pairs:
        all_links.update(current_links_map[p])
        for opt in feasible[p]:
            all_links.update(paths[p][opt]["links"])

    ordered_links = sorted(all_links, key=str)

    warm = {
        link: pulp.LpVariable(f"warm_{i}", lowBound=0)
        for i, link in enumerate(ordered_links)
    }
    hot = {
        link: pulp.LpVariable(f"hot_{i}", lowBound=0)
        for i, link in enumerate(ordered_links)
    }
    critical = {
        link: pulp.LpVariable(f"critical_{i}", lowBound=0)
        for i, link in enumerate(ordered_links)
    }
    capacity_excess = {
        link: pulp.LpVariable(f"capacity_excess_{i}", lowBound=0)
        for i, link in enumerate(ordered_links)
    }
    overlap = {
        link: pulp.LpVariable(f"overlap_{i}", lowBound=0)
        for i, link in enumerate(ordered_links)
    }

    for link in ordered_links:
        current = link_load.get(link, 0.0)
        old_users = [p for p in pairs if link in current_links_map[p]]

        # Never subtract more selected demand than the measured link carries.
        total_old_estimate = sum(predicted_demand[p] for p in old_users)
        removal_scale = min(
            1.0,
            current / max(total_old_estimate, 1e-9),
        )
        removed = sum(
            predicted_demand[p] * removal_scale
            for p in old_users
        )

        added = []
        selected_count = []

        for p in pairs:
            for opt in feasible[p]:
                if link in paths[p][opt]["links"]:
                    added.append(predicted_demand[p] * y[p, opt])
                    selected_count.append(y[p, opt])

        final_load = current - removed + pulp.lpSum(added)

        # Positive trend anticipates near-future pressure before congestion occurs.
        predicted_final_load = (
            final_load
            + TREND_WEIGHT * link_trend.get(link, 0.0)
        )

        # All utilization constraints are soft through excess variables.
        model += warm[link] >= (
            predicted_final_load - WARM_LEVEL * CAPACITY_MBPS
        )
        model += hot[link] >= (
            predicted_final_load - HOT_LEVEL * CAPACITY_MBPS
        )
        model += critical[link] >= (
            predicted_final_load - CRITICAL_LEVEL * CAPACITY_MBPS
        )
        model += capacity_excess[link] >= (
            predicted_final_load - CAPACITY_MBPS
        )

        # Two selected routes may share a link without a penalty.
        if selected_count:
            model += (
                pulp.lpSum(selected_count)
                <= 2 + overlap[link]
            )

    route_rewards = []

    for p in pairs:
        old_links = current_links_map[p]
        history = history_map[p]

        for opt in feasible[p]:
            new_links = set(paths[p][opt]["links"])
            shared = old_links & new_links

            old_link_novelty = 1.0 - (
                len(shared) / max(1, len(old_links))
            )

            union = old_links | new_links
            jaccard_novelty = 1.0 - (
                len(shared) / max(1, len(union))
            )

            link_novelty = (
                0.75 * old_link_novelty
                + 0.25 * jaccard_novelty
            )

            history_frequency = (
                history.count(opt) / max(1, len(history))
            )
            history_novelty = 1.0 - history_frequency

            deception = (
                0.75 * link_novelty
                + 0.25 * history_novelty
            )
            HOP_WEIGHT = 0.05
            # Reward leaving currently loaded or rising-risk old links.
            relief = sum(
                (
                    link_load.get(link, 0.0)
                    + TREND_WEIGHT * link_trend.get(link, 0.0)
                ) / CAPACITY_MBPS
                for link in old_links - new_links
            )

            mutation = 1.0 if opt != current_option_map[p] else 0.0

            reward = (
                DECEPTION_WEIGHT * deception
                + RELIEF_WEIGHT * relief
                + MUTATION_WEIGHT * mutation
            )

            ## if only hop count becomes too important
            # hop_penalty = HOP_WEIGHT * paths[p][opt]["hops"]

            # reward = (
            #     DECEPTION_WEIGHT * deception
            #     + RELIEF_WEIGHT * relief
            #     + MUTATION_WEIGHT * mutation
            #     - hop_penalty
            # )

            route_rewards.append(reward * y[p, opt])

    model += (
        pulp.lpSum(route_rewards)
        - WARM_WEIGHT * pulp.lpSum(warm.values())
        - HOT_WEIGHT * pulp.lpSum(hot.values())
        - CRITICAL_WEIGHT * pulp.lpSum(critical.values())
        - CAPACITY_EXCESS_WEIGHT * pulp.lpSum(capacity_excess.values())
        - MULTI_FLOW_OVERLAP_WEIGHT * pulp.lpSum(overlap.values())
    )

    start = time.perf_counter()
    model.solve(pulp.PULP_CBC_CMD(msg=False))
    solver_time = time.perf_counter() - start
    status = pulp.LpStatus[model.status]

    print(
        f"[PROACTIVE ROUTE ILP] {solver_time:.6f}s | "
        f"status={status} | objective={pulp.value(model.objective):.4f}"
    )

    if status != "Optimal":
        raise RuntimeError(f"Route ILP failed: {status}")

    # Return only actual mutations. Current-route selections become STAY actions.
    assignment = {}

    for p in pairs:
        selected = next(
            (
                opt
                for opt in feasible[p]
                if pulp.value(y[p, opt]) > 0.5
            ),
            None,
        )

        if selected is None:
            continue

        if selected == current_option_map[p]:
            print(f"[ROUTE STAY] {p}: option {selected}")
        else:
            assignment[p] = selected
            print(
                f"[ROUTE MUTATE] {p}: "
                f"{current_option_map[p]} -> {selected}"
            )

    return assignment


def apply_route_assignment(manager, assignment):
    if not assignment:
        print("No route assignment.")
        return

    with open(HOP_LIST_FILE, newline="") as f:
        hop_rows = {
            (
                row[0].strip(),
                row[1].strip(),
                int(row[2]),
            )
            for row in csv.reader(f)
            if len(row) >= 3
        }

    hosts, options, history = [], [], []

    for (a, b), option in assignment.items():
        history_a, history_b = a, b

        if (
            (a, b, option) not in hop_rows
            and (b, a, option) in hop_rows
        ):
            a, b = b, a

        hosts.append(f"{a},{b}")
        options.append(str(option))
        history.append(
            (history_a, history_b, option)
        )

    route_shuffle_endpoint_merge_log(
        specific_multiple=True,
        hosts=";".join(hosts),
        opt=";".join(options),
    )

    for a, b, option in history:
        manager.update_pair(a, b, option)

    manager.save_to_csv()

    print("[ROUTE ILP ASSIGNMENT]", assignment)


def run_route_ilp(selected_pairs):
    route_manager = RouteHistoryManager(
        all_hosts,
        queue_size=ROUTE_HISTORY_SIZE,
    )
    route_manager.load_from_csv()

    try:
        assignment = solve_route_assignment(
            selected_pairs,
            route_manager,
            avoid_recent=True,
        )
    except RuntimeError as e:
        print("[WARN]", e)
        print("Retrying without recent-route restriction.")
        assignment = solve_route_assignment(
            selected_pairs,
            route_manager,
            avoid_recent=False,
        )

    apply_route_assignment(route_manager, assignment)

    # Record STAY decisions too, so history represents every decision cycle.
    for a, b in selected_pairs:
        p = pair_key(a, b)
        if p in assignment:
            continue

        current = latest_recorded_option(
            route_manager.get_pair_history(*p),
            default=0,
        )
        route_manager.update_pair(*p, current)

    route_manager.save_to_csv()