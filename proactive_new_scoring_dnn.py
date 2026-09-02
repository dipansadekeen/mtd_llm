

# # ////////////////////////////////////////////////////////////////////////////////////////


# # proactive_new_scoring.py

# import re
# import os, time
# import requests
# import pandas as pd
# import numpy as np
# from requests.auth import HTTPBasicAuth
# from proactive_new_logging import log_evaluation_snapshot

# from mtd_utils import repeat_ip_history, repeat_route_history
# # DNN decision model
# from mtd_model_decision import MTDModel
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

# MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mtd_three_models")
# MTD_MODEL = MTDModel(MODEL_DIR)
# # DEFENSE_BUDGET = 1.0


# # E_IP = 0.70
# # # E_IP = 0.70 #Eip​=1−23.75/39.72​
# # # E_ROUTE = 0.60 # Eroute​=1−10.99/27.45 -- from graph​
# # E_ROUTE = 0.70 # Eroute​=1−10.99/27.45 -- from graph​

# E_IP=0.40
# E_ROUTE=0.60


# # O_IP = 2830 / 3000
# O_IP = 3350 / 4000

# O_ROUTE = 0.05

# LAMBDA_IP = 0.15

# LAMBDA_HOP = 0.03 # hop effect

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




# # //////////////////////////////// Flow addition
# FLOW_SUMMARY_CSV = "onos_host_summary_snapshot_v3.csv"
# ROUTE_OVERLAP_CSV = "onos_active_flow_route_overlap_v3.csv" # new


# def load_flow_suspicion(flow_summary_csv=FLOW_SUMMARY_CSV):
#     """
#     Load host-level flow suspicion from ONOS host summary.

#     Uses:
#       Q_h     = short-flow ratio
#       N_mac   = direct new sender MAC ratio

#     D_h = 0.40 * Q_h + 0.60 * N_mac
#     """

#     try:
#         f = pd.read_csv(flow_summary_csv)
#     except Exception:
#         return {}

#     if f.empty:
#         return {}

#     required = [
#         "dst_host",
#         "unique_flow_count_towards_host",
#         "short_lived_flow_count_towards_host",
#         "unique_sender_mac_count",
#     ]

#     for c in required:
#         if c not in f.columns:
#             return {}

#     f["host"] = f["dst_host"].apply(host_from_mac)
#     f = f.dropna(subset=["host"])

#     if f.empty:
#         return {}

#     for c in [
#         "unique_flow_count_towards_host",
#         "short_lived_flow_count_towards_host",
#         "unique_sender_mac_count",
#     ]:
#         f[c] = pd.to_numeric(f[c], errors="coerce").fillna(0.0)

#     flow_map = {}

#     # /////////new
#     FLOW_CONCERN_START = 3       # 1-3 flows toward a host = usually normal
#     FLOW_CONCERN_FULL = 20       # 20+ flows toward a host = strong concern

#     SENDER_CONCERN_START = 2     # 1-2 sender MACs = not concerning
#     SENDER_CONCERN_FULL = 10     # 10+ sender MACs = strong concern

#     for _, row in f.iterrows():
#         host = row["host"]

#         total_flows = float(row["unique_flow_count_towards_host"])
#         short_flows = float(row["short_lived_flow_count_towards_host"])
#         unique_sender_macs = float(row["unique_sender_mac_count"])

#         # Short-flow ratio only among flows toward this host
#         short_flow_ratio = short_flows / max(1.0, total_flows)
#         short_flow_ratio = min(max(short_flow_ratio, 0.0), 1.0)

#         # Sender pressure:
#         # 1 or 2 sender MACs should not be suspicious by itself
#         sender_mac_diversity = (
#             (unique_sender_macs - SENDER_CONCERN_START)
#             / max(1.0, SENDER_CONCERN_FULL - SENDER_CONCERN_START)
#         )
#         sender_mac_diversity = min(max(sender_mac_diversity, 0.0), 1.0)

#         # Flow volume gate:
#         # 1 or 2 flows should not create suspicion by itself
#         flow_volume_gate = (
#             (total_flows - FLOW_CONCERN_START)
#             / max(1.0, FLOW_CONCERN_FULL - FLOW_CONCERN_START)
#         )
#         flow_volume_gate = min(max(flow_volume_gate, 0.0), 1.0)

#         raw_flow_suspicion = (
#             0.70 * short_flow_ratio
#             + 0.30 * sender_mac_diversity
#         )

#         flow_suspicion = flow_volume_gate * raw_flow_suspicion
#         flow_suspicion = min(max(flow_suspicion, 0.0), 1.0)

#         flow_map[host] = {
#             "flow_suspicion": flow_suspicion,
#             "short_flow_ratio": short_flow_ratio,
#             "unique_sender_mac_count": unique_sender_macs,
#             "sender_mac_diversity": sender_mac_diversity,
#             "unique_flow_count": total_flows,
#             "short_lived_flow_count": short_flows,
#         }

#     return flow_map
#     # /////////new


# def load_route_overlap(csv=ROUTE_OVERLAP_CSV): # new route flow
#     try:
#         df = pd.read_csv(csv)
#     except Exception:
#         return {}

#     if df.empty or "flow" not in df.columns or "max_overlap_on_any_link" not in df.columns:
#         return {}

