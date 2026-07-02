# # proactive_logger.py

# import os
# import csv
# from pathlib import Path
# from datetime import datetime

# import pandas as pd


# BASE_DIR = Path(__file__).resolve().parent
# LOG_DIR = BASE_DIR / "proactive_files" / "logger" / "csv_logs"

# DECISION_LOG = LOG_DIR / "decision_summary.csv"
# HOST_LOG = LOG_DIR / "host_snapshot.csv"
# IP_SCORE_LOG = LOG_DIR / "ip_score_snapshot.csv"
# LINK_LOG = LOG_DIR / "link_snapshot.csv"
# ROUTE_SCORE_LOG = LOG_DIR / "route_score_snapshot.csv"


# def _append_csv(path, rows):
#     if not rows:
#         return

#     LOG_DIR.mkdir(parents=True, exist_ok=True)

#     fieldnames = sorted({k for r in rows for k in r.keys()})
#     write_header = not path.exists()

#     with open(path, "a", newline="") as f:
#         w = csv.DictWriter(f, fieldnames=fieldnames)
#         if write_header:
#             w.writeheader()
#         w.writerows(rows)


# def _cycle_id():
#     return datetime.now().strftime("%Y%m%dT%H%M%S_%f")


# def _host_from_mac(mac):
#     try:
#         mac = str(mac).lower().strip()
#         if not mac.startswith("00:00:00:00:00:"):
#             return ""
#         n = int(mac.split(":")[-1], 16)
#         return f"h{n}" if 1 <= n <= 40 else ""
#     except Exception:
#         return ""


# def _reason(selected, action, score, target_action):
#     if selected:
#         return "selected"

#     if action != target_action:
#         return f"not_selected_{action}_won"

#     if float(score or 0.0) <= 0:
#         return "not_selected_non_positive_score"

#     return "not_selected_lower_rank_or_budget"


# def log_evaluation_snapshot(
#     action,
#     hosts,
#     routes,
#     details,
#     host_csv="host_stats_onos.csv",
#     link_csv="link_stats_onos.csv",
#     link_capacity_mbps=1.0,
#     link_monitor_threshold_mbps=0.8,
# ):
#     """
#     Main logging function.

#     Creates:
#         proactive_files/logger/csv_logs/decision_summary.csv
#         proactive_files/logger/csv_logs/host_snapshot.csv
#         proactive_files/logger/csv_logs/ip_score_snapshot.csv
#         proactive_files/logger/csv_logs/link_snapshot.csv
#         proactive_files/logger/csv_logs/route_score_snapshot.csv
#     """

#     cid = _cycle_id()
#     ts = datetime.now().isoformat(timespec="seconds")

#     hosts = hosts or []
#     routes = routes or []
#     details = details or {}

#     ip_cands = details.get("ip_candidates", [])
#     route_cands = details.get("route_candidates", [])

#     selected_hosts = set(hosts)
#     selected_pairs = {(r.get("src"), r.get("dst")) for r in routes}

#     # -------------------------
#     # Decision summary
#     # -------------------------
#     _append_csv(DECISION_LOG, [{
#         "cycle_id": cid,
#         "timestamp": ts,
#         "action": action,
#         "selected_hosts": "|".join(hosts),
#         "selected_routes": "|".join(f"{r.get('src')}-{r.get('dst')}" for r in routes),
#         "n_ip_candidates": len(ip_cands),
#         "n_route_candidates": len(route_cands),
#         "top_ip_host": ip_cands[0].get("host", "") if ip_cands else "",
#         "top_ip_score": ip_cands[0].get("score", "") if ip_cands else "",
#         "top_route_pair": f"{route_cands[0].get('src')}-{route_cands[0].get('dst')}" if route_cands else "",
#         "top_route_score": route_cands[0].get("score", "") if route_cands else "",
#         "n_active_hosts": len(details.get("active_hosts", [])),
#         "n_active_pairs": len(details.get("active_pairs", [])),
#     }])

