
# # proactive_ilp_decision_compact.py

# import re
# import math,time
# import requests
# import pandas as pd
# import numpy as np
# from requests.auth import HTTPBasicAuth
# from proactive_new_logging import log_evaluation_snapshot

# from mtd_utils import repeat_ip_history, repeat_route_history
# import pulp
# # new
# from proactive_new_mitigation_route import run_route_ilp
# from proactive_new_mitigation import run_ip_ilp

# # =========================
# # CONFIG
# # =========================

# ONOS_BASE_URL = "http://127.0.0.1:8181"
# ONOS_USER = "onos"
# ONOS_PASS = "rocks"

# HOST_PPS_MONITOR_THRESHOLD = 100.0
# HOST_RX_MBPS_THRESHOLD = 0.080
# HOST_TX_MBPS_THRESHOLD = 0.091

# LINK_CAPACITY_MBPS = 1.0
# LINK_MONITOR_THRESHOLD_MBPS = 0.8

# EXCLUDED_IP_HOSTS = {"h1"}

# K_IP = 10
# K_ROUTE = 10
# DEFENSE_BUDGET = 0.50
 
# E_IP = 0.70
# # E_IP = 0.70 #Eip​=1−23.75/39.72​
# # E_ROUTE = 0.70
# E_ROUTE = 0.60 # Eroute​=1−10.99/27.45 -- from graph​


# O_IP = 2830 / 3000
# O_ROUTE = 0.05

# LAMBDA_IP = 0.15

# DEFAULT_GRID_PRIORITY = 0.0

# # RECENT_WINDOW = 10 
# RECENT_WINDOW = 15


# IP_ACTIVE_ONLY = False
# # new
# # =========================
# # STATIC MININET HOST DOMAIN
# # =========================

# MININET_MAC_PREFIX = "00:00:00:00:00:"
# MININET_IP_PREFIX = "10.0.0."
# MIN_HOST_ID = 1
# MAX_HOST_ID = 40

# # =========================
# # BASIC HELPERS
# # =========================

# def host_num(host):
#     m = re.search(r"\d+", str(host))
#     return int(m.group()) if m else None


# # def host_from_ip(ip):
# #     """
# #     Example:
# #         10.0.0.35/32 -> h35
# #         10.0.0.35    -> h35
# #     """
# #     try:
# #         ip = str(ip).split("/")[0]
# #         return f"h{int(ip.split('.')[-1])}"
# #     except Exception:
# #         return None

# # new
# def host_from_ip(ip):
#     """
#     Only map internal Mininet IPs:
#         10.0.0.1  -> h1
#         10.0.0.40 -> h40

#     Ignore external/OPAL/NAT IPs:
#         192.168.*.* -> None
#     """
#     try:
#         ip = str(ip).split("/")[0].strip()

#         if not ip.startswith(MININET_IP_PREFIX):
#             return None

#         host_id = int(ip.split(".")[-1])

#         if MIN_HOST_ID <= host_id <= MAX_HOST_ID:
#             return f"h{host_id}"

#         return None

#     except Exception:
#         return None

# # def host_from_mac(mac):
# #     """
# #     Example:
# #         00:00:00:00:00:23 -> h35
# #         because hex 23 = decimal 35
# #     """
# #     try:
# #         last = str(mac).split(":")[-1]
# #         return f"h{int(last, 16)}"
# #     except Exception:
# #         return None

# # new
# def host_from_mac(mac):
#     """
#     Only map Mininet host MACs:
#         00:00:00:00:00:01 -> h1
#         00:00:00:00:00:28 -> h40

#     Ignore external bridge / OPAL / physical NIC MACs.
#     """
#     try:
#         mac = str(mac).lower().strip()

#         if not mac.startswith(MININET_MAC_PREFIX):
#             return None

#         host_id = int(mac.split(":")[-1], 16)

#         if MIN_HOST_ID <= host_id <= MAX_HOST_ID:
#             return f"h{host_id}"

#         return None

#     except Exception:
#         return None

# def pair_key(a, b):
#     return tuple(sorted((str(a), str(b)), key=lambda x: host_num(x) or 99999))


# def safe_norm(s):
#     s = pd.to_numeric(s, errors="coerce").fillna(0.0)
#     mn, mx = s.min(), s.max()
#     if mx == mn:
#         return pd.Series([0.0] * len(s), index=s.index)
#     return (s - mn) / (mx - mn)


# def parse_history(v):
#     if pd.isna(v):
#         return []
#     return [x.strip() for x in str(v).split(",") if x.strip()]


# def latest_same_count(values):
#     if not values:
#         return 0
#     last = values[-1]
#     c = 0
#     for v in reversed(values):
#         if v == last:
#             c += 1
#         else:
#             break
#     return c


# def path_links(path):
#     links = []

#     if pd.isna(path):
#         return links

#     for item in str(path).split(","):
#         item = item.strip()

#         if "->" in item:
#             lk = normalize_onos_link(item)
#             if lk:
#                 links.append(lk)

#     return links

# # =========================
# # ONOS REST API
# # =========================

# # new
# def fetch_onos_host_maps(
#     base_url=ONOS_BASE_URL,
#     user=ONOS_USER,
#     password=ONOS_PASS,
#     timeout=5,
# ):
#     """
#     Fetch ONOS hosts and build safe maps:
#         ip_to_h  = only 10.0.0.X -> hX
#         mac_to_h = only 00:00:00:00:00:XX -> hX

#     External/OPAL/bridge addresses are ignored.
#     """

#     url = f"{base_url.rstrip('/')}/onos/v1/hosts"
#     r = requests.get(url, auth=HTTPBasicAuth(user, password), timeout=timeout)
#     r.raise_for_status()

#     data = r.json()
#     ip_to_h = {}
#     mac_to_h = {}

#     for item in data.get("hosts", []):
#         mac = item.get("mac")
#         ips = item.get("ipAddresses", [])

#         # MAC is the safest identity for your Mininet hosts.
#         h_from_mac = host_from_mac(mac)

#         if h_from_mac is not None:
#             mac_to_h[str(mac).lower()] = h_from_mac

#         # Only add internal 10.0.0.X IPs.
#         for ip in ips:
#             ip_clean = str(ip).split("/")[0].strip()
#             h_from_ip = host_from_ip(ip_clean)

#             if h_from_ip is not None:
#                 ip_to_h[ip_clean] = h_from_ip

#     return ip_to_h, mac_to_h

# def criterion_value(criteria, names):
#     """
#     Extract values from ONOS flow selector criteria.
#     Supports common ONOS fields:
#         IPV4_SRC, IPV4_DST, ETH_SRC, ETH_DST
#     """

#     for c in criteria:
#         ctype = c.get("type")

#         if ctype not in names:
#             continue

#         for key in ["ip", "mac", "value"]:
#             if key in c:
#                 return c[key]

#     return None


# def fetch_onos_active_pairs(
#     base_url=ONOS_BASE_URL,
#     user=ONOS_USER,
#     password=ONOS_PASS,
#     timeout=5,
# ):
#     """
#     Fetch active ONOS flows and extract active host pairs.

#     Returns:
#         active_pairs = {("h1", "h35"), ("h2", "h30")}
#         active_hosts = {"h1", "h35", "h2", "h30"}

#     Note:
#         This works when ONOS flow selector has source/destination IP or MAC.
#     """

#     ip_to_h, mac_to_h = fetch_onos_host_maps(base_url, user, password, timeout)

#     url = f"{base_url.rstrip('/')}/onos/v1/flows"
#     r = requests.get(url, auth=HTTPBasicAuth(user, password), timeout=timeout)
#     r.raise_for_status()

#     data = r.json()

#     active_pairs = set()
#     active_hosts = set()

#     for flow in data.get("flows", []):
#         if flow.get("state") != "ADDED":
#             continue

#         criteria = flow.get("selector", {}).get("criteria", [])

#         src_ip = criterion_value(criteria, {"IPV4_SRC", "IPV6_SRC"})
#         dst_ip = criterion_value(criteria, {"IPV4_DST", "IPV6_DST"})

#         src_mac = criterion_value(criteria, {"ETH_SRC"})
#         dst_mac = criterion_value(criteria, {"ETH_DST"})

#         src = None
#         dst = None

#         if src_ip:
#             src = ip_to_h.get(str(src_ip).split("/")[0]) or host_from_ip(src_ip)