#     total = max(len(df), 1)
#     out = {}

#     for _, r in df.iterrows():
#         flow = str(r["flow"]).strip()

#         if "->" not in flow:
#             continue

#         a, b = [x.strip() for x in flow.split("->", 1)]
#         pair = pair_key(a, b)

#         max_overlap = float(r["max_overlap_on_any_link"])
#         pressure = min(max_overlap / total, 1.0)

#         out[pair] = {
#             "max_flow_overlap": max_overlap,
#             "overlap_pressure": pressure,
#         }

#     return out

# # //////////////////////////////// Flow addition



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

# # grid reading timely
# def load_grid_priority(obs_csv, obs_time_seconds=None):
#     obs = pd.read_csv(obs_csv)

#     cols = {c.lower(): c for c in obs.columns}

#     host_col = None
#     rank_col = None
#     time_col = None

#     for key in ["pmu", "gen_bus", "bus", "host"]:
#         if key in cols:
#             host_col = cols[key]
#             break

#     for key in ["rank", "pmu_rank", "observability_rank"]:
#         if key in cols:
#             rank_col = cols[key]
#             break

#     for key in ["time_seconds", "timestamp", "time"]:
#         if key in cols:
#             time_col = cols[key]
#             break

#     if host_col is None or rank_col is None:
#         return {}

#     # Pick the observability phase for this MTD cycle
#     if obs_time_seconds is not None and time_col is not None:
#         obs[time_col] = pd.to_numeric(obs[time_col], errors="coerce")
#         obs = obs.dropna(subset=[time_col])

#         available_times = sorted(obs[time_col].unique())

#         if available_times:
#             # choose exact/next available phase
#             chosen_time = None
#             for t in available_times:
#                 if t >= obs_time_seconds:
#                     chosen_time = t
#                     break

#             # if requested time exceeds file, use last available
#             if chosen_time is None:
#                 chosen_time = available_times[-1]

#             obs = obs[obs[time_col] == chosen_time]

#             print(f"[OBS] using observability phase time_seconds={chosen_time}")

#     obs["host"] = obs[host_col].apply(
#         lambda x: f"h{int(x)}" if pd.notna(x) else None
#     )
#     obs["rank"] = pd.to_numeric(obs[rank_col], errors="coerce")

#     obs = obs.dropna(subset=["host", "rank"])

#     if obs.empty:
#         return {}

#     max_rank = obs["rank"].max()
#     min_rank = obs["rank"].min()

#     if max_rank == min_rank:
#         obs["grid_priority"] = 1.0
#     else:
#         obs["grid_priority"] = 1.0 - (
#             (obs["rank"] - min_rank) / (max_rank - min_rank)
#         )

#     return dict(zip(obs["host"], obs["grid_priority"]))

# # =========================
# # IP CANDIDATES
# # =========================

# # def build_ip_candidates(host_csv, ip_hist_csv, obs_csv, active_hosts=None,):
# # def build_ip_candidates(host_csv, ip_hist_csv, obs_csv, flow_summary_csv=FLOW_SUMMARY_CSV, active_hosts=None,): #//// Flow
# def build_ip_candidates(host_csv,ip_hist_csv,obs_csv,flow_summary_csv=FLOW_SUMMARY_CSV, active_hosts=None,obs_time_seconds=None,): #added grid
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

#         h = agg.copy()

#     for c in ["rx_pps", "tx_pps", "rx_mbps", "tx_mbps"]:
#         h[c] = pd.to_numeric(h[c], errors="coerce").fillna(0.0)

#     h["rx_pps_n"] = safe_norm(h["rx_pps"])
#     # h["tx_pps_n"] = safe_norm(h["tx_pps"])
#     h["rx_mbps_n"] = safe_norm(h["rx_mbps"])
#     # h["tx_mbps_n"] = safe_norm(h["tx_mbps"])

#     # imbalance indicator.
#     eps = 1e-9
#     h["rx_tx_imbalance"] = (
#         (h["rx_pps"] - h["tx_pps"]).clip(lower=0)
#         / (h["rx_pps"] + h["tx_pps"] + eps)
#     ).clip(0, 1)

#     # h["traffic_risk"] = (
#     #     0.35 * h["tx_pps_n"]
#     #     + 0.25 * h["rx_pps_n"]
#     #     + 0.25 * h["tx_mbps_n"]
#     #     + 0.15 * h["rx_mbps_n"]
#     # )

#     # so rx is the dos indicator.
#     h["traffic_risk"] = (
#         0.55 * h["rx_pps_n"]
#     + 0.35 * h["rx_tx_imbalance"]
#     + 0.10 * h["rx_mbps_n"]
#     )

#     h["monitor_score"] = np.maximum.reduce([
#         # (h["tx_pps"] / HOST_PPS_MONITOR_THRESHOLD).clip(0, 1),
#         (h["rx_pps"] / HOST_PPS_MONITOR_THRESHOLD).clip(0, 1),
#         # (h["tx_mbps"] / HOST_TX_MBPS_THRESHOLD).clip(0, 1),
#         (h["rx_mbps"] / HOST_RX_MBPS_THRESHOLD).clip(0, 1),
#     ])