#     # -------------------------
#     # IP candidate score log
#     # -------------------------
#     ip_rows = []
#     for rank, c in enumerate(ip_cands, 1):
#         h = c.get("host", "")
#         selected = h in selected_hosts

#         ip_rows.append({
#             "cycle_id": cid,
#             "timestamp": ts,
#             "rank": rank,
#             "host": h,
#             "action": action,
#             "selected": int(selected),
#             "selection_reason": _reason(selected, action, c.get("score"), "ip_shuffle"),
#             "score": c.get("score", ""),
#             "benefit": c.get("benefit", ""),
#             "cost": c.get("cost", ""),
#             "p_host": c.get("p_host", ""),
#             "traffic_risk": c.get("traffic_risk", ""),
#             "monitor_score": c.get("monitor_score", ""),
#             "ip_exposure": c.get("ip_exposure", ""),
#             "grid_priority": c.get("grid_priority", ""),
#             "rx_pps": c.get("rx_pps", ""),
#             "tx_pps": c.get("tx_pps", ""),
#             "rx_mbps": c.get("rx_mbps", ""),
#             "tx_mbps": c.get("tx_mbps", ""),
#         })

#     _append_csv(IP_SCORE_LOG, ip_rows)

#     # -------------------------
#     # Route candidate score log
#     # -------------------------
#     route_rows = []
#     for rank, c in enumerate(route_cands, 1):
#         src, dst = c.get("src", ""), c.get("dst", "")
#         selected = (src, dst) in selected_pairs

#         route_rows.append({
#             "cycle_id": cid,
#             "timestamp": ts,
#             "rank": rank,
#             "src": src,
#             "dst": dst,
#             "pair": f"{src}-{dst}",
#             "action": action,
#             "selected": int(selected),
#             "selection_reason": _reason(selected, action, c.get("score"), "route_mutation"),
#             "score": c.get("score", ""),
#             "benefit": c.get("benefit", ""),
#             "cost": c.get("cost", ""),
#             "p_route": c.get("p_route", ""),
#             "route_exposure": c.get("route_exposure", ""),
#             "link_usage": c.get("link_usage", ""),
#             "link_monitor": c.get("link_monitor", ""),
#             "current_option": c.get("current_option", c.get("option", "")),
#             "hop_count": c.get("hop_count", ""),
#             "latency_penalty": c.get("latency_penalty", ""),
#             "path": c.get("path", ""),
#         })

#     _append_csv(ROUTE_SCORE_LOG, route_rows)

#     # -------------------------
#     # Raw host and link snapshots
#     # -------------------------
#     _log_host_snapshot(cid, ts, action, host_csv, selected_hosts, ip_cands, details.get("active_hosts", []))
#     _log_link_snapshot(cid, ts, action, link_csv, link_capacity_mbps, link_monitor_threshold_mbps)

#     return cid


# def _log_host_snapshot(cid, ts, action, host_csv, selected_hosts, ip_cands, active_hosts):
#     if not os.path.exists(host_csv):
#         return

#     df = pd.read_csv(host_csv)
#     if df.empty:
#         return

#     if "host" not in df.columns:
#         df["host"] = df["host_mac"].apply(_host_from_mac) if "host_mac" in df.columns else ""

#     df = df[df["host"] != ""]
#     if df.empty:
#         return

#     if "timestamp" in df.columns:
#         df = df.sort_values("timestamp").groupby("host", as_index=False).tail(1)

#     for col in ["rx_pps", "tx_pps", "rx_mbps", "tx_mbps", "rx_kbps", "tx_kbps"]:
#         if col not in df.columns:
#             df[col] = 0.0
#         df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

#     cand_map = {c.get("host"): c for c in ip_cands if c.get("host")}
#     active_hosts = set(active_hosts or [])

#     rows = []
#     for _, r in df.iterrows():
#         h = r["host"]
#         cand = cand_map.get(h, {})

