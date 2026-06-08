# decision_proactive.py
#
# Scoring formulas
# ────────────────
# IP score (per host h30–h39):
#   S_i^IP = α · κ_i · r_i(t)  −  γ(λ₁·T_i(t) + λ₂/(A_i(t)+1))
#
#   r_i(t)  = rx_pps anomaly  — "is this host being flooded?"
#             |rx_pps(t) − ema_baseline| / (ema_baseline + ε)
#             source: host_stats_onos.csv → rx_pps column
#
#   T_i(t)  = tx_mbps peer-normalised load  — "how disruptive is a shuffle?"
#             tx_mbps(t) / max(tx_mbps across all preset hosts this step)
#             source: host_stats_onos.csv → tx_mbps column
#
#   A_i(t)  = trailing streak (raw steps) from ip_manager history
#   κ_i     = importance rank weight from observability [0.1 – 1.0]
#
# Route score (per h1→hx, hx ∈ h30–h39):
#   S_f^RRM = β₁·κ_f·r_f(t)  +  β₂·φ_f(t)  −  (δ·h_f + μ/(A_f(t)+1))
#
#   r_f(t)  = max link tx_pps anomaly on path  — "is this path being flooded?"
#             blended with route churn rate from history
#             source: link_stats_onos.csv → tx_pps column + route_manager
#
#   φ_f(t)  = max link tx_mbps / network_max_tx_mbps  — "is this path congested?"
#             source: link_stats_onos.csv → tx_mbps column
#
#   h_f     = normalised hop count (current option / max hops in network)
#   A_f(t)  = trailing streak (raw steps) from route_manager history
#   κ_f     = avg(κ_h1=0.65, κ_hx)
#
# Selection
# ─────────
#   Eligibility:  C_IP  = { i : S_IP  > 0,  cooldown ok }
#                 C_RRM = { f : S_RRM > 0,  cooldown ok }
#   Optimize:     sel_ip  = top K_IP  from C_IP   (greedy, score ↓)
#                 sel_rrm = top K_RRM from C_RRM

import csv
import os

# ── Formula weights ────────────────────────────────────────────────────────────
# ALPHA = 1.5     # IP gain scale
# GAMMA = 0.60    # IP cost scale
# LAM1  = 0.05    # T_i weight   (tx_mbps load penalty)
# LAM2  = 0.50    # age penalty  1/(A_i+1)

# BETA1 = 1.2     # route churn/pps-anomaly gain  β₁·κ_f·r_f
# BETA2 = 2.0     # route congestion gain          β₂·φ_f
# DELTA = 0.10    # hop-count cost
# MU    = 0.15    # route recency penalty          μ/(A_f+1)

# # ── Constraints ────────────────────────────────────────────────────────────────
# K_IP  = 1       # max IP shuffles per step
# K_RRM = 3       # max route reroutes per step
# CD    = 3       # cooldown steps  (3 × 30 s = 90 s)
# ── IP weights ─────────────────────────
# ALPHA = 6.0
ALPHA = 7.0
GAMMA = 1.0
LAM1  = 0.03
# LAM2  = 0.8
LAM2  = 1.5

# ── Route weights ──────────────────────
BETA1 = 3.0
BETA2 = 2.3
DELTA = 0.18
MU    = 0.75

# ── Constraints ────────────────────────
K_IP  = 1
K_RRM = 3
CD    = 1

# ── Data files ─────────────────────────────────────────────────────────────────
OBS_FILE        = "observability.csv"
HOP_LIST_FILE   = "hop_list.csv"
HOST_STATS_FILE = "host_stats_onos.csv"
LINK_STATS_FILE = "link_stats_onos.csv"

MAX_TIMESTEP = 2879   # last timestep in observability.csv

# ── Scope ──────────────────────────────────────────────────────────────────────
PRESET_HOSTS     = ["h30","h31","h32","h33","h34","h35","h36","h37","h38","h39"]
ROUTE_CANDIDATES = [("h1", hx) for hx in PRESET_HOSTS]

HOST_TO_SWITCH = {
    "h1":  "s1",
    "h2":  "s2", "h3":  "s2", "h4":  "s2", "h5":  "s2",
    "h6":  "s2", "h7":  "s2", "h8":  "s2",
    "h9":  "s3", "h10": "s3", "h11": "s3", "h12": "s3",
    "h13": "s3", "h14": "s3", "h15": "s3",
    "h16": "s4", "h17": "s4", "h18": "s4", "h19": "s4",
    "h20": "s4", "h21": "s4",
    "h22": "s5", "h23": "s5", "h24": "s5", "h25": "s5",
    "h26": "s5", "h27": "s5",
    "h28": "s6", "h29": "s6", "h30": "s6", "h31": "s6",
    "h32": "s6", "h33": "s6",
    "h34": "s7", "h35": "s7", "h36": "s7", "h37": "s7",
    "h38": "s7", "h39": "s7", "h40": "s7",
}