#     ip_hist = pd.read_csv(ip_hist_csv)
#     ip_hist["history_list"] = ip_hist["history"].apply(parse_history)
#     ip_hist["ip_exposure"] = ip_hist["history_list"].apply(
#         lambda x: latest_same_count(x) / max(1, len(x))
#     )

#     exposure_map = dict(zip(ip_hist["host"], ip_hist["ip_exposure"]))

#     # grid_map = load_grid_priority(obs_csv)
#     grid_map = load_grid_priority(obs_csv, obs_time_seconds=obs_time_seconds) # timely grid

#     flow_suspicion_map = load_flow_suspicion(flow_summary_csv) # ///// Flow

#     candidates = []

#     for _, row in h.iterrows():
#         host = row["host"]

#         ip_exposure = float(exposure_map.get(host, 0.0))
#         grid_priority = float(grid_map.get(host, DEFAULT_GRID_PRIORITY))


#         # p_host = (
#         #     0.40 * float(row["traffic_risk"])
#         #     + 0.35 * float(row["monitor_score"])
#         #     + 0.25 * grid_priority
#         # )

#         # //////////////// Flow added into consideration
#         flow_info = flow_suspicion_map.get(host, {})

#         flow_suspicion = float(flow_info.get("flow_suspicion", 0.0))
#         short_flow_ratio = float(flow_info.get("short_flow_ratio", 0.0))
#         sender_mac_diversity = float(flow_info.get("sender_mac_diversity", 0.0))

#         # // any retuning required on weights update here. //
#         p_host = (
#             0.35 * float(row["traffic_risk"])
#             + 0.30 * float(row["monitor_score"])
#             + 0.25 * grid_priority
#             + 0.10 * flow_suspicion
#         )
#         # /////////////// Flow added into consideration

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
#             "rx_pps_max": float(row.get("rx_pps_max", row["rx_pps"])),
#             "rx_pps_mean": float(row.get("rx_pps_mean", row["rx_pps"])),
#             "tx_pps_max": float(row.get("tx_pps_max", row["tx_pps"])),
#             "tx_pps_mean": float(row.get("tx_pps_mean", row["tx_pps"])),
#             "rx_mbps_max": float(row.get("rx_mbps_max", row["rx_mbps"])),
#             "rx_mbps_mean": float(row.get("rx_mbps_mean", row["rx_mbps"])),
#             "tx_mbps_max": float(row.get("tx_mbps_max", row["tx_mbps"])),
#             "tx_mbps_mean": float(row.get("tx_mbps_mean", row["tx_mbps"])),
#             "flow_suspicion": flow_suspicion, # Flow info from here
#             "short_flow_ratio": short_flow_ratio,
#             "unique_sender_mac_count": float(flow_info.get("unique_sender_mac_count", 0.0)),
#             "sender_mac_diversity": sender_mac_diversity,
#             "unique_flow_count": float(flow_info.get("unique_flow_count", 0.0)),
#             "short_lived_flow_count": float(flow_info.get("short_lived_flow_count", 0.0)),


#         })

#     candidates.sort(key=lambda x: x["score"], reverse=True)
#     return candidates


# # =========================
# # ROUTE CANDIDATES
# # =========================

# # def build_route_candidates(link_csv, hop_csv, route_hist_csv, active_pairs,):
# # def build_route_candidates(link_csv, hop_csv, route_hist_csv, active_pairs, obs_csv,): # added scoring
# def build_route_candidates(link_csv, hop_csv, route_hist_csv, active_pairs, obs_csv, obs_time_seconds=None,): # for grid time

#     if not active_pairs:
#         return []

#     # grid_map = load_grid_priority(obs_csv) # new added scoring
#     grid_map = load_grid_priority(obs_csv, obs_time_seconds=obs_time_seconds) # grid time update

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

#     hop["option"] = pd.to_numeric(hop["option"], errors="coerce").fillna(0).astype(int) #hop as score
#     hop["hop_count"] = pd.to_numeric(hop["hop_count"], errors="coerce").fillna(0.0) #hop as score

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

#     overlap_map = load_route_overlap()

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


#         # ////// flow for route
#         ov = overlap_map.get(pair, {})
#         max_flow_overlap = ov.get("max_flow_overlap", 0.0)
#         overlap_pressure = ov.get("overlap_pressure", 0.0)
#         # ////// flow for route


#         if g_current.empty:
#             continue

#         r = g_current.iloc[0]
#         links = path_links(r["path"])


#         # /// hop score ///
#         current_hop_count = float(r["hop_count"])
#         min_hop = float(g["hop_count"].min())
#         max_hop = float(g["hop_count"].max())

#         hop_penalty = (
#             (current_hop_count - min_hop) / (max_hop - min_hop)
#             if max_hop > min_hop else 0.0
#         )

#         # /// hop score ///


#         link_usage = max([usage_map.get(x, 0.0) for x in links], default=0.0)
#         link_monitor = max([monitor_map.get(x, 0.0) for x in links], default=0.0)

#         route_exposure = float(exposure_map.get(pair, 0.0))


#         # Observability of the active route endpoint pair
#         route_grid_priority = max(
#             float(grid_map.get(pair[0], DEFAULT_GRID_PRIORITY)),
#             float(grid_map.get(pair[1], DEFAULT_GRID_PRIORITY)),
#         )