#         rows.append({
#             "cycle_id": cid,
#             "timestamp": ts,
#             "host": h,
#             "host_mac": r.get("host_mac", ""),
#             "action": action,
#             "selected": int(h in selected_hosts),
#             "active_host": int(h in active_hosts),
#             "was_ip_candidate": int(h in cand_map),
#             "candidate_score": cand.get("score", ""),
#             "rx_pps": r["rx_pps"],
#             "tx_pps": r["tx_pps"],
#             "rx_mbps": r["rx_mbps"],
#             "tx_mbps": r["tx_mbps"],
#             "rx_kbps": r["rx_kbps"],
#             "tx_kbps": r["tx_kbps"],
#         })

#     _append_csv(HOST_LOG, rows)


# def _log_link_snapshot(cid, ts, action, link_csv, capacity, threshold):
#     if not os.path.exists(link_csv):
#         return

#     df = pd.read_csv(link_csv)
#     if df.empty:
#         return

#     if "timestamp" in df.columns:
#         df = df.sort_values("timestamp").groupby("link_id", as_index=False).tail(1)

#     for col in ["rx_mbps", "tx_mbps", "rx_pps", "tx_pps"]:
#         if col not in df.columns:
#             df[col] = 0.0
#         df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

#     df["link_mbps"] = df[["rx_mbps", "tx_mbps"]].max(axis=1)
#     df["link_usage_norm"] = (df["link_mbps"] / capacity).clip(0, 1)
#     df["link_monitor"] = (df["link_mbps"] / threshold).clip(0, 1)

#     rows = []
#     for _, r in df.iterrows():
#         rows.append({
#             "cycle_id": cid,
#             "timestamp": ts,
#             "link_id": r.get("link_id", ""),
#             "action": action,
#             "rx_mbps": r["rx_mbps"],
#             "tx_mbps": r["tx_mbps"],
#             "rx_pps": r["rx_pps"],
#             "tx_pps": r["tx_pps"],
#             "link_mbps": r["link_mbps"],
#             "link_usage_norm": r["link_usage_norm"],
#             "link_monitor": r["link_monitor"],
#         })

#     _append_csv(LINK_LOG, rows)




# ///////////adapt to new setup


# proactive_logger.py

import os
import csv
from pathlib import Path
from datetime import datetime

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "proactive_files" / "logger" / "csv_logs"

DECISION_LOG = LOG_DIR / "decision_summary.csv"
HOST_LOG = LOG_DIR / "host_snapshot.csv"
IP_SCORE_LOG = LOG_DIR / "ip_score_snapshot.csv"
LINK_LOG = LOG_DIR / "link_snapshot.csv"
ROUTE_SCORE_LOG = LOG_DIR / "route_score_snapshot.csv"


def _append_csv(path, rows):
    if not rows:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    fieldnames = sorted({k for r in rows for k in r.keys()})
    write_header = not path.exists()

    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            w.writeheader()
        w.writerows(rows)


def _cycle_id():
    return datetime.now().strftime("%Y%m%dT%H%M%S_%f")


def _host_from_mac(mac):
    try:
        mac = str(mac).lower().strip()
        if not mac.startswith("00:00:00:00:00:"):
            return ""
        n = int(mac.split(":")[-1], 16)
        return f"h{n}" if 1 <= n <= 40 else ""
    except Exception:
        return ""


def _reason(selected, action, score, target_action):
    if selected:
        return "selected"

    if action != target_action:
        return f"not_selected_{action}_won"

    if float(score or 0.0) <= 0:
        return "not_selected_non_positive_score"

    return "not_selected_lower_rank_or_budget"