#         if dst_ip:
#             dst = ip_to_h.get(str(dst_ip).split("/")[0]) or host_from_ip(dst_ip)

#         if src is None and src_mac:
#             src = mac_to_h.get(str(src_mac).lower()) or host_from_mac(src_mac)

#         if dst is None and dst_mac:
#             dst = mac_to_h.get(str(dst_mac).lower()) or host_from_mac(dst_mac)

#         # if src and dst and src != dst:
#         #     p = pair_key(src, dst)
#         #     active_pairs.add(p)
#         #     active_hosts.update(p)

#         if src and dst and src != dst:
#             src_n = host_num(src)
#             dst_n = host_num(dst)

#             # Keep only real Mininet hosts h1-h40
#             if src_n is None or dst_n is None:
#                 continue

#             if not (MIN_HOST_ID <= src_n <= MAX_HOST_ID):
#                 continue

#             if not (MIN_HOST_ID <= dst_n <= MAX_HOST_ID):
#                 continue

#             p = pair_key(src, dst)
#             active_pairs.add(p)
#             active_hosts.update(p)

#     return active_pairs, active_hosts


# # =========================
# # OBSERVABILITY / PMU RANK
# # =========================

# def load_grid_priority(obs_csv):
#     """
#     PMU/bus rank gives power-grid priority.

#     Expected:
#         PMU 39 or gen_bus 39 means host h39.

#     Rank handling:
#         rank 1 -> priority 1.0
#         lower ranks -> smaller priority
#         hosts not listed -> DEFAULT_GRID_PRIORITY
#     """

#     obs = pd.read_csv(obs_csv)

#     cols = {c.lower(): c for c in obs.columns}

#     host_col = None
#     rank_col = None

#     for key in ["pmu", "gen_bus", "bus", "host"]:
#         if key in cols:
#             host_col = cols[key]
#             break

#     for key in ["rank", "pmu_rank", "observability_rank"]:
#         if key in cols:
#             rank_col = cols[key]
#             break

#     if host_col is None or rank_col is None:
#         return {}

#     obs["host"] = obs[host_col].apply(lambda x: f"h{int(x)}" if pd.notna(x) else None)
#     obs["rank"] = pd.to_numeric(obs[rank_col], errors="coerce")

#     obs = obs.dropna(subset=["host", "rank"])

#     if obs.empty:
#         return {}

#     max_rank = obs["rank"].max()
#     min_rank = obs["rank"].min()

#     if max_rank == min_rank:
#         obs["grid_priority"] = 1.0
#     else:
#         obs["grid_priority"] = 1.0 - ((obs["rank"] - min_rank) / (max_rank - min_rank))

#     return dict(zip(obs["host"], obs["grid_priority"]))


# # =========================
# # IP CANDIDATES
# # =========================

# def build_ip_candidates(
#     host_csv,
#     ip_hist_csv,
#     obs_csv,
#     active_hosts=None,
# ):
#     h = pd.read_csv(host_csv)

#     h["host"] = h["host_mac"].apply(host_from_mac)
#     h = h.dropna(subset=["host"])

#     h = h[~h["host"].isin(EXCLUDED_IP_HOSTS)]

#     if IP_ACTIVE_ONLY and active_hosts is not None:
#         h = h[h["host"].isin(active_hosts)]

#     if h.empty:
#         return []

#     # # Latest row per host
#     # if "timestamp" in h.columns:
#     #     h = h.sort_values("timestamp").groupby("host", as_index=False).tail(1)

#     # Recent max-mean blended values per host || #new 
#     if "timestamp" in h.columns:
#         h = h.sort_values("timestamp").groupby("host", group_keys=False).tail(RECENT_WINDOW)

#         agg = h.groupby("host", as_index=False).agg({
#             "host_mac": "last",
#             "rx_pps": ["max", "mean"],
#             "tx_pps": ["max", "mean"],
#             "rx_mbps": ["max", "mean"],
#             "tx_mbps": ["max", "mean"],
#         })

#         agg.columns = [
#             "host", "host_mac",
#             "rx_pps_max", "rx_pps_mean",
#             "tx_pps_max", "tx_pps_mean",
#             "rx_mbps_max", "rx_mbps_mean",
#             "tx_mbps_max", "tx_mbps_mean",
#         ]

#         for c in ["rx_pps", "tx_pps", "rx_mbps", "tx_mbps"]:
#             agg[c] = 0.9 * agg[f"{c}_max"] + 0.1 * agg[f"{c}_mean"]

#         h = agg[["host", "host_mac", "rx_pps", "tx_pps", "rx_mbps", "tx_mbps"]]

#     for c in ["rx_pps", "tx_pps", "rx_mbps", "tx_mbps"]:
#         h[c] = pd.to_numeric(h[c], errors="coerce").fillna(0.0)

#     h["rx_pps_n"] = safe_norm(h["rx_pps"])
#     h["tx_pps_n"] = safe_norm(h["tx_pps"])
#     h["rx_mbps_n"] = safe_norm(h["rx_mbps"])
#     h["tx_mbps_n"] = safe_norm(h["tx_mbps"])

#     h["traffic_risk"] = (
#         0.35 * h["tx_pps_n"]
#         + 0.25 * h["rx_pps_n"]
#         + 0.25 * h["tx_mbps_n"]
#         + 0.15 * h["rx_mbps_n"]
#     )

#     h["monitor_score"] = np.maximum.reduce([
#         (h["tx_pps"] / HOST_PPS_MONITOR_THRESHOLD).clip(0, 1),
#         (h["rx_pps"] / HOST_PPS_MONITOR_THRESHOLD).clip(0, 1),
#         (h["tx_mbps"] / HOST_TX_MBPS_THRESHOLD).clip(0, 1),
#         (h["rx_mbps"] / HOST_RX_MBPS_THRESHOLD).clip(0, 1),
#     ])

#     ip_hist = pd.read_csv(ip_hist_csv)
#     ip_hist["history_list"] = ip_hist["history"].apply(parse_history)
#     ip_hist["ip_exposure"] = ip_hist["history_list"].apply(
#         lambda x: latest_same_count(x) / max(1, len(x))
#     )

#     exposure_map = dict(zip(ip_hist["host"], ip_hist["ip_exposure"]))

#     grid_map = load_grid_priority(obs_csv)

#     candidates = []

#     for _, row in h.iterrows():
#         host = row["host"]

#         ip_exposure = float(exposure_map.get(host, 0.0))
#         grid_priority = float(grid_map.get(host, DEFAULT_GRID_PRIORITY))

#         # p_host = (
#         #     0.35 * float(row["traffic_risk"])
#         #     + 0.30 * float(row["monitor_score"])
#         #     + 0.25 * grid_priority
#         #     + 0.10 * ip_exposure
#         # )

#         p_host = (
#             0.40 * float(row["traffic_risk"])
#             + 0.35 * float(row["monitor_score"])
#             + 0.25 * grid_priority
#         )

#         benefit = p_host * ip_exposure * E_IP
#         cost = LAMBDA_IP * O_IP
#         score = benefit - cost

#         candidates.append({
#             "host": host,
#             "score": score,
#             "benefit": benefit,
#             "cost": cost,
#             "p_host": p_host,
#             "traffic_risk": float(row["traffic_risk"]),
#             "monitor_score": float(row["monitor_score"]),
#             "ip_exposure": ip_exposure,
#             "grid_priority": grid_priority,
#             "rx_pps": float(row["rx_pps"]),
#             "tx_pps": float(row["tx_pps"]),
#             "rx_mbps": float(row["rx_mbps"]),
#             "tx_mbps": float(row["tx_mbps"]),
#         })

#     candidates.sort(key=lambda x: x["score"], reverse=True)
#     return candidates


# # =========================
# # ROUTE CANDIDATES
# # =========================

# def build_route_candidates(
#     link_csv,
#     hop_csv,
#     route_hist_csv,
#     active_pairs,
# ):
#     if not active_pairs:
#         return []

#     link = pd.read_csv(link_csv)

#     # if "timestamp" in link.columns:
#     #     link = link.sort_values("timestamp").groupby("link_id", as_index=False).tail(1)

#     # Recent max-mean blended values per link || #new
#     if "timestamp" in link.columns:
#         link = link.sort_values("timestamp").groupby("link_id", group_keys=False).tail(RECENT_WINDOW)