#         p_route = (
#             # 0.45 * link_usage
#             0.40 * link_usage
#             + 0.30 * link_monitor
#             + 0.10 * route_grid_priority
#             + 0.20 * overlap_pressure
#         )

#         benefit = p_route * route_exposure * E_ROUTE
#         # cost = O_ROUTE + 0.10 * link_usage
#         cost = O_ROUTE
#         # hop_cost = LAMBDA_HOP * hop_penalty
#         hop_cost = .0001

#         score = benefit - cost - hop_cost

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
#             "current_hop_count": current_hop_count, #hop score
#             "hop_penalty": hop_penalty, # hop score
#             "hop_cost": hop_cost, # hop score
#             "route_grid_priority": route_grid_priority, # hop score
#             "path": r["path"],
#             "max_flow_overlap": max_flow_overlap, # flow into route
#             "overlap_pressure": overlap_pressure, # flow into route
#         })

#     candidates.sort(key=lambda x: x["score"], reverse=True)
#     return candidates


# # =========================
# # DNN DECISION
# # =========================
# # The former decision MILP is replaced by:
# #   Deep Sets -> operation -> Host/Route DNN -> threshold + Top-K
# # run_ip_ilp() and run_route_ilp() are still used later for execution.


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

# # for grid
# def decide_ilp(
#     host_csv="host_stats_onos.csv",
#     link_csv="link_stats_onos.csv",
#     hop_csv="hop_list.csv",
#     ip_hist_csv="ip_history.csv",
#     route_hist_csv="route_history.csv",
#     obs_csv="observability.csv",
#     obs_time_seconds=None,
# ):
#     active_pairs, active_hosts = fetch_onos_active_pairs()
#     # for grid timing
#     ip_candidates = build_ip_candidates(
#         host_csv=host_csv,
#         ip_hist_csv=ip_hist_csv,
#         obs_csv=obs_csv,
#         active_hosts=active_hosts,
#         obs_time_seconds=obs_time_seconds,
#     )

#     # grid timing
#     route_candidates = build_route_candidates(
#         link_csv=link_csv,
#         hop_csv=hop_csv,
#         route_hist_csv=route_hist_csv,
#         active_pairs=active_pairs,
#         obs_csv=obs_csv,
#         obs_time_seconds=obs_time_seconds,
#     )


#     action, selected_hosts, selected_routes, decision_solver_time_s, rm_conf = MTD_MODEL.decide(
#         ip_candidates,
#         route_candidates,
#         k_ip=K_IP,
#         k_route=K_ROUTE,
#     )

#     print(
#         f"[DNN DECISION] action={action} | "
#         f"RM_conf={rm_conf:.4f} | time={decision_solver_time_s:.6f}s"
#     )

#     details = {
#         "active_pairs": sorted(list(active_pairs)),
#         "active_hosts": sorted(list(active_hosts), key=lambda x: host_num(x) or 99999),
#         "ip_candidates": ip_candidates,
#         "route_candidates": route_candidates,
#         "selected_routes": selected_routes,
#         "decision_solver_time_s": decision_solver_time_s,  # kept for logger compatibility
#         "operation_rm_confidence": rm_conf,
#     }

#     return action, selected_hosts, selected_routes, details



# # ////////////need logging /////////////////
# import csv
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
#     # grid time
#     cycle_idx = 0
#     MTD_INTERVAL_SECONDS = 30
#     # //////


#     while(True):
#         # action, hosts, routes, details = decide_ilp() #commented for grid time

#         # grid time
#         obs_time_seconds = cycle_idx * MTD_INTERVAL_SECONDS

#         action, hosts, routes, details = decide_ilp(
#             obs_time_seconds=obs_time_seconds
#         )
#         # grid time



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

#         # old
#         # print("\nTop IP candidates:")
#         # for c in details["ip_candidates"][:10]:
#         #     print(
#         #         f"  {c['host']} | dnn={c.get('candidate_confidence', 0):.4f} | "
#         #         f"score={c['score']:.4f} | p_host={c['p_host']:.3f} | "
#         #         f"ip_exp={c['ip_exposure']:.2f} | "
#         #         f"grid={c['grid_priority']:.2f}"
#         #     )

#         # print("\nTop route candidates:")
#         # for c in details["route_candidates"][:10]:
#         #     print(
#         #         f"  {c['src']}->{c['dst']} | current_option={c['current_option']} | "
#         #         f"dnn={c.get('candidate_confidence', 0):.4f} | score={c['score']:.4f} | "
#         #         f"route_exp={c['route_exposure']:.2f} | "
#         #         f"link_usage={c['link_usage']:.2f}"
#         #     )


#         # =========================
#         # PRINT DNN-RANKED CANDIDATES
#         # =========================

#         print("\nTop IP candidates by DNN:")

#         ip_ranked = sorted(
#             details["ip_candidates"],
#             key=lambda c: c.get("candidate_confidence", -1),
#             reverse=True
#         )

#         for c in ip_ranked[:10]:
#             dnn = c.get("candidate_confidence")
#             dnn_text = f"{dnn:.4f}" if dnn is not None else "N/A"

#             print(
#                 f"  {c['host']} | "
#                 f"dnn={dnn_text} | "
#                 f"old_score={c['score']:.4f} | "
#                 f"p_host={c['p_host']:.3f} | "
#                 f"ip_exp={c['ip_exposure']:.2f} | "
#                 f"grid={c['grid_priority']:.2f}"
#             )


