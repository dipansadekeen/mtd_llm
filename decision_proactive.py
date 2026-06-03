# decision_proactive.py

# from main_controller import ip_manager, route_manager
import csv, os

# ── Weights & Costs ───────────────────────────────────────────────────
WEIGHT_AGE  = 0.7
WEIGHT_OBS  = 0.3
WEIGHT_AGE_RRM  = 0.7
WEIGHT_OBS_RRM  = 0.3
HOP_PENALTY = 0.08
COST_IP     = 0.50
COST_RRM    = 0.10

# WEIGHT_AGE  = 0.9
# WEIGHT_OBS  = 0.6
# WEIGHT_AGE_RRM  = 0.8
# WEIGHT_OBS_RRM  = 0.38

# HOP_PENALTY = 0.08
# COST_IP     = 0.50
# COST_RRM    = 0.10


# ─────────────────────────────────────────────────────────────────────

OBS_FILE     = "observability.csv"
HOP_LIST_FILE = "hop_list.csv"

PRESET_HOSTS = ["h30", "h31", "h32", "h33", "h34", "h35", "h36", "h37", "h38", "h39"]

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
 
# All h1-hx pairs across different switches
H1_PAIRS = [
    ("h1", hx) for hx in all_hosts
    if hx != "h1" and HOST_TO_SWITCH[hx] != HOST_TO_SWITCH["h1"]
]
 
 
# ── Helpers ───────────────────────────────────────────────────────────
 
def trailing_streak(history):
    """Trailing streak of last non-zero value, normalised to [0,1]. Used for age."""
    values = [v for v in history if v != 0]
    if not values:
        return 0.0
    current = values[-1]
    streak = 0
    for v in reversed(values):
        if v == current:
            streak += 1
        else:
            break
    return streak / len(values)
 
 
def last_nonzero(history):
    """Last non-zero value in history, or None."""
    for v in reversed(history):
        if v != 0:
            return v
    return None
 
MAX_TIMESTEP = 2879   # last timestep in observability.csv

def load_observability(i):
    """
    Reads observability.csv, uses only the latest timestep.
    gen_bus=35 → h35. rank 1 (most observable) → 1.0, lowest → 0.0.
    Returns { 'h35': 1.0, 'h33': 0.89, ... }
    """
    target_ts   = i % (MAX_TIMESTEP + 1)   # loop back after 2879
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
        return {}
 
    ranks    = [int(r["rank"].strip()) for r in latest_rows]
    max_rank, min_rank = max(ranks), min(ranks)
 
    return {
        f"h{r['gen_bus'].strip()}": round(
            (max_rank - int(r["rank"].strip())) / (max_rank - min_rank)
            if max_rank != min_rank else 1.0, 6
        )
        for r in latest_rows
    }
 
 
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
            # for key in [(src, dst), (dst, src)]:
            #     lookup.setdefault(key, {})[opt] = hops
            lookup.setdefault((src, dst), {})[opt] = hops
    return lookup
 
 
# ── Decision ──────────────────────────────────────────────────────────
#
#  I_ip  = 0.7 * age + 0.3 * obs                          - cost_ip
#  I_rrm = 0.7 * age + 0.3 * obs - 0.3 * norm_hops       - cost_rrm
#
#  returns 'ip' or 'route'
# ─────────────────────────────────────────────────────────────────────
 
def decide(ip_manager, route_manager,i):
    obs_map = load_observability(i)
    hop_lookup = load_hop_lookup()
 
    # ── I_ip : mean over all PRESET_HOSTS ────────────────────────────
    ip_scores = []
    for host in PRESET_HOSTS:
        hist = ip_manager.get_host_ips(host)
        age  = trailing_streak(hist)
        obs  = obs_map.get(host, 0.0)
        ip_scores.append(WEIGHT_AGE * age + WEIGHT_OBS * obs - COST_IP)
 
    mean_ip = sum(ip_scores) / len(ip_scores)
 
    # ── I_rrm : mean over all H1_PAIRS ───────────────────────────────
    all_hops  = [h for a, b in H1_PAIRS for h in hop_lookup.get((a, b), {}).values()]
    min_hops  = min(all_hops) if all_hops else 1.0
    max_hops  = max(all_hops) if all_hops else 1.0
 
    rrm_scores = []
    for a, b in H1_PAIRS:
        hist     = route_manager.get_pair_history(a, b)
        age      = trailing_streak(hist)
        obs      = (obs_map.get(a, 0.0) + obs_map.get(b, 0.0)) / 2
        opt_map  = hop_lookup.get((a, b), {})
        last_opt = last_nonzero(hist)
        cur_hops = (
            opt_map.get(last_opt)
            if last_opt is not None and last_opt in opt_map
            else (sum(opt_map.values()) / len(opt_map) if opt_map else (min_hops + max_hops) / 2)
        )
        norm_hops = (cur_hops - min_hops) / (max_hops - min_hops) if max_hops != min_hops else 0.0
        rrm_scores.append(WEIGHT_AGE_RRM * age + WEIGHT_OBS_RRM * obs - HOP_PENALTY * norm_hops - COST_RRM)
 
    mean_rrm = sum(rrm_scores) / len(rrm_scores)
 
    decision = "ip" if mean_ip > mean_rrm else "route"
    print(f"  [DECISION]  I_ip={mean_ip:.4f}   I_rrm={mean_rrm:.4f}   → {'IP SHUFFLE' if decision == 'ip' else 'ROUTE MUTATE'}")
    return decision,  mean_ip, mean_rrm