#         agg = link.groupby("link_id", as_index=False).agg({
#             "rx_mbps": ["max", "mean"],
#             "tx_mbps": ["max", "mean"],
#         })

#         agg.columns = [
#             "link_id",
#             "rx_mbps_max", "rx_mbps_mean",
#             "tx_mbps_max", "tx_mbps_mean",
#         ]

#         for c in ["rx_mbps", "tx_mbps"]:
#             agg[c] = 0.9 * agg[f"{c}_max"] + 0.1 * agg[f"{c}_mean"]

#         link = agg[["link_id", "rx_mbps", "tx_mbps"]]

#     link["rx_mbps"] = pd.to_numeric(link["rx_mbps"], errors="coerce").fillna(0.0)
#     link["tx_mbps"] = pd.to_numeric(link["tx_mbps"], errors="coerce").fillna(0.0)
#     link["link_mbps"] = link[["rx_mbps", "tx_mbps"]].max(axis=1)

#     link["link_usage_norm"] = (link["link_mbps"] / LINK_CAPACITY_MBPS).clip(0, 1)
#     link["link_monitor"] = (link["link_mbps"] / LINK_MONITOR_THRESHOLD_MBPS).clip(0, 1)
    
#     link["norm_link"] = link["link_id"].apply(normalize_onos_link)

#     usage_map = dict(zip(link["norm_link"], link["link_usage_norm"]))
#     monitor_map = dict(zip(link["norm_link"], link["link_monitor"]))


#     hop = pd.read_csv(
#         hop_csv,
#         header=None,
#         names=["host1", "host2", "option", "hop_count", "src_mac", "dst_mac", "path"]
#     )

#     hop["pair"] = hop.apply(lambda r: pair_key(r["host1"], r["host2"]), axis=1)
#     hop = hop[hop["pair"].isin(active_pairs)].copy()

#     if hop.empty:
#         return []

#     route_hist = pd.read_csv(route_hist_csv)
#     route_hist["pair"] = route_hist.apply(lambda r: pair_key(r["host_a"], r["host_b"]), axis=1)
#     route_hist["history_list"] = route_hist["history"].apply(parse_history)
#     route_hist["route_exposure"] = route_hist["history_list"].apply(
#         lambda x: latest_same_count(x) / max(1, len(x))
#     )

#     exposure_map = dict(zip(route_hist["pair"], route_hist["route_exposure"]))

#     # to handle it not considering opt 0 blindly.
#     route_hist["current_option"] = route_hist["history_list"].apply(
#         lambda x: int(x[-1]) if x else 0
#     )

#     current_option_map = dict(zip(route_hist["pair"], route_hist["current_option"]))
#     # to handle it not considering opt 0 blindly.

#     candidates = []

#     grouped = hop.groupby("pair")

#     # to handle it not considering opt 0 blindly.    
#     # for pair, g in hop.groupby("pair"):
#     #     g0 = g[g["option"].astype(int) == 0]

#     #     if g0.empty:
#     #         continue

#     #     r = g0.iloc[0]
#     #     links = path_links(r["path"])
#     # to handle it not considering opt 0 blindly.

#     for pair, g in hop.groupby("pair"):
#         current_option = int(current_option_map.get(pair, 0))

#         g_current = g[g["option"].astype(int) == current_option]

#         if g_current.empty:
#             continue

#         r = g_current.iloc[0]
#         links = path_links(r["path"])

#         link_usage = max([usage_map.get(x, 0.0) for x in links], default=0.0)
#         link_monitor = max([monitor_map.get(x, 0.0) for x in links], default=0.0)

#         route_exposure = float(exposure_map.get(pair, 0.0))

#         # p_route = (
#         #     0.45 * link_usage
#         #     + 0.30 * link_monitor
#         #     + 0.25 * route_exposure
#         # )

#         p_route = (
#             0.60 * link_usage
#             + 0.40 * link_monitor
#         )

#         benefit = p_route * route_exposure * E_ROUTE
#         # cost = O_ROUTE + 0.10 * link_usage
#         cost = O_ROUTE

#         score = benefit - cost

#         candidates.append({
#             "pair": pair,
#             "src": pair[0],
#             "dst": pair[1],
#             "current_option": current_option,
#             "score": score,
#             "benefit": benefit,
#             "cost": cost,
#             "p_route": p_route,
#             "route_exposure": route_exposure,
#             "link_usage": link_usage,
#             "link_monitor": link_monitor,
#             "path": r["path"],
#         })

#     candidates.sort(key=lambda x: x["score"], reverse=True)
#     return candidates


# # =========================
# # MILP SOLVER
# # =========================

# def solve_milp(ip_candidates, route_candidates):
#     """
#     Binary MILP:

#     maximize:
#         sum IP scores + sum route scores

#     subject to:
#         z_none + z_ip + z_route = 1
#         x_h <= z_ip
#         y_f <= z_route
#         sum x_h <= K_IP z_ip
#         sum y_f <= K_ROUTE z_route
#         total defense cost <= DEFENSE_BUDGET
#     """

#     if pulp is None:
#         return solve_fallback(ip_candidates, route_candidates)

#     model = pulp.LpProblem("Proactive_MTD_Selection", pulp.LpMaximize)

#     z_none = pulp.LpVariable("z_none", cat="Binary")
#     z_ip = pulp.LpVariable("z_ip", cat="Binary")
#     z_route = pulp.LpVariable("z_route", cat="Binary")

#     x = {
#         c["host"]: pulp.LpVariable(f"x_{c['host']}", cat="Binary")
#         for c in ip_candidates
#     }

#     y = {
#         i: pulp.LpVariable(f"y_route_{i}", cat="Binary")
#         for i, _ in enumerate(route_candidates)
#     }

#     model += (
#         pulp.lpSum(c["score"] * x[c["host"]] for c in ip_candidates)
#         + pulp.lpSum(c["score"] * y[i] for i, c in enumerate(route_candidates))
#     )

#     model += z_none + z_ip + z_route == 1

#     for c in ip_candidates:
#         model += x[c["host"]] <= z_ip

#     for i, _ in enumerate(route_candidates):
#         model += y[i] <= z_route

#     model += pulp.lpSum(x.values()) <= K_IP * z_ip
#     model += pulp.lpSum(y.values()) <= K_ROUTE * z_route

#     model += (
#         pulp.lpSum(c["cost"] * x[c["host"]] for c in ip_candidates)
#         + pulp.lpSum(c["cost"] * y[i] for i, c in enumerate(route_candidates))
#         <= DEFENSE_BUDGET
#     )

#     model.solve(pulp.PULP_CBC_CMD(msg=False))

#     selected_hosts = [
#         h for h, var in x.items()
#         if pulp.value(var) is not None and pulp.value(var) > 0.5
#     ]

#     selected_routes = [
#         route_candidates[i]
#         for i, var in y.items()
#         if pulp.value(var) is not None and pulp.value(var) > 0.5
#     ]

#     if pulp.value(z_ip) and pulp.value(z_ip) > 0.5:
#         action = "ip_shuffle"
#     elif pulp.value(z_route) and pulp.value(z_route) > 0.5:
#         action = "route_mutation"
#     else:
#         action = "no_mtd"

#     return action, selected_hosts, selected_routes


# def solve_fallback(ip_candidates, route_candidates):
#     """
#     Simple fallback if PuLP is not installed.
#     Keeps the same logic for K_IP=1, K_ROUTE=1.
#     """

#     best_ip = None
#     for c in ip_candidates:
#         if c["cost"] <= DEFENSE_BUDGET:
#             if best_ip is None or c["score"] > best_ip["score"]:
#                 best_ip = c

#     best_route = None
#     for c in route_candidates:
#         if c["cost"] <= DEFENSE_BUDGET:
#             if best_route is None or c["score"] > best_route["score"]:
#                 best_route = c

#     ip_val = best_ip["score"] if best_ip else -math.inf
#     route_val = best_route["score"] if best_route else -math.inf

#     if ip_val <= 0 and route_val <= 0:
#         return "no_mtd", [], []

#     if ip_val >= route_val:
#         return "ip_shuffle", [best_ip["host"]], []

#     return "route_mutation", [], [best_route]


# def dpid_to_switch(device_id):
#     dev = str(device_id).strip()

#     if dev.startswith("of:"):
#         body = dev.replace("of:", "")