#         print("\nTop route candidates by DNN:")

#         route_ranked = sorted(
#             details["route_candidates"],
#             key=lambda c: c.get("candidate_confidence", -1),
#             reverse=True
#         )

#         for c in route_ranked[:10]:
#             dnn = c.get("candidate_confidence")
#             dnn_text = f"{dnn:.4f}" if dnn is not None else "N/A"

#             print(
#                 f"  {c['src']}->{c['dst']} | "
#                 f"current_option={c['current_option']} | "
#                 f"dnn={dnn_text} | "
#                 f"old_score={c['score']:.4f} | "
#                 f"route_exp={c['route_exposure']:.2f} | "
#                 f"link_usage={c['link_usage']:.2f}"
#             )
#         #new above
        
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
        
#         cycle_idx += 1
#         time.sleep(30)

# ////////////////// new edition /////////////////////////




# ////////////////////////////////////////////////////////////////////////////////////////


# proactive_new_scoring.py

import re
import os, time
import requests
import pandas as pd
import numpy as np
from requests.auth import HTTPBasicAuth
from proactive_new_logging import log_evaluation_snapshot

from mtd_utils import repeat_ip_history, repeat_route_history
# DNN decision model
from mtd_model_decision import MTDModel
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

# Must match the candidate-student deployment policy used during training.
K_IP = 6
K_ROUTE = 20
DEFENSE_BUDGET = 0.50

def resolve_model_dir():
    """Use an explicit environment path, then the user's bundle folder names."""
    here = os.path.dirname(os.path.abspath(__file__))
    requested = os.environ.get("MTD_MODEL_DIR")
    candidates = [requested] if requested else []
    candidates += [
        os.path.join(here, "three_models_"),
        os.path.join(here, "mtd_three_models"),
    ]
    for path in candidates:
        if path and os.path.isdir(path):
            return os.path.abspath(path)
    checked = "\n  - ".join(os.path.abspath(p) for p in candidates if p)
    raise FileNotFoundError(
        "Cannot find the three-model execution folder. Checked:\n  - " + checked
        + "\nSet MTD_MODEL_DIR to the verified three_models_ artifact folder."
    )


MODEL_DIR = resolve_model_dir()
MTD_MODEL = MTDModel(MODEL_DIR)
# DEFENSE_BUDGET = 1.0


# E_IP = 0.70
# # E_IP = 0.70 #Eip​=1−23.75/39.72​
# # E_ROUTE = 0.60 # Eroute​=1−10.99/27.45 -- from graph​
# E_ROUTE = 0.70 # Eroute​=1−10.99/27.45 -- from graph​

E_IP=0.40
E_ROUTE=0.60


# O_IP = 2830 / 3000
O_IP = 3350 / 4000

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
ROUTE_OVERLAP_CSV = "onos_active_flow_route_overlap_v3.csv" # new


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

    # /////////new
    FLOW_CONCERN_START = 3       # 1-3 flows toward a host = usually normal
    FLOW_CONCERN_FULL = 20       # 20+ flows toward a host = strong concern

    SENDER_CONCERN_START = 2     # 1-2 sender MACs = not concerning
    SENDER_CONCERN_FULL = 10     # 10+ sender MACs = strong concern

    for _, row in f.iterrows():
        host = row["host"]

        total_flows = float(row["unique_flow_count_towards_host"])
        short_flows = float(row["short_lived_flow_count_towards_host"])
        unique_sender_macs = float(row["unique_sender_mac_count"])

        # Short-flow ratio only among flows toward this host
        short_flow_ratio = short_flows / max(1.0, total_flows)
        short_flow_ratio = min(max(short_flow_ratio, 0.0), 1.0)

        # Sender pressure:
        # 1 or 2 sender MACs should not be suspicious by itself
        sender_mac_diversity = (
            (unique_sender_macs - SENDER_CONCERN_START)
            / max(1.0, SENDER_CONCERN_FULL - SENDER_CONCERN_START)
        )
        sender_mac_diversity = min(max(sender_mac_diversity, 0.0), 1.0)

        # Flow volume gate:
        # 1 or 2 flows should not create suspicion by itself
        flow_volume_gate = (
            (total_flows - FLOW_CONCERN_START)
            / max(1.0, FLOW_CONCERN_FULL - FLOW_CONCERN_START)
        )
        flow_volume_gate = min(max(flow_volume_gate, 0.0), 1.0)

        raw_flow_suspicion = (
            0.70 * short_flow_ratio
            + 0.30 * sender_mac_diversity
        )

        flow_suspicion = flow_volume_gate * raw_flow_suspicion
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
    # /////////new


def load_route_overlap(csv=ROUTE_OVERLAP_CSV): # new route flow
    try:
        df = pd.read_csv(csv)
    except Exception:
        return {}

    if df.empty or "flow" not in df.columns or "max_overlap_on_any_link" not in df.columns:
        return {}

    total = max(len(df), 1)
    out = {}

    for _, r in df.iterrows():
        flow = str(r["flow"]).strip()

        if "->" not in flow:
            continue

        a, b = [x.strip() for x in flow.split("->", 1)]
        pair = pair_key(a, b)

        max_overlap = float(r["max_overlap_on_any_link"])
        pressure = min(max_overlap / total, 1.0)

        out[pair] = {
            "max_flow_overlap": max_overlap,
            "overlap_pressure": pressure,
        }

    return out

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