def log_evaluation_snapshot(
    action,
    hosts,
    routes,
    details,
    host_csv="host_stats_onos.csv",
    link_csv="link_stats_onos.csv",
    link_capacity_mbps=1.0,
    link_monitor_threshold_mbps=0.8,
):
    """
    Main logging function.

    Creates:
        proactive_files/logger/csv_logs/decision_summary.csv
        proactive_files/logger/csv_logs/host_snapshot.csv
        proactive_files/logger/csv_logs/ip_score_snapshot.csv
        proactive_files/logger/csv_logs/link_snapshot.csv
        proactive_files/logger/csv_logs/route_score_snapshot.csv
    """

    cid = _cycle_id()
    ts = datetime.now().isoformat(timespec="seconds")

    hosts = hosts or []
    routes = routes or []
    details = details or {}

    ip_cands = details.get("ip_candidates", [])
    route_cands = details.get("route_candidates", [])

    selected_hosts = set(hosts)
    selected_pairs = {(r.get("src"), r.get("dst")) for r in routes}

    # -------------------------
    # Decision summary
    # -------------------------
    _append_csv(DECISION_LOG, [{
        "cycle_id": cid,
        "timestamp": ts,
        "action": action,
        "selected_hosts": "|".join(hosts),
        "selected_routes": "|".join(f"{r.get('src')}-{r.get('dst')}" for r in routes),
        "n_ip_candidates": len(ip_cands),
        "n_route_candidates": len(route_cands),
        "top_ip_host": ip_cands[0].get("host", "") if ip_cands else "",
        "top_ip_score": ip_cands[0].get("score", "") if ip_cands else "",
        "top_route_pair": f"{route_cands[0].get('src')}-{route_cands[0].get('dst')}" if route_cands else "",
        "top_route_score": route_cands[0].get("score", "") if route_cands else "",
        "n_active_hosts": len(details.get("active_hosts", [])),
        "n_active_pairs": len(details.get("active_pairs", [])),
    }])

    # -------------------------
    # IP candidate score log
    # -------------------------
    ip_rows = []
    for rank, c in enumerate(ip_cands, 1):
        h = c.get("host", "")
        selected = h in selected_hosts

        ip_rows.append({
            "cycle_id": cid,
            "timestamp": ts,
            "rank": rank,
            "host": h,
            "action": action,
            "selected": int(selected),
            "selection_reason": _reason(selected, action, c.get("score"), "ip_shuffle"),
            "score": c.get("score", ""),
            "benefit": c.get("benefit", ""),
            "cost": c.get("cost", ""),
            "p_host": c.get("p_host", ""),
            "traffic_risk": c.get("traffic_risk", ""),
            "monitor_score": c.get("monitor_score", ""),
            "ip_exposure": c.get("ip_exposure", ""),
            "grid_priority": c.get("grid_priority", ""),
            # --- new scoring: flow-suspicion term (0.10 of p_host) ---
            "flow_suspicion": c.get("flow_suspicion", ""),
            "short_flow_ratio": c.get("short_flow_ratio", ""),
            "sender_mac_diversity": c.get("sender_mac_diversity", ""),
            "unique_sender_mac_count": c.get("unique_sender_mac_count", ""),
            "unique_flow_count": c.get("unique_flow_count", ""),
            "short_lived_flow_count": c.get("short_lived_flow_count", ""),
            # ---------------------------------------------------------
            "rx_pps": c.get("rx_pps", ""),
            "tx_pps": c.get("tx_pps", ""),
            "rx_mbps": c.get("rx_mbps", ""),
            "tx_mbps": c.get("tx_mbps", ""),
        })

    _append_csv(IP_SCORE_LOG, ip_rows)

    # -------------------------
    # Route candidate score log
    # -------------------------
    route_rows = []
    for rank, c in enumerate(route_cands, 1):
        src, dst = c.get("src", ""), c.get("dst", "")
        selected = (src, dst) in selected_pairs

        route_rows.append({
            "cycle_id": cid,
            "timestamp": ts,
            "rank": rank,
            "src": src,
            "dst": dst,
            "pair": f"{src}-{dst}",
            "action": action,
            "selected": int(selected),
            "selection_reason": _reason(selected, action, c.get("score"), "route_mutation"),
            "score": c.get("score", ""),
            "benefit": c.get("benefit", ""),
            "cost": c.get("cost", ""),
            "p_route": c.get("p_route", ""),
            "route_exposure": c.get("route_exposure", ""),
            "link_usage": c.get("link_usage", ""),
            "link_monitor": c.get("link_monitor", ""),
            # --- new scoring: grid priority term (0.10 of p_route) ---
            "max_flow_overlap": c.get("max_flow_overlap", ""), # flow route
            "overlap_pressure": c.get("overlap_pressure", ""), # flow route
            "route_grid_priority": c.get("route_grid_priority", ""),
            # --- new scoring: hop penalty / hop cost ---
            # scoring dict uses `current_hop_count`; keep `hop_count` as an
            # alias for backward compatibility with older readers.
            "current_hop_count": c.get("current_hop_count", c.get("hop_count", "")),
            "hop_count": c.get("current_hop_count", c.get("hop_count", "")),
            "hop_penalty": c.get("hop_penalty", ""),
            "hop_cost": c.get("hop_cost", ""),
            # ---------------------------------------------------------
            "current_option": c.get("current_option", c.get("option", "")),
            "path": c.get("path", ""),
        })

    _append_csv(ROUTE_SCORE_LOG, route_rows)

    # -------------------------
    # Raw host and link snapshots
    # -------------------------
    _log_host_snapshot(cid, ts, action, host_csv, selected_hosts, ip_cands, details.get("active_hosts", []))
    _log_link_snapshot(cid, ts, action, link_csv, link_capacity_mbps, link_monitor_threshold_mbps)

    return cid