#         # Handles both:
#         # of:0000000000000004/1
#         # of:0000000000000004:1
#         body = body.split("/")[0]
#         body = body.split(":")[0]

#         return f"s{int(body, 16)}"

#     return dev


# def normalize_onos_link(link_str):
#     """
#     Converts ONOS link formats like:
#       of:0000000000000001/1->of:0000000000000002/2
#       of:0000000000000001:1->of:0000000000000002:2

#     into:
#       ('s1', 's2')
#     """
#     s = str(link_str).strip()

#     if "->" not in s:
#         return None

#     left, right = [x.strip() for x in s.split("->", 1)]

#     def endpoint_to_switch(endpoint):
#         return dpid_to_switch(endpoint)

#     return tuple(sorted([
#         endpoint_to_switch(left),
#         endpoint_to_switch(right)
#     ]))


# # =========================
# # MAIN DECISION FUNCTION
# # =========================

# def decide_ilp(
#     host_csv="host_stats_onos.csv",
#     link_csv="link_stats_onos.csv",
#     hop_csv="hop_list.csv",
#     ip_hist_csv="ip_history.csv",
#     route_hist_csv="route_history.csv",
#     obs_csv="observability.csv",
# ):
#     active_pairs, active_hosts = fetch_onos_active_pairs()

#     ip_candidates = build_ip_candidates(
#         host_csv=host_csv,
#         ip_hist_csv=ip_hist_csv,
#         obs_csv=obs_csv,
#         active_hosts=active_hosts,
#     )

#     route_candidates = build_route_candidates(
#         link_csv=link_csv,
#         hop_csv=hop_csv,
#         route_hist_csv=route_hist_csv,
#         active_pairs=active_pairs,
#     )

#     action, selected_hosts, selected_routes = solve_milp(
#         ip_candidates,
#         route_candidates,
#     )

#     details = {
#         "active_pairs": sorted(list(active_pairs)),
#         "active_hosts": sorted(list(active_hosts), key=lambda x: host_num(x) or 99999),
#         "ip_candidates": ip_candidates,
#         "route_candidates": route_candidates,
#         "selected_routes": selected_routes,
#     }

#     return action, selected_hosts, selected_routes, details



# # ////////////need logging /////////////////
# import csv, os
# from datetime import datetime

# DECISION_LOG = "decision_log.csv"

# def log_decision(action, hosts, routes, details, path=DECISION_LOG):
#     ipc = details.get("ip_candidates", [])
#     rtc = details.get("route_candidates", [])

#     sel_pairs = {(r["src"], r["dst"]) for r in (routes or [])}
#     used = (sum(c["cost"] for c in ipc if c["host"] in set(hosts or []))
#             + sum(c["cost"] for c in rtc if (c["src"], c["dst"]) in sel_pairs))

#     row = {
#         "timestamp": datetime.now().isoformat(timespec="seconds"),
#         "action": action,
#         "n_selected_hosts": len(hosts or []),
#         "selected_hosts": "|".join(hosts or []),
#         "n_selected_routes": len(routes or []),
#         "selected_routes": "|".join(
#             f"{r['src']}-{r['dst']}@opt{r.get('current_option','?')}" for r in (routes or [])
#         ),
#         "cost_used": round(used, 4),
#         "n_ip_cand": len(ipc),
#         "n_route_cand": len(rtc),
#         "top_ip": ipc[0]["host"] if ipc else "",
#         "top_ip_score": round(ipc[0]["score"], 4) if ipc else "",
#         "top_route": f"{rtc[0]['src']}-{rtc[0]['dst']}" if rtc else "",
#         "top_route_score": round(rtc[0]["score"], 4) if rtc else "",
#         "active_pairs": len(details.get("active_pairs", [])),
#     }

#     write_header = not os.path.exists(path)
#     with open(path, "a", newline="") as f:
#         w = csv.DictWriter(f, fieldnames=list(row.keys()))
#         if write_header:
#             w.writeheader()
#         w.writerow(row)
# # ////////////need logging /////////////////

# # =========================
# # RUN DIRECTLY
# # =========================

# if __name__ == "__main__":

#     while(True):
#         action, hosts, routes, details = decide_ilp()

#         # # ////// need logging //////////
#         # log_decision(action, hosts, routes, details)   # <-- add this
#         # # ////// need logging //////////

#         #detailed_logger///////////// #new
#         cycle_id = log_evaluation_snapshot(
#             action=action,
#             hosts=hosts,
#             routes=routes,
#             details=details,
#             host_csv="host_stats_onos.csv",
#             link_csv="link_stats_onos.csv",
#             link_capacity_mbps=LINK_CAPACITY_MBPS,
#             link_monitor_threshold_mbps=LINK_MONITOR_THRESHOLD_MBPS,
#         )

#         print("[EVAL LOG CYCLE]", cycle_id)
#         #detailed_logger///////////// #new


#         print("\nSelected action:", action)
#         print("Selected IP hosts:", hosts)

#         print("Selected route mutations:")
#         for r in routes:
#             print(
#                 f"  {r['src']} -> {r['dst']} | "
#                 f"current_option={r['current_option']} | "
#                 f"score={r['score']:.4f} | path={r['path']}"
#             )

#         # print("\nActive ONOS pairs:")
#         # for p in details["active_pairs"]:
#         #     print(" ", p)

#         print("\nTop IP candidates:")
#         for c in details["ip_candidates"][:10]:
#             print(
#                 f"  {c['host']} | score={c['score']:.4f} | "
#                 f"p_host={c['p_host']:.3f} | "
#                 f"ip_exp={c['ip_exposure']:.2f} | "
#                 f"grid={c['grid_priority']:.2f}"
#             )

#         print("\nTop route candidates:")
#         for c in details["route_candidates"][:10]:
#             print(
#                 f"  {c['src']}->{c['dst']} | current_option={c['current_option']} | "
#                 f"score={c['score']:.4f} | "
#                 f"route_exp={c['route_exposure']:.2f} | "
#                 f"link_usage={c['link_usage']:.2f}"
#             )

#         print(routes)
#         # new
#         if action == "route_mutation":
#             selected_pairs = [(r["src"], r["dst"]) for r in routes]
#             run_route_ilp(selected_pairs)

#             repeat_ip_history()             # repeats IP history

#         elif action == "ip_shuffle":
#             run_ip_ilp(hosts)

#             repeat_route_history()          # repeats route history

#         else:
#             print("[NO MTD] No mitigation executed.")
#         time.sleep(30)




# ////////////////////////////////////////////////////////////////////////////////////////


# proactive_new_scoring.py

import re
import math,time
import requests
import pandas as pd
import numpy as np
from requests.auth import HTTPBasicAuth
from proactive_new_logging import log_evaluation_snapshot

from mtd_utils import repeat_ip_history, repeat_route_history
import pulp
# new
from proactive_new_mitigation_route import run_route_ilp
from proactive_new_mitigation import run_ip_ilp

# =========================
# CONFIG
# =========================

ONOS_BASE_URL = "http://127.0.0.1:8181"
ONOS_USER = "onos"
ONOS_PASS = "rocks"

HOST_PPS_MONITOR_THRESHOLD = 100.0
HOST_RX_MBPS_THRESHOLD = 0.080
HOST_TX_MBPS_THRESHOLD = 0.091

LINK_CAPACITY_MBPS = 1.0
LINK_MONITOR_THRESHOLD_MBPS = 0.8

EXCLUDED_IP_HOSTS = {"h1"}

K_IP = 10
K_ROUTE = 10
DEFENSE_BUDGET = 0.50
 
E_IP = 0.70
# E_IP = 0.70 #Eip​=1−23.75/39.72​
# E_ROUTE = 0.70
# E_ROUTE = 0.60 # Eroute​=1−10.99/27.45 -- from graph​
E_ROUTE = 0.70 # Eroute​=1−10.99/27.45 -- from graph​



O_IP = 2830 / 3000
O_ROUTE = 0.05

LAMBDA_IP = 0.15

LAMBDA_HOP = 0.03 # hop effect

DEFAULT_GRID_PRIORITY = 0.0

# RECENT_WINDOW = 10 
RECENT_WINDOW = 15


IP_ACTIVE_ONLY = False
# new
# =========================
# STATIC MININET HOST DOMAIN
# =========================

MININET_MAC_PREFIX = "00:00:00:00:00:"
MININET_IP_PREFIX = "10.0.0."
MIN_HOST_ID = 1
MAX_HOST_ID = 40