# grid reading timely
def load_grid_priority(obs_csv, obs_time_seconds=None):
    obs = pd.read_csv(obs_csv)

    cols = {c.lower(): c for c in obs.columns}

    host_col = None
    rank_col = None
    time_col = None

    for key in ["pmu", "gen_bus", "bus", "host"]:
        if key in cols:
            host_col = cols[key]
            break

    for key in ["rank", "pmu_rank", "observability_rank"]:
        if key in cols:
            rank_col = cols[key]
            break

    for key in ["time_seconds", "timestamp", "time"]:
        if key in cols:
            time_col = cols[key]
            break

    if host_col is None or rank_col is None:
        return {}

    # Pick the observability phase for this MTD cycle
    if obs_time_seconds is not None and time_col is not None:
        obs[time_col] = pd.to_numeric(obs[time_col], errors="coerce")
        obs = obs.dropna(subset=[time_col])

        available_times = sorted(obs[time_col].unique())

        if available_times:
            # choose exact/next available phase
            chosen_time = None
            for t in available_times:
                if t >= obs_time_seconds:
                    chosen_time = t
                    break

            # if requested time exceeds file, use last available
            if chosen_time is None:
                chosen_time = available_times[-1]

            obs = obs[obs[time_col] == chosen_time]

            print(f"[OBS] using observability phase time_seconds={chosen_time}")

    obs["host"] = obs[host_col].apply(
        lambda x: f"h{int(x)}" if pd.notna(x) else None
    )
    obs["rank"] = pd.to_numeric(obs[rank_col], errors="coerce")

    obs = obs.dropna(subset=["host", "rank"])

    if obs.empty:
        return {}

    max_rank = obs["rank"].max()
    min_rank = obs["rank"].min()

    if max_rank == min_rank:
        obs["grid_priority"] = 1.0
    else:
        obs["grid_priority"] = 1.0 - (
            (obs["rank"] - min_rank) / (max_rank - min_rank)
        )

    return dict(zip(obs["host"], obs["grid_priority"]))

# =========================
# IP CANDIDATES
# =========================

# def build_ip_candidates(host_csv, ip_hist_csv, obs_csv, active_hosts=None,):
# def build_ip_candidates(host_csv, ip_hist_csv, obs_csv, flow_summary_csv=FLOW_SUMMARY_CSV, active_hosts=None,): #//// Flow
def build_ip_candidates(host_csv,ip_hist_csv,obs_csv,flow_summary_csv=FLOW_SUMMARY_CSV, active_hosts=None,obs_time_seconds=None,): #added grid
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

        h = agg.copy()

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

    # grid_map = load_grid_priority(obs_csv)
    grid_map = load_grid_priority(obs_csv, obs_time_seconds=obs_time_seconds) # timely grid

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
            "rx_pps_max": float(row.get("rx_pps_max", row["rx_pps"])),
            "rx_pps_mean": float(row.get("rx_pps_mean", row["rx_pps"])),
            "tx_pps_max": float(row.get("tx_pps_max", row["tx_pps"])),
            "tx_pps_mean": float(row.get("tx_pps_mean", row["tx_pps"])),
            "rx_mbps_max": float(row.get("rx_mbps_max", row["rx_mbps"])),
            "rx_mbps_mean": float(row.get("rx_mbps_mean", row["rx_mbps"])),
            "tx_mbps_max": float(row.get("tx_mbps_max", row["tx_mbps"])),
            "tx_mbps_mean": float(row.get("tx_mbps_mean", row["tx_mbps"])),
            "flow_suspicion": flow_suspicion, # Flow info from here
            "short_flow_ratio": short_flow_ratio,
            "unique_sender_mac_count": float(flow_info.get("unique_sender_mac_count", 0.0)),
            "sender_mac_diversity": sender_mac_diversity,
            "unique_flow_count": float(flow_info.get("unique_flow_count", 0.0)),
            "short_lived_flow_count": float(flow_info.get("short_lived_flow_count", 0.0)),

            # Threshold-aware raw-input fields used by Raw-B/Raw-C style
            # student checkpoints. These are policy constants available at
            # deployment, not teacher labels.
            "rx_pps_threshold_ratio_max": float(row.get("rx_pps_max", row["rx_pps"])) / max(HOST_PPS_MONITOR_THRESHOLD, 1e-12),
            "rx_pps_threshold_ratio_mean": float(row.get("rx_pps_mean", row["rx_pps"])) / max(HOST_PPS_MONITOR_THRESHOLD, 1e-12),
            "rx_pps_threshold_margin_max": float(row.get("rx_pps_max", row["rx_pps"])) - HOST_PPS_MONITOR_THRESHOLD,
            "rx_mbps_threshold_ratio_max": float(row.get("rx_mbps_max", row["rx_mbps"])) / max(HOST_RX_MBPS_THRESHOLD, 1e-12),
            "rx_mbps_threshold_ratio_mean": float(row.get("rx_mbps_mean", row["rx_mbps"])) / max(HOST_RX_MBPS_THRESHOLD, 1e-12),
            "rx_mbps_threshold_margin_max": float(row.get("rx_mbps_max", row["rx_mbps"])) - HOST_RX_MBPS_THRESHOLD,


        })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates


# =========================
# ROUTE CANDIDATES
# =========================

# def build_route_candidates(link_csv, hop_csv, route_hist_csv, active_pairs,):
# def build_route_candidates(link_csv, hop_csv, route_hist_csv, active_pairs, obs_csv,): # added scoring
def build_route_candidates(link_csv, hop_csv, route_hist_csv, active_pairs, obs_csv, obs_time_seconds=None,): # for grid time

    if not active_pairs:
        return []

    # grid_map = load_grid_priority(obs_csv) # new added scoring
    grid_map = load_grid_priority(obs_csv, obs_time_seconds=obs_time_seconds) # grid time update

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

        # Keep both the old blended values and the raw mean/max aggregates.
        # Raw-input student checkpoints can therefore consume the same fields
        # they saw during training instead of falling back to prepared scores.
        link = agg.copy()

    for c in ["rx_mbps", "tx_mbps"]:
        if f"{c}_max" not in link.columns:
            link[f"{c}_max"] = link[c]
        if f"{c}_mean" not in link.columns:
            link[f"{c}_mean"] = link[c]

    link["rx_mbps"] = pd.to_numeric(link["rx_mbps"], errors="coerce").fillna(0.0)
    link["tx_mbps"] = pd.to_numeric(link["tx_mbps"], errors="coerce").fillna(0.0)
    link["link_mbps"] = link[["rx_mbps", "tx_mbps"]].max(axis=1)

    link["link_usage_norm"] = (link["link_mbps"] / LINK_CAPACITY_MBPS).clip(0, 1)
    link["link_monitor"] = (link["link_mbps"] / LINK_MONITOR_THRESHOLD_MBPS).clip(0, 1)
    
    link["norm_link"] = link["link_id"].apply(normalize_onos_link)

    usage_map = dict(zip(link["norm_link"], link["link_usage_norm"]))
    monitor_map = dict(zip(link["norm_link"], link["link_monitor"]))
    link_raw_maps = {
        c: dict(zip(link["norm_link"], pd.to_numeric(link[c], errors="coerce").fillna(0.0)))
        for c in [
            "rx_mbps", "tx_mbps",
            "rx_mbps_max", "rx_mbps_mean",
            "tx_mbps_max", "tx_mbps_mean",
        ]
    }


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

    overlap_map = load_route_overlap()

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


        # ////// flow for route
        ov = overlap_map.get(pair, {})
        max_flow_overlap = ov.get("max_flow_overlap", 0.0)
        overlap_pressure = ov.get("overlap_pressure", 0.0)
        # ////// flow for route


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

        # Route-level raw traffic uses the bottleneck link for each statistic.
        # These fields are harmless for prepared-feature checkpoints and are
        # required by raw/aggregated route student checkpoints.
        raw_route = {
            c: max([link_raw_maps[c].get(x, 0.0) for x in links], default=0.0)
            for c in link_raw_maps
        }
        raw_route["link_mbps_max"] = max(raw_route["rx_mbps_max"], raw_route["tx_mbps_max"])
        raw_route["link_mbps_mean"] = max(raw_route["rx_mbps_mean"], raw_route["tx_mbps_mean"])
        raw_route["link_capacity_ratio_max"] = raw_route["link_mbps_max"] / max(LINK_CAPACITY_MBPS, 1e-12)
        raw_route["link_capacity_ratio_mean"] = raw_route["link_mbps_mean"] / max(LINK_CAPACITY_MBPS, 1e-12)
        raw_route["link_monitor_ratio_max"] = raw_route["link_mbps_max"] / max(LINK_MONITOR_THRESHOLD_MBPS, 1e-12)
        raw_route["link_monitor_ratio_mean"] = raw_route["link_mbps_mean"] / max(LINK_MONITOR_THRESHOLD_MBPS, 1e-12)
        raw_route["link_capacity_margin_max"] = raw_route["link_mbps_max"] - LINK_CAPACITY_MBPS
        raw_route["link_monitor_margin_max"] = raw_route["link_mbps_max"] - LINK_MONITOR_THRESHOLD_MBPS

        route_exposure = float(exposure_map.get(pair, 0.0))


        # Observability of the active route endpoint pair
        route_grid_priority = max(
            float(grid_map.get(pair[0], DEFAULT_GRID_PRIORITY)),
            float(grid_map.get(pair[1], DEFAULT_GRID_PRIORITY)),
        )

        p_route = (
            # 0.45 * link_usage
            0.40 * link_usage
            + 0.30 * link_monitor
            + 0.10 * route_grid_priority
            + 0.20 * overlap_pressure
        )

        benefit = p_route * route_exposure * E_ROUTE
        # cost = O_ROUTE + 0.10 * link_usage
        cost = O_ROUTE
        # hop_cost = LAMBDA_HOP * hop_penalty
        hop_cost = .0001

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
            "max_flow_overlap": max_flow_overlap, # flow into route
            "overlap_pressure": overlap_pressure, # flow into route
            **raw_route,
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates


# =========================
# DNN DECISION
# =========================
# The former decision MILP is replaced by:
#   Deep Sets -> operation -> Host/Route DNN -> threshold + Top-K
# run_ip_ilp() and run_route_ilp() are still used later for execution.


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

# for grid
def decide_ilp(
    host_csv="host_stats_onos.csv",
    link_csv="link_stats_onos.csv",
    hop_csv="hop_list.csv",
    ip_hist_csv="ip_history.csv",
    route_hist_csv="route_history.csv",
    obs_csv="observability.csv",
    obs_time_seconds=None,
):
    active_pairs, active_hosts = fetch_onos_active_pairs()
    # for grid timing
    ip_candidates = build_ip_candidates(
        host_csv=host_csv,
        ip_hist_csv=ip_hist_csv,
        obs_csv=obs_csv,
        active_hosts=active_hosts,
        obs_time_seconds=obs_time_seconds,
    )

    # grid timing
    route_candidates = build_route_candidates(
        link_csv=link_csv,
        hop_csv=hop_csv,
        route_hist_csv=route_hist_csv,
        active_pairs=active_pairs,
        obs_csv=obs_csv,
        obs_time_seconds=obs_time_seconds,
    )


    action, selected_hosts, selected_routes, decision_solver_time_s, rm_conf = MTD_MODEL.decide(
        ip_candidates,
        route_candidates,
        k_ip=K_IP,
        k_route=K_ROUTE,
    )

    print(
        f"[DNN DECISION] action={action} | "
        f"RM_conf={rm_conf:.4f} | time={decision_solver_time_s:.6f}s"
    )

    details = {
        "active_pairs": sorted(list(active_pairs)),
        "active_hosts": sorted(list(active_hosts), key=lambda x: host_num(x) or 99999),
        "ip_candidates": ip_candidates,
        "route_candidates": route_candidates,
        "selected_routes": selected_routes,
        "decision_solver_time_s": decision_solver_time_s,  # kept for logger compatibility
        "operation_rm_confidence": rm_conf,
    }

    return action, selected_hosts, selected_routes, details



# ////////////need logging /////////////////
import csv
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
    # grid time
    cycle_idx = 0
    MTD_INTERVAL_SECONDS = 30
    # //////


    while(True):
        cycle_started = time.monotonic()
        # action, hosts, routes, details = decide_ilp() #commented for grid time

        # grid time
        obs_time_seconds = cycle_idx * MTD_INTERVAL_SECONDS

        action, hosts, routes, details = decide_ilp(
            obs_time_seconds=obs_time_seconds
        )
        # grid time



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

        # old
        # print("\nTop IP candidates:")
        # for c in details["ip_candidates"][:10]:
        #     print(
        #         f"  {c['host']} | dnn={c.get('candidate_confidence', 0):.4f} | "
        #         f"score={c['score']:.4f} | p_host={c['p_host']:.3f} | "
        #         f"ip_exp={c['ip_exposure']:.2f} | "
        #         f"grid={c['grid_priority']:.2f}"
        #     )

        # print("\nTop route candidates:")
        # for c in details["route_candidates"][:10]:
        #     print(
        #         f"  {c['src']}->{c['dst']} | current_option={c['current_option']} | "
        #         f"dnn={c.get('candidate_confidence', 0):.4f} | score={c['score']:.4f} | "
        #         f"route_exp={c['route_exposure']:.2f} | "
        #         f"link_usage={c['link_usage']:.2f}"
        #     )


        # =========================
        # PRINT DNN-RANKED CANDIDATES
        # =========================

        print("\nTop IP candidates by DNN:")

        ip_ranked = sorted(
            details["ip_candidates"],
            key=lambda c: c.get("candidate_confidence", -1),
            reverse=True
        )

        for c in ip_ranked[:10]:
            dnn = c.get("candidate_confidence")
            dnn_text = f"{dnn:.4f}" if dnn is not None else "N/A"

            print(
                f"  {c['host']} | "
                f"dnn={dnn_text} | "
                f"old_score={c['score']:.4f} | "
                f"p_host={c['p_host']:.3f} | "
                f"ip_exp={c['ip_exposure']:.2f} | "
                f"grid={c['grid_priority']:.2f}"
            )


        print("\nTop route candidates by DNN:")

        route_ranked = sorted(
            details["route_candidates"],
            key=lambda c: c.get("candidate_confidence", -1),
            reverse=True
        )

        for c in route_ranked[:10]:
            dnn = c.get("candidate_confidence")
            dnn_text = f"{dnn:.4f}" if dnn is not None else "N/A"

            print(
                f"  {c['src']}->{c['dst']} | "
                f"current_option={c['current_option']} | "
                f"dnn={dnn_text} | "
                f"old_score={c['score']:.4f} | "
                f"route_exp={c['route_exposure']:.2f} | "
                f"link_usage={c['link_usage']:.2f}"
            )
        #new above
        
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
        
        cycle_idx += 1

        # The uploaded loop defined a 30-second interval but never slept,
        # which would repeatedly query ONOS and execute decisions as fast as
        # the CPU allowed. Keep cycles aligned to the intended interval.
        cycle_elapsed = time.monotonic() - cycle_started
        time.sleep(max(0.0, MTD_INTERVAL_SECONDS - cycle_elapsed))
        time.sleep(5)