SKIP_HOSTS = {"h40"}
all_hosts  = [f"h{i}" for i in range(1, 41) if f"h{i}" not in SKIP_HOSTS]

H1_PAIRS = [
    ("h1", hx) for hx in all_hosts
    if hx != "h1" and HOST_TO_SWITCH[hx] != HOST_TO_SWITCH["h1"]
]

# ── EMA baselines (updated every call to decide()) ────────────────────────────
_EMA_ALPHA = 0.3

_host_baseline_rx_pps  = {h: None for h in PRESET_HOSTS}
_link_baseline_tx_pps  = {}   # link_id → float
_link_baseline_tx_mbps = {}   # link_id → float

# MAC → host name (built once from hop_list)
_mac_to_host = {}


def _build_mac_map():
    global _mac_to_host
    if _mac_to_host:
        return
    with open(HOP_LIST_FILE, newline="") as f:
        for row in csv.reader(f):
            if len(row) < 6:
                continue
            _mac_to_host[row[4].strip()] = row[0].strip()
            _mac_to_host[row[5].strip()] = row[1].strip()


def _ema(prev, current):
    if prev is None:
        return current
    return (1 - _EMA_ALPHA) * prev + _EMA_ALPHA * current


# ── ONOS data loaders ──────────────────────────────────────────────────────────

def load_host_stats():
    """
    Reads host_stats_onos.csv (latest timestamp only).
    Returns { host: {'rx_pps': float, 'tx_mbps': float} }
    """
    _build_mac_map()
    rows = []
    with open(HOST_STATS_FILE, newline="") as f:
        for row in csv.DictReader(f):
            host = _mac_to_host.get(row["host_mac"].strip())
            if host in PRESET_HOSTS:
                rows.append((
                    row["timestamp"].strip(), host,
                    float(row["rx_pps"]),
                    float(row["tx_mbps"]),
                ))
    if not rows:
        return {}
    latest_ts = max(r[0] for r in rows)
    return {
        host: {"rx_pps": rx_pps, "tx_mbps": tx_mbps}
        for ts, host, rx_pps, tx_mbps in rows
        if ts == latest_ts
    }


def load_link_stats():
    """
    Reads link_stats_onos.csv (latest timestamp only).
    Returns { link_id: {'tx_pps': float, 'tx_mbps': float} }
    """
    rows = []
    with open(LINK_STATS_FILE, newline="") as f:
        for row in csv.DictReader(f):
            rows.append((
                row["timestamp"].strip(),
                row["link_id"].strip(),
                float(row["tx_pps"]),
                float(row["tx_mbps"]),
            ))
    if not rows:
        return {}
    latest_ts = max(r[0] for r in rows)
    return {
        link_id: {"tx_pps": tx_pps, "tx_mbps": tx_mbps}
        for ts, link_id, tx_pps, tx_mbps in rows
        if ts == latest_ts
    }


def load_observability(i):
    """
    Reads observability.csv at timestep i (loops after MAX_TIMESTEP).
    Returns:
        kappa_map  { 'h35': 1.0, ... }   rank weight [0.1–1.0]
        imp_map    { 'h35': 0.30, ... }   raw importance_score
    """
    target_ts   = i % (MAX_TIMESTEP + 1)
    latest_rows = []
    with open(OBS_FILE, newline="") as f:
        for row in csv.DictReader(f):
            try:
                ts = int(row["timestep"].strip())
            except ValueError:
                continue
            if ts == target_ts:
                latest_rows.append(row)

    if not latest_rows:
        return {}, {}

    n           = len(latest_rows)
    sorted_rows = sorted(latest_rows, key=lambda r: int(r["rank"].strip()))
    kappa_map, imp_map = {}, {}
    for idx, r in enumerate(sorted_rows):
        host = f"h{r['gen_bus'].strip()}"
        kappa_map[host] = round(1.0 - (idx / n) * 0.9, 3)   # rank1→1.0, rankN→0.1
        imp_map[host]   = round(float(r["importance_score"].strip()), 6)

    return kappa_map, imp_map