# //////////////////////////////// Flow addition
FLOW_SUMMARY_CSV = "onos_host_summary_snapshot_v3.csv"


def load_flow_suspicion(flow_summary_csv=FLOW_SUMMARY_CSV):
    """
    Load host-level flow suspicion from ONOS host summary.

    Uses:
      Q_h     = short-flow ratio
      N_mac   = direct new sender MAC ratio

    D_h = 0.40 * Q_h + 0.60 * N_mac
    """

    try:
        f = pd.read_csv(flow_summary_csv)
    except Exception:
        return {}

    if f.empty:
        return {}

    required = [
        "dst_host",
        "unique_flow_count_towards_host",
        "short_lived_flow_count_towards_host",
        "unique_sender_mac_count",
    ]

    for c in required:
        if c not in f.columns:
            return {}

    f["host"] = f["dst_host"].apply(host_from_mac)
    f = f.dropna(subset=["host"])

    if f.empty:
        return {}

    for c in [
        "unique_flow_count_towards_host",
        "short_lived_flow_count_towards_host",
        "unique_sender_mac_count",
    ]:
        f[c] = pd.to_numeric(f[c], errors="coerce").fillna(0.0)

    flow_map = {}

    for _, row in f.iterrows():
        host = row["host"]

        total_flows = float(row["unique_flow_count_towards_host"])
        short_flows = float(row["short_lived_flow_count_towards_host"])

        unique_sender_macs = float(row["unique_sender_mac_count"])
        short_flow_ratio = short_flows / max(1.0, total_flows)
        # Direct unique sender MAC diversity.
        # Since the maximum possible Mininet sender domain is h1-h40,
        # normalize by MAX_HOST_ID.
        sender_mac_diversity = unique_sender_macs

        short_flow_ratio = min(max(short_flow_ratio, 0.0), 1.0)
        # new_mac_ratio = min(max(new_mac_ratio, 0.0), 1.0)


        flow_suspicion = (
            0.60 * short_flow_ratio
            + 0.40 * sender_mac_diversity
        )

        flow_suspicion = min(max(flow_suspicion, 0.0), 1.0)

        flow_map[host] = {
            "flow_suspicion": flow_suspicion,
            "short_flow_ratio": short_flow_ratio,
            "unique_sender_mac_count": unique_sender_macs,
            "sender_mac_diversity": sender_mac_diversity,
            "unique_flow_count": total_flows,
            "short_lived_flow_count": short_flows,
        }

    return flow_map

# //////////////////////////////// Flow addition



# =========================
# BASIC HELPERS
# =========================

def host_num(host):
    m = re.search(r"\d+", str(host))
    return int(m.group()) if m else None


# def host_from_ip(ip):
#     """
#     Example:
#         10.0.0.35/32 -> h35
#         10.0.0.35    -> h35
#     """
#     try:
#         ip = str(ip).split("/")[0]
#         return f"h{int(ip.split('.')[-1])}"
#     except Exception:
#         return None

# new
def host_from_ip(ip):
    """
    Only map internal Mininet IPs:
        10.0.0.1  -> h1
        10.0.0.40 -> h40

    Ignore external/OPAL/NAT IPs:
        192.168.*.* -> None
    """
    try:
        ip = str(ip).split("/")[0].strip()

        if not ip.startswith(MININET_IP_PREFIX):
            return None

        host_id = int(ip.split(".")[-1])

        if MIN_HOST_ID <= host_id <= MAX_HOST_ID:
            return f"h{host_id}"

        return None

    except Exception:
        return None

# def host_from_mac(mac):
#     """
#     Example:
#         00:00:00:00:00:23 -> h35
#         because hex 23 = decimal 35
#     """
#     try:
#         last = str(mac).split(":")[-1]
#         return f"h{int(last, 16)}"
#     except Exception:
#         return None

# new
def host_from_mac(mac):
    """
    Only map Mininet host MACs:
        00:00:00:00:00:01 -> h1
        00:00:00:00:00:28 -> h40

    Ignore external bridge / OPAL / physical NIC MACs.
    """
    try:
        mac = str(mac).lower().strip()

        if not mac.startswith(MININET_MAC_PREFIX):
            return None

        host_id = int(mac.split(":")[-1], 16)

        if MIN_HOST_ID <= host_id <= MAX_HOST_ID:
            return f"h{host_id}"

        return None

    except Exception:
        return None

def pair_key(a, b):
    return tuple(sorted((str(a), str(b)), key=lambda x: host_num(x) or 99999))


def safe_norm(s):
    s = pd.to_numeric(s, errors="coerce").fillna(0.0)
    mn, mx = s.min(), s.max()
    if mx == mn:
        return pd.Series([0.0] * len(s), index=s.index)
    return (s - mn) / (mx - mn)


def parse_history(v):
    if pd.isna(v):
        return []
    return [x.strip() for x in str(v).split(",") if x.strip()]


def latest_same_count(values):
    if not values:
        return 0
    last = values[-1]
    c = 0
    for v in reversed(values):
        if v == last:
            c += 1
        else:
            break
    return c


def path_links(path):
    links = []

    if pd.isna(path):
        return links

    for item in str(path).split(","):
        item = item.strip()

        if "->" in item:
            lk = normalize_onos_link(item)
            if lk:
                links.append(lk)

    return links

# =========================
# ONOS REST API
# =========================

# new
def fetch_onos_host_maps(
    base_url=ONOS_BASE_URL,
    user=ONOS_USER,
    password=ONOS_PASS,
    timeout=5,
):
    """
    Fetch ONOS hosts and build safe maps:
        ip_to_h  = only 10.0.0.X -> hX
        mac_to_h = only 00:00:00:00:00:XX -> hX

    External/OPAL/bridge addresses are ignored.
    """

    url = f"{base_url.rstrip('/')}/onos/v1/hosts"
    r = requests.get(url, auth=HTTPBasicAuth(user, password), timeout=timeout)
    r.raise_for_status()

    data = r.json()
    ip_to_h = {}
    mac_to_h = {}

    for item in data.get("hosts", []):
        mac = item.get("mac")
        ips = item.get("ipAddresses", [])

        # MAC is the safest identity for your Mininet hosts.
        h_from_mac = host_from_mac(mac)

        if h_from_mac is not None:
            mac_to_h[str(mac).lower()] = h_from_mac

        # Only add internal 10.0.0.X IPs.
        for ip in ips:
            ip_clean = str(ip).split("/")[0].strip()
            h_from_ip = host_from_ip(ip_clean)

            if h_from_ip is not None:
                ip_to_h[ip_clean] = h_from_ip

    return ip_to_h, mac_to_h

def criterion_value(criteria, names):
    """
    Extract values from ONOS flow selector criteria.
    Supports common ONOS fields:
        IPV4_SRC, IPV4_DST, ETH_SRC, ETH_DST
    """

    for c in criteria:
        ctype = c.get("type")

        if ctype not in names:
            continue

        for key in ["ip", "mac", "value"]:
            if key in c:
                return c[key]

    return None


def fetch_onos_active_pairs(
    base_url=ONOS_BASE_URL,
    user=ONOS_USER,
    password=ONOS_PASS,
    timeout=5,
):
    """
    Fetch active ONOS flows and extract active host pairs.

    Returns:
        active_pairs = {("h1", "h35"), ("h2", "h30")}
        active_hosts = {"h1", "h35", "h2", "h30"}

    Note:
        This works when ONOS flow selector has source/destination IP or MAC.
    """

    ip_to_h, mac_to_h = fetch_onos_host_maps(base_url, user, password, timeout)

    url = f"{base_url.rstrip('/')}/onos/v1/flows"
    r = requests.get(url, auth=HTTPBasicAuth(user, password), timeout=timeout)
    r.raise_for_status()

    data = r.json()

    active_pairs = set()
    active_hosts = set()

    for flow in data.get("flows", []):
        if flow.get("state") != "ADDED":
            continue

        criteria = flow.get("selector", {}).get("criteria", [])

        src_ip = criterion_value(criteria, {"IPV4_SRC", "IPV6_SRC"})
        dst_ip = criterion_value(criteria, {"IPV4_DST", "IPV6_DST"})

        src_mac = criterion_value(criteria, {"ETH_SRC"})
        dst_mac = criterion_value(criteria, {"ETH_DST"})

        src = None
        dst = None

        if src_ip:
            src = ip_to_h.get(str(src_ip).split("/")[0]) or host_from_ip(src_ip)

        if dst_ip:
            dst = ip_to_h.get(str(dst_ip).split("/")[0]) or host_from_ip(dst_ip)

        if src is None and src_mac:
            src = mac_to_h.get(str(src_mac).lower()) or host_from_mac(src_mac)

        if dst is None and dst_mac:
            dst = mac_to_h.get(str(dst_mac).lower()) or host_from_mac(dst_mac)

        # if src and dst and src != dst:
        #     p = pair_key(src, dst)
        #     active_pairs.add(p)
        #     active_hosts.update(p)

        if src and dst and src != dst:
            src_n = host_num(src)
            dst_n = host_num(dst)

            # Keep only real Mininet hosts h1-h40
            if src_n is None or dst_n is None:
                continue

            if not (MIN_HOST_ID <= src_n <= MAX_HOST_ID):
                continue

            if not (MIN_HOST_ID <= dst_n <= MAX_HOST_ID):
                continue

            p = pair_key(src, dst)
            active_pairs.add(p)
            active_hosts.update(p)

    return active_pairs, active_hosts