def _log_host_snapshot(cid, ts, action, host_csv, selected_hosts, ip_cands, active_hosts):
    if not os.path.exists(host_csv):
        return

    df = pd.read_csv(host_csv)
    if df.empty:
        return

    if "host" not in df.columns:
        df["host"] = df["host_mac"].apply(_host_from_mac) if "host_mac" in df.columns else ""

    df = df[df["host"] != ""]
    if df.empty:
        return

    if "timestamp" in df.columns:
        df = df.sort_values("timestamp").groupby("host", as_index=False).tail(1)

    for col in ["rx_pps", "tx_pps", "rx_mbps", "tx_mbps", "rx_kbps", "tx_kbps"]:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    cand_map = {c.get("host"): c for c in ip_cands if c.get("host")}
    active_hosts = set(active_hosts or [])

    rows = []
    for _, r in df.iterrows():
        h = r["host"]
        cand = cand_map.get(h, {})

        rows.append({
            "cycle_id": cid,
            "timestamp": ts,
            "host": h,
            "host_mac": r.get("host_mac", ""),
            "action": action,
            "selected": int(h in selected_hosts),
            "active_host": int(h in active_hosts),
            "was_ip_candidate": int(h in cand_map),
            "candidate_score": cand.get("score", ""),
            "rx_pps": r["rx_pps"],
            "tx_pps": r["tx_pps"],
            "rx_mbps": r["rx_mbps"],
            "tx_mbps": r["tx_mbps"],
            "rx_kbps": r["rx_kbps"],
            "tx_kbps": r["tx_kbps"],
        })

    _append_csv(HOST_LOG, rows)


def _log_link_snapshot(cid, ts, action, link_csv, capacity, threshold):
    if not os.path.exists(link_csv):
        return

    df = pd.read_csv(link_csv)
    if df.empty:
        return

    if "timestamp" in df.columns:
        df = df.sort_values("timestamp").groupby("link_id", as_index=False).tail(1)

    for col in ["rx_mbps", "tx_mbps", "rx_pps", "tx_pps"]:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    df["link_mbps"] = df[["rx_mbps", "tx_mbps"]].max(axis=1)
    df["link_usage_norm"] = (df["link_mbps"] / capacity).clip(0, 1)
    df["link_monitor"] = (df["link_mbps"] / threshold).clip(0, 1)

    rows = []
    for _, r in df.iterrows():
        rows.append({
            "cycle_id": cid,
            "timestamp": ts,
            "link_id": r.get("link_id", ""),
            "action": action,
            "rx_mbps": r["rx_mbps"],
            "tx_mbps": r["tx_mbps"],
            "rx_pps": r["rx_pps"],
            "tx_pps": r["tx_pps"],
            "link_mbps": r["link_mbps"],
            "link_usage_norm": r["link_usage_norm"],
            "link_monitor": r["link_monitor"],
        })

    _append_csv(LINK_LOG, rows)