def load_hop_lookup():
    """Returns { (ha, hb): { option: hop_count } } from hop_list.csv."""
    lookup = {}
    with open(HOP_LIST_FILE, newline="") as f:
        for row in csv.reader(f):
            if len(row) < 4:
                continue
            src, dst = row[0].strip(), row[1].strip()
            try:
                opt  = int(row[2].strip())
                hops = float(row[3].strip())
            except ValueError:
                continue
            lookup.setdefault((src, dst), {})[opt] = hops
    return lookup


# Known link_ids (lazy-loaded once)
_known_links = set()


def _get_known_links():
    global _known_links
    if _known_links:
        return _known_links
    with open(LINK_STATS_FILE, newline="") as f:
        for row in csv.DictReader(f):
            _known_links.add(row["link_id"].strip())
    return _known_links


def _get_path_links(ha, hb, opt=None):
    """
    Returns the resolved link_ids on the path ha→hb.
    Uses opt if given; otherwise the shortest available path.
    Both forward and reverse link_id formats are checked.
    """
    rows = []
    with open(HOP_LIST_FILE, newline="") as f:
        for row in csv.reader(f):
            if len(row) < 7:
                continue
            if row[0].strip() == ha and row[1].strip() == hb:
                rows.append(row)
    if not rows:
        return []

    if opt is not None:
        chosen = [r for r in rows if int(r[2].strip()) == opt]
        if not chosen:
            chosen = rows
    else:
        chosen = sorted(rows, key=lambda r: float(r[3]))

    path_str = chosen[0][6].strip()
    known    = _get_known_links()
    result   = []
    for part in [p.strip() for p in path_str.split(",")]:
        segs = part.split(" -> ")
        if len(segs) != 2:
            continue
        fwd = f"{segs[0].strip()} -> {segs[1].strip()}"
        rev = f"{segs[1].strip()} -> {segs[0].strip()}"
        if fwd in known:
            result.append(fwd)
        elif rev in known:
            result.append(rev)
    return result


# ── History helpers (unchanged from original) ──────────────────────────────────

def trailing_streak(history):
    """Trailing streak normalised [0,1]."""
    values = [v for v in history if v != 0]
    if not values:
        return 0.0
    current = values[-1]
    streak  = sum(1 for _ in iter(lambda: next(
        (None for v in reversed(values) if v != current), 0), 0))
    # simpler loop:
    streak = 0
    for v in reversed(values):
        if v == current:
            streak += 1
        else:
            break
    return streak / len(values)


def trailing_streak_raw(history):
    """Raw trailing streak count — used as A_i in 1/(A_i+1)."""
    values = [v for v in history if v != 0]
    if not values:
        return 0
    current = values[-1]
    streak  = 0
    for v in reversed(values):
        if v == current:
            streak += 1
        else:
            break
    return streak


def last_nonzero(history):
    """Last non-zero value in history, or None."""
    for v in reversed(history):
        if v != 0:
            return v
    return None


def route_churn_rate(history):
    """Fraction of steps where the route option changed."""
    if len(history) < 2:
        return 0.0
    changes = sum(1 for i in range(1, len(history)) if history[i] != history[i-1])
    return changes / (len(history) - 1)


# ── Per-host IP scoring ────────────────────────────────────────────────────────