# =========================
# OBSERVABILITY / PMU RANK
# =========================

def load_grid_priority(obs_csv):
    """
    PMU/bus rank gives power-grid priority.

    Expected:
        PMU 39 or gen_bus 39 means host h39.

    Rank handling:
        rank 1 -> priority 1.0
        lower ranks -> smaller priority
        hosts not listed -> DEFAULT_GRID_PRIORITY
    """

    obs = pd.read_csv(obs_csv)

    cols = {c.lower(): c for c in obs.columns}

    host_col = None
    rank_col = None

    for key in ["pmu", "gen_bus", "bus", "host"]:
        if key in cols:
            host_col = cols[key]
            break

    for key in ["rank", "pmu_rank", "observability_rank"]:
        if key in cols:
            rank_col = cols[key]
            break

    if host_col is None or rank_col is None:
        return {}

    obs["host"] = obs[host_col].apply(lambda x: f"h{int(x)}" if pd.notna(x) else None)
    obs["rank"] = pd.to_numeric(obs[rank_col], errors="coerce")

    obs = obs.dropna(subset=["host", "rank"])

    if obs.empty:
        return {}

    max_rank = obs["rank"].max()
    min_rank = obs["rank"].min()

    if max_rank == min_rank:
        obs["grid_priority"] = 1.0
    else:
        obs["grid_priority"] = 1.0 - ((obs["rank"] - min_rank) / (max_rank - min_rank))

    return dict(zip(obs["host"], obs["grid_priority"]))


# =========================
# IP CANDIDATES
# =========================

# def build_ip_candidates(host_csv, ip_hist_csv, obs_csv, active_hosts=None,):
def build_ip_candidates(host_csv, ip_hist_csv, obs_csv, flow_summary_csv=FLOW_SUMMARY_CSV, active_hosts=None,): #//// Flow
    h = pd.read_csv(host_csv)

    h["host"] = h["host_mac"].apply(host_from_mac)
    h = h.dropna(subset=["host"])

    h = h[~h["host"].isin(EXCLUDED_IP_HOSTS)]

    if IP_ACTIVE_ONLY and active_hosts is not None:
        h = h[h["host"].isin(active_hosts)]

    if h.empty:
        return []

    # # Latest row per host
    # if "timestamp" in h.columns:
    #     h = h.sort_values("timestamp").groupby("host", as_index=False).tail(1)

    # Recent max-mean blended values per host || #new 
    if "timestamp" in h.columns:
        h = h.sort_values("timestamp").groupby("host", group_keys=False).tail(RECENT_WINDOW)

        agg = h.groupby("host", as_index=False).agg({
            "host_mac": "last",
            "rx_pps": ["max", "mean"],
            "tx_pps": ["max", "mean"],
            "rx_mbps": ["max", "mean"],
            "tx_mbps": ["max", "mean"],
        })

        agg.columns = [
            "host", "host_mac",
            "rx_pps_max", "rx_pps_mean",
            "tx_pps_max", "tx_pps_mean",
            "rx_mbps_max", "rx_mbps_mean",
            "tx_mbps_max", "tx_mbps_mean",
        ]

        for c in ["rx_pps", "tx_pps", "rx_mbps", "tx_mbps"]:
            agg[c] = 0.9 * agg[f"{c}_max"] + 0.1 * agg[f"{c}_mean"]

        h = agg[["host", "host_mac", "rx_pps", "tx_pps", "rx_mbps", "tx_mbps"]]

    for c in ["rx_pps", "tx_pps", "rx_mbps", "tx_mbps"]:
        h[c] = pd.to_numeric(h[c], errors="coerce").fillna(0.0)

    h["rx_pps_n"] = safe_norm(h["rx_pps"])
    # h["tx_pps_n"] = safe_norm(h["tx_pps"])
    h["rx_mbps_n"] = safe_norm(h["rx_mbps"])
    # h["tx_mbps_n"] = safe_norm(h["tx_mbps"])

    # imbalance indicator.
    eps = 1e-9
    h["rx_tx_imbalance"] = (
        (h["rx_pps"] - h["tx_pps"]).clip(lower=0)
        / (h["rx_pps"] + h["tx_pps"] + eps)
    ).clip(0, 1)

    # h["traffic_risk"] = (
    #     0.35 * h["tx_pps_n"]
    #     + 0.25 * h["rx_pps_n"]
    #     + 0.25 * h["tx_mbps_n"]
    #     + 0.15 * h["rx_mbps_n"]
    # )

    # so rx is the dos indicator.
    h["traffic_risk"] = (
        0.55 * h["rx_pps_n"]
    + 0.35 * h["rx_tx_imbalance"]
    + 0.10 * h["rx_mbps_n"]
    )

    h["monitor_score"] = np.maximum.reduce([
        # (h["tx_pps"] / HOST_PPS_MONITOR_THRESHOLD).clip(0, 1),
        (h["rx_pps"] / HOST_PPS_MONITOR_THRESHOLD).clip(0, 1),
        # (h["tx_mbps"] / HOST_TX_MBPS_THRESHOLD).clip(0, 1),
        (h["rx_mbps"] / HOST_RX_MBPS_THRESHOLD).clip(0, 1),
    ])

    ip_hist = pd.read_csv(ip_hist_csv)
    ip_hist["history_list"] = ip_hist["history"].apply(parse_history)
    ip_hist["ip_exposure"] = ip_hist["history_list"].apply(
        lambda x: latest_same_count(x) / max(1, len(x))
    )

    exposure_map = dict(zip(ip_hist["host"], ip_hist["ip_exposure"]))

    grid_map = load_grid_priority(obs_csv)

    flow_suspicion_map = load_flow_suspicion(flow_summary_csv) # ///// Flow

    candidates = []

    for _, row in h.iterrows():
        host = row["host"]

        ip_exposure = float(exposure_map.get(host, 0.0))
        grid_priority = float(grid_map.get(host, DEFAULT_GRID_PRIORITY))


        # p_host = (
        #     0.40 * float(row["traffic_risk"])
        #     + 0.35 * float(row["monitor_score"])
        #     + 0.25 * grid_priority
        # )

        # //////////////// Flow added into consideration
        flow_info = flow_suspicion_map.get(host, {})

        flow_suspicion = float(flow_info.get("flow_suspicion", 0.0))
        short_flow_ratio = float(flow_info.get("short_flow_ratio", 0.0))
        sender_mac_diversity = float(flow_info.get("sender_mac_diversity", 0.0))

        # // any retuning required on weights update here. //
        p_host = (
            0.35 * float(row["traffic_risk"])
            + 0.30 * float(row["monitor_score"])
            + 0.25 * grid_priority
            + 0.10 * flow_suspicion
        )
        # /////////////// Flow added into consideration

        benefit = p_host * ip_exposure * E_IP
        cost = LAMBDA_IP * O_IP
        score = benefit - cost

        candidates.append({
            "host": host,
            "score": score,
            "benefit": benefit,
            "cost": cost,
            "p_host": p_host,
            "traffic_risk": float(row["traffic_risk"]),
            "monitor_score": float(row["monitor_score"]),
            "ip_exposure": ip_exposure,
            "grid_priority": grid_priority,
            "rx_pps": float(row["rx_pps"]),
            "tx_pps": float(row["tx_pps"]),
            "rx_mbps": float(row["rx_mbps"]),
            "tx_mbps": float(row["tx_mbps"]),
            "flow_suspicion": flow_suspicion, # Flow info from here
            "short_flow_ratio": short_flow_ratio,
            "unique_sender_mac_count": float(flow_info.get("unique_sender_mac_count", 0.0)),
            "sender_mac_diversity": sender_mac_diversity,
            "unique_flow_count": float(flow_info.get("unique_flow_count", 0.0)),
            "short_lived_flow_count": float(flow_info.get("short_lived_flow_count", 0.0)),


        })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates


# =========================
# ROUTE CANDIDATES
# =========================

# def build_route_candidates(link_csv, hop_csv, route_hist_csv, active_pairs,):
def build_route_candidates(link_csv, hop_csv, route_hist_csv, active_pairs, obs_csv,): # added scoring

    if not active_pairs:
        return []

    grid_map = load_grid_priority(obs_csv) # new added scoring

    link = pd.read_csv(link_csv)

    # if "timestamp" in link.columns:
    #     link = link.sort_values("timestamp").groupby("link_id", as_index=False).tail(1)

    # Recent max-mean blended values per link || #new
    if "timestamp" in link.columns:
        link = link.sort_values("timestamp").groupby("link_id", group_keys=False).tail(RECENT_WINDOW)

        agg = link.groupby("link_id", as_index=False).agg({
            "rx_mbps": ["max", "mean"],
            "tx_mbps": ["max", "mean"],
        })

        agg.columns = [
            "link_id",
            "rx_mbps_max", "rx_mbps_mean",
            "tx_mbps_max", "tx_mbps_mean",
        ]

        for c in ["rx_mbps", "tx_mbps"]:
            agg[c] = 0.9 * agg[f"{c}_max"] + 0.1 * agg[f"{c}_mean"]

        link = agg[["link_id", "rx_mbps", "tx_mbps"]]

    link["rx_mbps"] = pd.to_numeric(link["rx_mbps"], errors="coerce").fillna(0.0)
    link["tx_mbps"] = pd.to_numeric(link["tx_mbps"], errors="coerce").fillna(0.0)
    link["link_mbps"] = link[["rx_mbps", "tx_mbps"]].max(axis=1)

    link["link_usage_norm"] = (link["link_mbps"] / LINK_CAPACITY_MBPS).clip(0, 1)
    link["link_monitor"] = (link["link_mbps"] / LINK_MONITOR_THRESHOLD_MBPS).clip(0, 1)
    
    link["norm_link"] = link["link_id"].apply(normalize_onos_link)

    usage_map = dict(zip(link["norm_link"], link["link_usage_norm"]))
    monitor_map = dict(zip(link["norm_link"], link["link_monitor"]))


    hop = pd.read_csv(
        hop_csv,
        header=None,
        names=["host1", "host2", "option", "hop_count", "src_mac", "dst_mac", "path"]
    )

    hop["option"] = pd.to_numeric(hop["option"], errors="coerce").fillna(0).astype(int) #hop as score
    hop["hop_count"] = pd.to_numeric(hop["hop_count"], errors="coerce").fillna(0.0) #hop as score

    hop["pair"] = hop.apply(lambda r: pair_key(r["host1"], r["host2"]), axis=1)
    hop = hop[hop["pair"].isin(active_pairs)].copy()

    if hop.empty:
        return []

    route_hist = pd.read_csv(route_hist_csv)
    route_hist["pair"] = route_hist.apply(lambda r: pair_key(r["host_a"], r["host_b"]), axis=1)
    route_hist["history_list"] = route_hist["history"].apply(parse_history)
    route_hist["route_exposure"] = route_hist["history_list"].apply(
        lambda x: latest_same_count(x) / max(1, len(x))
    )

    exposure_map = dict(zip(route_hist["pair"], route_hist["route_exposure"]))

    # to handle it not considering opt 0 blindly.
    route_hist["current_option"] = route_hist["history_list"].apply(
        lambda x: int(x[-1]) if x else 0
    )

    current_option_map = dict(zip(route_hist["pair"], route_hist["current_option"]))
    # to handle it not considering opt 0 blindly.

    candidates = []

    grouped = hop.groupby("pair")

    # to handle it not considering opt 0 blindly.    
    # for pair, g in hop.groupby("pair"):
    #     g0 = g[g["option"].astype(int) == 0]

    #     if g0.empty:
    #         continue

    #     r = g0.iloc[0]
    #     links = path_links(r["path"])
    # to handle it not considering opt 0 blindly.

    for pair, g in hop.groupby("pair"):
        current_option = int(current_option_map.get(pair, 0))

        g_current = g[g["option"].astype(int) == current_option]

        if g_current.empty:
            continue

        r = g_current.iloc[0]
        links = path_links(r["path"])


        # /// hop score ///
        current_hop_count = float(r["hop_count"])
        min_hop = float(g["hop_count"].min())
        max_hop = float(g["hop_count"].max())

        hop_penalty = (
            (current_hop_count - min_hop) / (max_hop - min_hop)
            if max_hop > min_hop else 0.0
        )

        # /// hop score ///


        link_usage = max([usage_map.get(x, 0.0) for x in links], default=0.0)
        link_monitor = max([monitor_map.get(x, 0.0) for x in links], default=0.0)

        route_exposure = float(exposure_map.get(pair, 0.0))


        # Observability of the active route endpoint pair
        route_grid_priority = max(
            float(grid_map.get(pair[0], DEFAULT_GRID_PRIORITY)),
            float(grid_map.get(pair[1], DEFAULT_GRID_PRIORITY)),
        )


        # p_route = (
        #     0.45 * link_usage
        #     + 0.30 * link_monitor
        #     + 0.25 * route_exposure
        # )

        # p_route = (
        #     0.60 * link_usage
        #     + 0.40 * link_monitor
        # )

        # new added scoring
        p_route = (
            0.55 * link_usage
            + 0.35 * link_monitor
            + 0.10 * route_grid_priority
        )

        benefit = p_route * route_exposure * E_ROUTE
        # cost = O_ROUTE + 0.10 * link_usage
        cost = O_ROUTE
        hop_cost = LAMBDA_HOP * hop_penalty

        score = benefit - cost - hop_cost

        candidates.append({
            "pair": pair,
            "src": pair[0],
            "dst": pair[1],
            "current_option": current_option,
            "score": score,
            "benefit": benefit,
            "cost": cost,
            "p_route": p_route,
            "route_exposure": route_exposure,
            "link_usage": link_usage,
            "link_monitor": link_monitor,
            "current_hop_count": current_hop_count, #hop score
            "hop_penalty": hop_penalty, # hop score
            "hop_cost": hop_cost, # hop score
            "route_grid_priority": route_grid_priority, # hop score
            "path": r["path"],
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates


# =========================
# MILP SOLVER
# =========================

def solve_milp(ip_candidates, route_candidates):
    """
    Binary MILP:

    maximize:
        sum IP scores + sum route scores

    subject to:
        z_none + z_ip + z_route = 1
        x_h <= z_ip
        y_f <= z_route
        sum x_h <= K_IP z_ip
        sum y_f <= K_ROUTE z_route
        total defense cost <= DEFENSE_BUDGET
    """

    if pulp is None:
        return solve_fallback(ip_candidates, route_candidates)

    model = pulp.LpProblem("Proactive_MTD_Selection", pulp.LpMaximize)

    z_none = pulp.LpVariable("z_none", cat="Binary")
    z_ip = pulp.LpVariable("z_ip", cat="Binary")
    z_route = pulp.LpVariable("z_route", cat="Binary")

    x = {
        c["host"]: pulp.LpVariable(f"x_{c['host']}", cat="Binary")
        for c in ip_candidates
    }

    y = {
        i: pulp.LpVariable(f"y_route_{i}", cat="Binary")
        for i, _ in enumerate(route_candidates)
    }

    model += (
        pulp.lpSum(c["score"] * x[c["host"]] for c in ip_candidates)
        + pulp.lpSum(c["score"] * y[i] for i, c in enumerate(route_candidates))
    )

    # model += z_none + z_ip + z_route == 1 #new select either
    model += z_ip + z_route == 1

    for c in ip_candidates:
        model += x[c["host"]] <= z_ip

    for i, _ in enumerate(route_candidates):
        model += y[i] <= z_route

    model += pulp.lpSum(x.values()) <= K_IP * z_ip
    model += pulp.lpSum(y.values()) <= K_ROUTE * z_route

    # >>> add these two lines here < --- # new select either 
    model += pulp.lpSum(x.values()) >= z_ip
    model += pulp.lpSum(y.values()) >= z_route

    model += (
        pulp.lpSum(c["cost"] * x[c["host"]] for c in ip_candidates)
        + pulp.lpSum(c["cost"] * y[i] for i, c in enumerate(route_candidates))
        <= DEFENSE_BUDGET
    )

    model.solve(pulp.PULP_CBC_CMD(msg=False))

    selected_hosts = [
        h for h, var in x.items()
        if pulp.value(var) is not None and pulp.value(var) > 0.5
    ]

    selected_routes = [
        route_candidates[i]
        for i, var in y.items()
        if pulp.value(var) is not None and pulp.value(var) > 0.5
    ]

    if pulp.value(z_ip) and pulp.value(z_ip) > 0.5:
        action = "ip_shuffle"
    elif pulp.value(z_route) and pulp.value(z_route) > 0.5:
        action = "route_mutation"
    else:
        action = "no_mtd"

    return action, selected_hosts, selected_routes


def solve_fallback(ip_candidates, route_candidates):
    """
    Simple fallback if PuLP is not installed.
    Keeps the same logic for K_IP=1, K_ROUTE=1.
    """

    best_ip = None
    for c in ip_candidates:
        if c["cost"] <= DEFENSE_BUDGET:
            if best_ip is None or c["score"] > best_ip["score"]:
                best_ip = c

    best_route = None
    for c in route_candidates:
        if c["cost"] <= DEFENSE_BUDGET:
            if best_route is None or c["score"] > best_route["score"]:
                best_route = c

    ip_val = best_ip["score"] if best_ip else -math.inf
    route_val = best_route["score"] if best_route else -math.inf

    if ip_val <= 0 and route_val <= 0:
        return "no_mtd", [], []

    if ip_val >= route_val:
        return "ip_shuffle", [best_ip["host"]], []

    return "route_mutation", [], [best_route]


def dpid_to_switch(device_id):
    dev = str(device_id).strip()

    if dev.startswith("of:"):
        body = dev.replace("of:", "")

        # Handles both:
        # of:0000000000000004/1
        # of:0000000000000004:1
        body = body.split("/")[0]
        body = body.split(":")[0]

        return f"s{int(body, 16)}"

    return dev


def normalize_onos_link(link_str):
    """
    Converts ONOS link formats like:
      of:0000000000000001/1->of:0000000000000002/2
      of:0000000000000001:1->of:0000000000000002:2

    into:
      ('s1', 's2')
    """
    s = str(link_str).strip()

    if "->" not in s:
        return None

    left, right = [x.strip() for x in s.split("->", 1)]

    def endpoint_to_switch(endpoint):
        return dpid_to_switch(endpoint)

    return tuple(sorted([
        endpoint_to_switch(left),
        endpoint_to_switch(right)
    ]))


# =========================
# MAIN DECISION FUNCTION
# =========================

def decide_ilp(
    host_csv="host_stats_onos.csv",
    link_csv="link_stats_onos.csv",
    hop_csv="hop_list.csv",
    ip_hist_csv="ip_history.csv",
    route_hist_csv="route_history.csv",
    obs_csv="observability.csv",
):
    active_pairs, active_hosts = fetch_onos_active_pairs()

    ip_candidates = build_ip_candidates(
        host_csv=host_csv,
        ip_hist_csv=ip_hist_csv,
        obs_csv=obs_csv,
        active_hosts=active_hosts,
    )

    # route_candidates = build_route_candidates(
    #     link_csv=link_csv,
    #     hop_csv=hop_csv,
    #     route_hist_csv=route_hist_csv,
    #     active_pairs=active_pairs,
    # )

    # new added score
    route_candidates = build_route_candidates(
        link_csv=link_csv,
        hop_csv=hop_csv,
        route_hist_csv=route_hist_csv,
        active_pairs=active_pairs,
        obs_csv=obs_csv,
    )


    action, selected_hosts, selected_routes = solve_milp(
        ip_candidates,
        route_candidates,
    )

    details = {
        "active_pairs": sorted(list(active_pairs)),
        "active_hosts": sorted(list(active_hosts), key=lambda x: host_num(x) or 99999),
        "ip_candidates": ip_candidates,
        "route_candidates": route_candidates,
        "selected_routes": selected_routes,
    }

    return action, selected_hosts, selected_routes, details



# ////////////need logging /////////////////
import csv, os
from datetime import datetime

DECISION_LOG = "decision_log.csv"

def log_decision(action, hosts, routes, details, path=DECISION_LOG):
    ipc = details.get("ip_candidates", [])
    rtc = details.get("route_candidates", [])

    sel_pairs = {(r["src"], r["dst"]) for r in (routes or [])}
    used = (sum(c["cost"] for c in ipc if c["host"] in set(hosts or []))
            + sum(c["cost"] for c in rtc if (c["src"], c["dst"]) in sel_pairs))

    row = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "action": action,
        "n_selected_hosts": len(hosts or []),
        "selected_hosts": "|".join(hosts or []),
        "n_selected_routes": len(routes or []),
        "selected_routes": "|".join(
            f"{r['src']}-{r['dst']}@opt{r.get('current_option','?')}" for r in (routes or [])
        ),
        "cost_used": round(used, 4),
        "n_ip_cand": len(ipc),
        "n_route_cand": len(rtc),
        "top_ip": ipc[0]["host"] if ipc else "",
        "top_ip_score": round(ipc[0]["score"], 4) if ipc else "",
        "top_route": f"{rtc[0]['src']}-{rtc[0]['dst']}" if rtc else "",
        "top_route_score": round(rtc[0]["score"], 4) if rtc else "",
        "active_pairs": len(details.get("active_pairs", [])),
    }

    write_header = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if write_header:
            w.writeheader()
        w.writerow(row)
# ////////////need logging /////////////////

# =========================
# RUN DIRECTLY
# =========================

if __name__ == "__main__":

    while(True):
        action, hosts, routes, details = decide_ilp()

        # # ////// need logging //////////
        # log_decision(action, hosts, routes, details)   # <-- add this
        # # ////// need logging //////////

        #detailed_logger///////////// #new
        cycle_id = log_evaluation_snapshot(
            action=action,
            hosts=hosts,
            routes=routes,
            details=details,
            host_csv="host_stats_onos.csv",
            link_csv="link_stats_onos.csv",
            link_capacity_mbps=LINK_CAPACITY_MBPS,
            link_monitor_threshold_mbps=LINK_MONITOR_THRESHOLD_MBPS,
        )

        print("[EVAL LOG CYCLE]", cycle_id)
        #detailed_logger///////////// #new


        print("\nSelected action:", action)
        print("Selected IP hosts:", hosts)

        print("Selected route mutations:")
        for r in routes:
            print(
                f"  {r['src']} -> {r['dst']} | "
                f"current_option={r['current_option']} | "
                f"score={r['score']:.4f} | path={r['path']}"
            )

        # print("\nActive ONOS pairs:")
        # for p in details["active_pairs"]:
        #     print(" ", p)

        print("\nTop IP candidates:")
        for c in details["ip_candidates"][:10]:
            print(
                f"  {c['host']} | score={c['score']:.4f} | "
                f"p_host={c['p_host']:.3f} | "
                f"ip_exp={c['ip_exposure']:.2f} | "
                f"grid={c['grid_priority']:.2f}"
            )

        print("\nTop route candidates:")
        for c in details["route_candidates"][:10]:
            print(
                f"  {c['src']}->{c['dst']} | current_option={c['current_option']} | "
                f"score={c['score']:.4f} | "
                f"route_exp={c['route_exposure']:.2f} | "
                f"link_usage={c['link_usage']:.2f}"
            )

        print(routes)
        # new
        if action == "route_mutation":
            selected_pairs = [(r["src"], r["dst"]) for r in routes]
            run_route_ilp(selected_pairs)

            repeat_ip_history()             # repeats IP history

        elif action == "ip_shuffle":
            run_ip_ilp(hosts)

            repeat_route_history()          # repeats route history

        else:
            print("[NO MTD] No mitigation executed.")
        time.sleep(30)