# def log_decision_items(ip_manager, route_manager, i, dataset_file="decision_dataset.csv"):
# def log_decision_items(ip_manager, route_manager, i, action_taken=None, dataset_file="decision_dataset.csv"):
def log_decision_items(ip_manager, route_manager, i, action_taken=None, I_ip=None, I_rrm=None, dataset_file="decision_dataset.csv"):
    import csv
    import os

    obs_map = load_observability(i)
    hop_lookup = load_hop_lookup()

    # ── IP side ─────────────────────────────────────────────
    ip_scores = []
    ip_ages = []
    ip_obs_vals = []

    for host in PRESET_HOSTS:
        hist = ip_manager.get_host_ips(host)
        age = trailing_streak(hist)
        obs = obs_map.get(host, 0.0)

        ip_ages.append(age)
        ip_obs_vals.append(obs)
        ip_scores.append(WEIGHT_AGE * age + WEIGHT_OBS * obs - COST_IP)

    ip_mean_age = sum(ip_ages) / len(ip_ages) if ip_ages else 0.0
    ip_mean_obs = sum(ip_obs_vals) / len(ip_obs_vals) if ip_obs_vals else 0.0
    mean_ip = sum(ip_scores) / len(ip_scores) if ip_scores else 0.0

    # ── Route side ──────────────────────────────────────────
    # route_pairs = [("h1", hx) for hx in PRESET_HOSTS if hx != "h1"]
    route_pairs = H1_PAIRS

    all_hops = []
    for a, b in route_pairs:
        all_hops.extend(hop_lookup.get((a, b), {}).values())

    min_hops = min(all_hops) if all_hops else 1.0
    max_hops = max(all_hops) if all_hops else 1.0

    rrm_scores = []
    route_ages = []
    route_obs_vals = []
    route_norm_hops_vals = []

    for a, b in route_pairs:
        hist = route_manager.get_pair_history(a, b)
        age = trailing_streak(hist)
        obs = (obs_map.get(a, 0.0) + obs_map.get(b, 0.0)) / 2

        opt_map = hop_lookup.get((a, b), {})
        last_opt = last_nonzero(hist)

        cur_hops = (
            opt_map.get(last_opt)
            if last_opt is not None and last_opt in opt_map
            else (sum(opt_map.values()) / len(opt_map) if opt_map else (min_hops + max_hops) / 2)
        )

        norm_hops = (
            (cur_hops - min_hops) / (max_hops - min_hops)
            if max_hops != min_hops else 0.0
        )

        route_ages.append(age)
        route_obs_vals.append(obs)
        route_norm_hops_vals.append(norm_hops)

        rrm_scores.append(
            WEIGHT_AGE_RRM * age +
            WEIGHT_OBS_RRM * obs -
            HOP_PENALTY * norm_hops -
            COST_RRM
        )

    route_mean_age = sum(route_ages) / len(route_ages) if route_ages else 0.0
    route_mean_obs = sum(route_obs_vals) / len(route_obs_vals) if route_obs_vals else 0.0
    route_mean_norm_hops = (
        sum(route_norm_hops_vals) / len(route_norm_hops_vals)
        if route_norm_hops_vals else 0.0
    )
    mean_rrm = sum(rrm_scores) / len(rrm_scores) if rrm_scores else 0.0

    # decision = "ip" if mean_ip > mean_rrm else "route"

    # row = {
    #     "timestep": i,
    #     "ip_mean_age": ip_mean_age,
    #     "ip_mean_obs": ip_mean_obs,
    #     "route_mean_age": route_mean_age,
    #     "route_mean_obs": route_mean_obs,
    #     "route_mean_norm_hops": route_mean_norm_hops,
    #     "mean_ip_score": mean_ip,
    #     "mean_rrm_score": mean_rrm,
    #     # "decision": decision,
    #     "decision": action_taken,
    # }

    # row = {
    #     "timestep": i,
    #     "ip_mean_age": ip_mean_age,
    #     "ip_mean_obs": ip_mean_obs,
    #     "route_mean_age": route_mean_age,
    #     "route_mean_obs": route_mean_obs,
    #     "route_mean_norm_hops": route_mean_norm_hops,
    #     "I_ip": I_ip if I_ip is not None else mean_ip,
    #     "I_rrm": I_rrm if I_rrm is not None else mean_rrm,
    #     "decision": action_taken,
    # }
    row = {
        "timestep": i,
        "ip_mean_age": round(ip_mean_age, 2),
        "ip_mean_obs": round(ip_mean_obs, 2),
        "route_mean_age": round(route_mean_age, 2),
        "route_mean_obs": round(route_mean_obs, 2),
        "route_mean_norm_hops": round(route_mean_norm_hops, 2),
        "I_ip": round(I_ip if I_ip is not None else mean_ip, 2),
        "I_rrm": round(I_rrm if I_rrm is not None else mean_rrm, 2),
        "decision": action_taken,
    }

    file_exists = os.path.exists(dataset_file)
    fieldnames = list(row.keys())

    with open(dataset_file, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)