def score_ip_hosts(ip_manager, kappa_map, host_stats, cooldown_state):
    """
    S_i^IP = α·κ_i·r_i  −  γ(λ₁·T_i + λ₂/(A_i+1))

    r_i  from host_stats rx_pps  (EMA anomaly)
    T_i  from host_stats tx_mbps (peer-normalised load)
    A_i  from ip_manager history (trailing streak raw count)
    """
    global _host_baseline_rx_pps

    tx_vals = {h: host_stats.get(h, {}).get("tx_mbps", 0.001) for h in PRESET_HOSTS}
    max_tx  = max(tx_vals.values()) if max(tx_vals.values()) > 0 else 1e-9

    results = []
    for host in PRESET_HOSTS:
        stats  = host_stats.get(host, {})
        rx_pps = stats.get("rx_pps",  0.0)
        tx_mbps= stats.get("tx_mbps", 0.001)

        # Update EMA baseline for rx_pps
        _host_baseline_rx_pps[host] = _ema(_host_baseline_rx_pps[host], rx_pps)
        base_rx = _host_baseline_rx_pps[host]

        # r_i: rx_pps anomaly vs rolling baseline
        r_i = min(1.0, abs(rx_pps - base_rx) / (base_rx + 1e-9))

        # T_i: tx_mbps peer-normalised (operational load)
        T_i = tx_mbps / max_tx

        # A_i: raw trailing streak (IP age)
        hist = ip_manager.get_host_ips(host)
        A_i  = trailing_streak_raw(hist)

        kappa = kappa_map.get(host, 0.5)
        gain  = ALPHA * kappa * r_i
        cost  = GAMMA * (LAM1 * T_i + LAM2 / (A_i + 1))
        score = round(gain - cost, 5)

        cd_remaining = cooldown_state["ip"].get(host, 0)
        eligible     = score > 0 and cd_remaining == 0

        results.append({
            "host":         host,
            "score":        score,
            "gain":         round(gain, 5),
            "cost":         round(cost, 5),
            "kappa":        kappa,
            "r_i":          round(r_i, 5),
            "T_i":          round(T_i, 5),
            "A_i":          A_i,
            "rx_pps":       round(rx_pps, 4),
            "tx_mbps":      round(tx_mbps, 5),
            "base_rx_pps":  round(base_rx, 5),
            "eligible":     eligible,
            "cd_remaining": cd_remaining,
        })

    return sorted(results, key=lambda x: -x["score"])


# ── Per-route RRM scoring ──────────────────────────────────────────────────────

def score_rrm_routes(route_manager, kappa_map, link_stats, hop_lookup, cooldown_state):
    """
    S_f^RRM = β₁·κ_f·r_f  +  β₂·φ_f  −  (δ·h_f + μ/(A_f+1))

    r_f  = 0.5·link_pps_anomaly + 0.5·route_churn_rate
    φ_f  = max link tx_mbps / network_max   (from link_stats)
    h_f  = normalised hop count
    A_f  = trailing streak raw count from route_manager
    """
    global _link_baseline_tx_pps, _link_baseline_tx_mbps

    # Update EMA baselines for all links
    for lid, stats in link_stats.items():
        _link_baseline_tx_pps[lid]  = _ema(_link_baseline_tx_pps.get(lid),  stats["tx_pps"])
        _link_baseline_tx_mbps[lid] = _ema(_link_baseline_tx_mbps.get(lid), stats["tx_mbps"])

    max_link_mbps = max(
        (s["tx_mbps"] for s in link_stats.values()),
        default=1e-9,
    )
    if max_link_mbps < 1e-9:
        max_link_mbps = 1e-9

    all_hops  = [h for a, b in ROUTE_CANDIDATES for h in hop_lookup.get((a, b), {}).values()]
    min_hops  = min(all_hops) if all_hops else 1.0
    max_hops  = max(all_hops) if all_hops else 1.0

    kappa_h1 = 0.65   # h1 not in observability

    results = []
    for a, b in ROUTE_CANDIDATES:
        hist      = route_manager.get_pair_history(a, b)
        A_f       = trailing_streak_raw(hist)
        churn     = route_churn_rate(hist)
        last_opt  = last_nonzero(hist)

        opt_map  = hop_lookup.get((a, b), hop_lookup.get((b, a), {}))
        cur_hops = (
            opt_map.get(last_opt)
            if last_opt is not None and last_opt in opt_map
            else (sum(opt_map.values()) / len(opt_map) if opt_map else (min_hops + max_hops) / 2)
        )
        h_f = (cur_hops - min_hops) / (max_hops - min_hops) if max_hops != min_hops else 0.0

        # Path links
        path_links = _get_path_links(a, b, opt=last_opt)

        # r_f: link tx_pps anomaly on path
        r_f_link = 0.0
        for lid in path_links:
            base_pps = _link_baseline_tx_pps.get(lid, 0.0)
            cur_pps  = link_stats.get(lid, {}).get("tx_pps", 0.0)
            if base_pps > 1e-9:
                r_f_link = max(r_f_link, min(1.0, abs(cur_pps - base_pps) / base_pps))

        r_f = min(1.0, 0.5 * r_f_link + 0.5 * churn)

        # φ_f: max link tx_mbps congestion on path
        phi_f = 0.0
        for lid in path_links:
            cur_mbps = link_stats.get(lid, {}).get("tx_mbps", 0.0)
            phi_f    = max(phi_f, cur_mbps / max_link_mbps)

        kappa_b = kappa_map.get(b, 0.5)
        kappa_f = (kappa_h1 + kappa_b) / 2

        gain  = BETA1 * kappa_f * r_f + BETA2 * phi_f
        cost  = DELTA * h_f + MU / (A_f + 1)
        score = round(gain - cost, 5)

        cd_remaining = cooldown_state["rrm"].get((a, b), 0)
        eligible     = score > 0 and cd_remaining == 0

        results.append({
            "pair":         (a, b),
            "score":        score,
            "gain":         round(gain, 5),
            "cost":         round(cost, 5),
            "kappa_f":      round(kappa_f, 3),
            "r_f":          round(r_f, 5),
            "phi_f":        round(phi_f, 5),
            "h_f":          round(h_f, 4),
            "A_f":          A_f,
            "path_links":   path_links,
            "eligible":     eligible,
            "cd_remaining": cd_remaining,
        })

    return sorted(results, key=lambda x: -x["score"])


# ── Main decide function ───────────────────────────────────────────────────────

def decide(ip_manager, route_manager, i, cooldown_state):
    """
    Full scoring + selection cycle for one 30s step.

    Returns
    ───────
    sel_ip     list[str]     hosts selected for IP shuffle  (len ≤ K_IP)
    sel_rrm    list[tuple]   pairs selected for reroute     (len ≤ K_RRM)
    c_ip       list[dict]    eligible IP candidates (sorted ↓)
    c_rrm      list[dict]    eligible route candidates (sorted ↓)
    ip_scores  list[dict]    all host scores
    rrm_scores list[dict]    all route scores
    """
    kappa_map, _    = load_observability(i)
    host_stats      = load_host_stats()
    link_stats      = load_link_stats()
    hop_lookup      = load_hop_lookup()

    ip_scores  = score_ip_hosts(ip_manager, kappa_map, host_stats, cooldown_state)
    rrm_scores = score_rrm_routes(route_manager, kappa_map, link_stats, hop_lookup, cooldown_state)

    # Eligibility filter
    c_ip  = [s for s in ip_scores  if s["eligible"]]
    c_rrm = [s for s in rrm_scores if s["eligible"]]

    # Greedy top-K
    sel_ip  = [s["host"] for s in c_ip[:K_IP]]
    sel_rrm = [s["pair"] for s in c_rrm[:K_RRM]]

    blocked_ip  = [s["host"] for s in c_ip[K_IP:]]
    blocked_rrm = [s["pair"] for s in c_rrm[K_RRM:]]

    obj = (sum(s["score"] for s in c_ip[:K_IP])
         + sum(s["score"] for s in c_rrm[:K_RRM]))

    print(f"  [SCORE]  "
          f"C_IP={[s['host'] for s in c_ip]}  sel_IP={sel_ip}  "
          f"C_RRM={[s['pair'] for s in c_rrm]}  sel_RRM={sel_rrm}  "
          f"obj={obj:+.4f}")
    if blocked_ip:
        print(f"  [BLOCKED IP]   K={K_IP} full → {blocked_ip}")
    if blocked_rrm:
        print(f"  [BLOCKED RRM]  K={K_RRM} full → {blocked_rrm}")

    return sel_ip, sel_rrm, c_ip, c_rrm, ip_scores, rrm_scores


# ── Logging ───────────────────────────────────────────────────────────────────

def log_decision_items(
    ip_manager, route_manager, i,
    sel_ip=None, sel_rrm=None,
    c_ip=None, c_rrm=None,
    ip_scores=None, rrm_scores=None,
    action_taken=None,
    dataset_file="decision_dataset.csv",
):
    """
    Appends one row per 30s step to decision_dataset.csv.

    Columns
    ───────
    timestep
    action_taken             'ip' | 'route' | 'both' | 'none'

    IP side
    ───────
    sel_ip_hosts             hosts actually shuffled    e.g. "h32"
    c_ip_hosts               eligible candidates        e.g. "h32,h35,h30"
    ip_top1_host             highest-scoring host
    ip_top1_score
    ip_top1_r_i              rx_pps anomaly of top-1
    ip_top1_T_i              tx_mbps load of top-1
    ip_top1_kappa
    ip_top1_A_i              IP age (raw trailing streak steps)
    ip_mean_score
    ip_mean_r_i
    ip_mean_T_i
    ip_mean_kappa

    Route side
    ──────────
    sel_rrm_pairs            pairs actually rerouted    e.g. "h1-h32;h1-h35"
    c_rrm_pairs              eligible candidates        e.g. "h1-h32;h1-h35;h1-h30"
    rrm_top1_pair
    rrm_top1_score
    rrm_top1_r_f             path pps anomaly blend of top-1
    rrm_top1_phi_f           path congestion of top-1
    rrm_top1_kappa_f
    rrm_top1_A_f             route age (raw trailing streak steps)
    rrm_mean_score
    rrm_mean_r_f
    rrm_mean_phi_f
    rrm_mean_kappa_f
    """
    sel_ip     = sel_ip     or []
    sel_rrm    = sel_rrm    or []
    c_ip       = c_ip       or []
    c_rrm      = c_rrm      or []
    ip_scores  = ip_scores  or []
    rrm_scores = rrm_scores or []

    def _mean(lst):
        return round(sum(lst) / len(lst), 5) if lst else 0.0

    ip_top1  = ip_scores[0]  if ip_scores  else {}
    rrm_top1 = rrm_scores[0] if rrm_scores else {}

    row = {
        "timestep":      i,
        "action_taken":  action_taken or "none",

        # ── IP ────────────────────────────────────────────────────────────
        "sel_ip_hosts":  ",".join(sel_ip) if sel_ip else "none",
        "c_ip_hosts":    ",".join(s["host"] for s in c_ip) if c_ip else "none",
        "ip_top1_host":  ip_top1.get("host", ""),
        "ip_top1_score": round(ip_top1.get("score",  0.0), 5),
        "ip_top1_r_i":   round(ip_top1.get("r_i",    0.0), 5),
        "ip_top1_T_i":   round(ip_top1.get("T_i",    0.0), 5),
        "ip_top1_kappa": round(ip_top1.get("kappa",  0.0), 3),
        "ip_top1_A_i":   ip_top1.get("A_i", 0),
        "ip_mean_score": _mean([s["score"] for s in ip_scores]),
        "ip_mean_r_i":   _mean([s["r_i"]   for s in ip_scores]),
        "ip_mean_T_i":   _mean([s["T_i"]   for s in ip_scores]),
        "ip_mean_kappa": _mean([s["kappa"]  for s in ip_scores]),

        # ── Route ─────────────────────────────────────────────────────────
        "sel_rrm_pairs":    ";".join(f"{a}-{b}" for a, b in sel_rrm) if sel_rrm else "none",
        "c_rrm_pairs":      ";".join(f"{s['pair'][0]}-{s['pair'][1]}" for s in c_rrm) if c_rrm else "none",
        "rrm_top1_pair":    (f"{rrm_top1['pair'][0]}-{rrm_top1['pair'][1]}"
                             if rrm_top1 and "pair" in rrm_top1 else ""),
        "rrm_top1_score":   round(rrm_top1.get("score",   0.0), 5),
        "rrm_top1_r_f":     round(rrm_top1.get("r_f",     0.0), 5),
        "rrm_top1_phi_f":   round(rrm_top1.get("phi_f",   0.0), 5),
        "rrm_top1_kappa_f": round(rrm_top1.get("kappa_f", 0.0), 3),
        "rrm_top1_A_f":     rrm_top1.get("A_f", 0),
        "rrm_mean_score":   _mean([s["score"]   for s in rrm_scores]),
        "rrm_mean_r_f":     _mean([s["r_f"]     for s in rrm_scores]),
        "rrm_mean_phi_f":   _mean([s["phi_f"]   for s in rrm_scores]),
        "rrm_mean_kappa_f": _mean([s["kappa_f"] for s in rrm_scores]),
    }

    file_exists = os.path.exists(dataset_file)
    with open(dataset_file, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    # ── Selection log (who was selected, when, and their score) ───────────────
    _write_selection_log(i, sel_ip, sel_rrm, ip_scores, rrm_scores, action_taken)


# def _write_selection_log(
#     i, sel_ip, sel_rrm, ip_scores, rrm_scores, action_taken,
#     selection_log_file="selection_log.csv",
# ):
#     """
#     Lightweight per-selection log.  One row per selected host or route pair.

#     Columns
#     ───────
#     timestep      step index
#     action        'ip' or 'route'
#     selected      host name (e.g. h32) or pair (e.g. h1-h35)
#     score         S_IP or S_RRM of the selected candidate
#     kappa         κ_i (host) or κ_f (route)
#     anomaly       r_i (rx_pps anomaly) or r_f (path pps anomaly)
#     load_cong     T_i (tx_mbps load) or φ_f (path congestion)
#     age           A_i or A_f (trailing streak steps)

#     Console line (always printed):
#     [SEL] step=4  IP: h32 (S=+0.31, κ=0.80, r=0.41, A=3)
#     [SEL] step=4  RRM: h1-h35 (S=+0.22, κ=0.73, r=0.33, A=5)
#     """
#     import datetime

#     # Build score lookup maps
#     ip_lookup  = {s["host"]: s for s in (ip_scores  or [])}
#     rrm_lookup = {s["pair"]: s for s in (rrm_scores or [])}

#     rows = []

#     for host in (sel_ip or []):
#         s = ip_lookup.get(host, {})
#         score   = s.get("score",  0.0)
#         kappa   = s.get("kappa",  0.0)
#         r_i     = s.get("r_i",   0.0)
#         T_i     = s.get("T_i",   0.0)
#         A_i     = s.get("A_i",   0)
#         rows.append({
#             "timestep":  i,
#             "action":    "ip",
#             "selected":  host,
#             "score":     round(score, 5),
#             "kappa":     round(kappa, 3),
#             "anomaly":   round(r_i,   5),
#             "load_cong": round(T_i,   5),
#             "age":       A_i,
#         })
#         print(f"  [SEL] step={i}  IP : {host} "
#               f"(S={score:+.4f}  κ={kappa:.2f}  r_i={r_i:.4f}  T_i={T_i:.4f}  A={A_i})")

#     for pair in (sel_rrm or []):
#         s = rrm_lookup.get(pair, {})
#         score   = s.get("score",   0.0)
#         kappa_f = s.get("kappa_f", 0.0)
#         r_f     = s.get("r_f",     0.0)
#         phi_f   = s.get("phi_f",   0.0)
#         A_f     = s.get("A_f",     0)
#         label   = f"{pair[0]}-{pair[1]}"
#         rows.append({
#             "timestep":  i,
#             "action":    "route",
#             "selected":  label,
#             "score":     round(score,   5),
#             "kappa":     round(kappa_f, 3),
#             "anomaly":   round(r_f,     5),
#             "load_cong": round(phi_f,   5),
#             "age":       A_f,
#         })
#         print(f"  [SEL] step={i}  RRM: {label} "
#               f"(S={score:+.4f}  κ={kappa_f:.2f}  r_f={r_f:.4f}  φ={phi_f:.4f}  A={A_f})")

#     if not rows:
#         print(f"  [SEL] step={i}  no action (all scores ≤ 0 or in cooldown)")

#     # Write to CSV
#     file_exists = os.path.exists(selection_log_file)
#     with open(selection_log_file, "a", newline="") as f:
#         writer = csv.DictWriter(f, fieldnames=["timestep","action","selected",
#                                                "score","kappa","anomaly",
#                                                "load_cong","age"])
#         if not file_exists:
#             writer.writeheader()
#         writer.writerows(rows)

def _write_selection_log(
    i, sel_ip, sel_rrm, ip_scores, rrm_scores, action_taken,
    ip_matrix_file="ip_selection_matrix.csv",
    rrm_matrix_file="rrm_selection_matrix.csv",
):
    """
    Writes two matrix-style CSVs — one for IP, one for routes.
    Each call appends ONE ROW (= one step) to each file.

    ip_selection_matrix.csv
    ───────────────────────
    Columns: step | h30_score | h30_kappa | h30_r_i | h30_T_i | h30_age | h30_status | h31_... | ...
    status:  SELECTED | BLOCKED | COOLDOWN(n) | below0

    rrm_selection_matrix.csv
    ────────────────────────
    Columns: step | h1-h30_score | h1-h30_kappa_f | h1-h30_r_f | h1-h30_phi_f | h1-h30_age | h1-h30_status | ...
    status:  SELECTED | BLOCKED | COOLDOWN(n) | below0

    Console: compact matrix table printed each step.
    """

    sel_ip_set  = set(sel_ip  or [])
    sel_rrm_set = set(tuple(p) for p in (sel_rrm or []))

    ip_lookup  = {s["host"]: s        for s in (ip_scores  or [])}
    rrm_lookup = {tuple(s["pair"]): s for s in (rrm_scores or [])}

    def _ip_status(host):
        if host in sel_ip_set:
            return "SELECTED"
        s  = ip_lookup.get(host, {})
        cd = s.get("cd_remaining", 0)
        if cd > 0:
            return f"COOLDOWN({cd})"
        if s.get("score", -1) > 0:
            return "BLOCKED"
        return "below0"

    def _rrm_status(pair):
        if pair in sel_rrm_set:
            return "SELECTED"
        s  = rrm_lookup.get(pair, {})
        cd = s.get("cd_remaining", 0)
        if cd > 0:
            return f"COOLDOWN({cd})"
        if s.get("score", -1) > 0:
            return "BLOCKED"
        return "below0"

    # ── IP matrix row ──────────────────────────────────────────────────────────
    ip_row = {"step": i}
    for host in PRESET_HOSTS:
        s = ip_lookup.get(host, {})
        ip_row[f"{host}_score"]  = round(s.get("score", 0.0), 4)
        ip_row[f"{host}_kappa"]  = round(s.get("kappa", 0.0), 3)
        ip_row[f"{host}_r_i"]    = round(s.get("r_i",   0.0), 4)
        ip_row[f"{host}_T_i"]    = round(s.get("T_i",   0.0), 4)
        ip_row[f"{host}_age"]    = s.get("A_i", 0)
        ip_row[f"{host}_status"] = _ip_status(host)

    ip_exists = os.path.exists(ip_matrix_file)
    with open(ip_matrix_file, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(ip_row.keys()))
        if not ip_exists:
            writer.writeheader()
        writer.writerow(ip_row)

    # ── RRM matrix row ─────────────────────────────────────────────────────────
    rrm_row = {"step": i}
    for a, b in ROUTE_CANDIDATES:
        pair  = (a, b)
        label = f"{a}-{b}"
        s = rrm_lookup.get(pair, {})
        rrm_row[f"{label}_score"]   = round(s.get("score",   0.0), 4)
        rrm_row[f"{label}_kappa_f"] = round(s.get("kappa_f", 0.0), 3)
        rrm_row[f"{label}_r_f"]     = round(s.get("r_f",     0.0), 4)
        rrm_row[f"{label}_phi_f"]   = round(s.get("phi_f",   0.0), 4)
        rrm_row[f"{label}_age"]     = s.get("A_f", 0)
        rrm_row[f"{label}_status"]  = _rrm_status(pair)

    rrm_exists = os.path.exists(rrm_matrix_file)
    with open(rrm_matrix_file, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rrm_row.keys()))
        if not rrm_exists:
            writer.writeheader()
        writer.writerow(rrm_row)

    # ── Console matrix ─────────────────────────────────────────────────────────
    W = 11

    print(f"\n  ┌─ IP matrix  step={i} {'─'*60}")
    print(f"  │ {'host':<6} {'score':>{W}} {'κ':>{W}} {'r_i':>{W}} {'T_i':>{W}} {'age':>{W}}  status")
    print(f"  │ {'─'*6} {'─'*W} {'─'*W} {'─'*W} {'─'*W} {'─'*W}  {'─'*14}")
    for host in PRESET_HOSTS:
        s      = ip_lookup.get(host, {})
        status = _ip_status(host)
        marker = " ◀" if status == "SELECTED" else ("  ~" if "COOLDOWN" in status else "")
        print(f"  │ {host:<6} "
              f"{s.get('score', 0.0):>{W}.4f} "
              f"{s.get('kappa', 0.0):>{W}.3f} "
              f"{s.get('r_i',   0.0):>{W}.4f} "
              f"{s.get('T_i',   0.0):>{W}.4f} "
              f"{s.get('A_i',   0):>{W}}  "
              f"{status:<14}{marker}")
    print(f"  └{'─'*80}")

    print(f"\n  ┌─ RRM matrix  step={i} {'─'*60}")
    print(f"  │ {'pair':<10} {'score':>{W}} {'κ_f':>{W}} {'r_f':>{W}} {'φ_f':>{W}} {'age':>{W}}  status")
    print(f"  │ {'─'*10} {'─'*W} {'─'*W} {'─'*W} {'─'*W} {'─'*W}  {'─'*14}")
    for a, b in ROUTE_CANDIDATES:
        pair   = (a, b)
        label  = f"{a}-{b}"
        s      = rrm_lookup.get(pair, {})
        status = _rrm_status(pair)
        marker = " ◀" if status == "SELECTED" else ("  ~" if "COOLDOWN" in status else "")
        print(f"  │ {label:<10} "
              f"{s.get('score',   0.0):>{W}.4f} "
              f"{s.get('kappa_f', 0.0):>{W}.3f} "
              f"{s.get('r_f',     0.0):>{W}.4f} "
              f"{s.get('phi_f',   0.0):>{W}.4f} "
              f"{s.get('A_f',     0):>{W}}  "
              f"{status:<14}{marker}")
    print(f"  └{'─'*80}")