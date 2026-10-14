# module_llm_prompts.py

import json
import pandas as pd
from datetime import datetime
TOPOLOGY_FILE = "topology_s10.txt"
from module_llm_helper import build_host_stats, build_link_stats, now_iso

FINAL_PROMPT_FILE = "module_prompt.txt"


def load_prompt_template(path=FINAL_PROMPT_FILE):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

# ===================== CELL 1: build HOST-focused scene + store what will be shown to LLM =====================
HOST_CSV = "host_stats_onos.csv"          # <-- your host stats CSV
HOST_META = "host_metadata.json"    # <-- optional (mac->host mapping)
WINDOW_MINUTES = 5
TREND_POINTS = 10
SCENE_LOG = "llm_scene_log.jsonl"
DECISION_LOG = "llm_decision_log.jsonl"
LINK_CSV = "link_stats_onos.csv"


def build_host_scene_and_prompt(model_name="gpt-oss:20b-cloud", last_k_decisions=10):
    # ---- read host stats ----
    df = pd.read_csv(HOST_CSV)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])

    if df.empty:
        return None, None

    # ---- filter last WINDOW_MINUTES ----
    t_end = df["timestamp"].max()
    t_min = t_end - pd.Timedelta(minutes=WINDOW_MINUTES)
    dfw = df[df["timestamp"] >= t_min].copy()
    if dfw.empty:
        return None, None

    # ---- metadata ----
    try:
        with open(HOST_META, "r", encoding="utf-8") as f:
            host_meta_obj = json.load(f)
    except FileNotFoundError:
        host_meta_obj = {"note": f"{HOST_META} not found"}

    # ---- build host stats via separate function ----
    hosts = build_host_stats(dfw, trend_points=TREND_POINTS)

    #///// filter //////
    hosts = [
        {
            "mac": h["mac"],
            "tx_pps_trend": h["tx_pps_trend"],
            "rx_pps_trend": h["rx_pps_trend"],
            "tx_kbps_trend": h["tx_kbps_trend"],
            "rx_kbps_trend": h["rx_kbps_trend"]
        }
        for h in hosts
    ]

    # ---- last K decisions ----
    last_decisions = []
    try:
        with open(DECISION_LOG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    last_decisions.append(json.loads(line))
        last_decisions = last_decisions[-last_k_decisions:]
    except FileNotFoundError:
        last_decisions = []

    # ---- HOST-level scene (what we show to LLM) ----
    scene = {
        "ts": now_iso(),
        "window_minutes": WINDOW_MINUTES,
        "trend_points": TREND_POINTS,
        "window_end_time": str(t_end),
        "counts": {
            "unique_host_macs": int(len(hosts)),
            "raw_rows_in_window": int(len(df)),
        },
        "host_metadata": host_meta_obj,
        "host_stats": hosts,
        "last_decisions": last_decisions
    }
    prompt = f"""
You are an SDN network anomaly detection function. You need to decide on the below task.

Task:
Select host MAC addresses that show DDoS-like behavior.

DDoS-like indicators:
- very high tx_pps_trend or rx_pps_trend
- sudden spike in tx_pps_trend or rx_pps_trend
- sustained high packet rate across multiple trend points
- high PPS with relatively low or moderate kbps
- clear deviation from most other hosts in the same window

Do NOT require both tx and rx to be abnormal.
A host may be suspicious from either tx-side or rx-side behavior alone.

If no host shows DDoS-like behavior, choose do_nothing.

Return ONLY valid JSON.

Output Schema:
{{
"decision": "ip_shuffle | do_nothing",
"macs_to_shuffle": ["MAC_ADDRESS"],
"confidence": 0.0,
"observation": [
{{"mac":"MAC_ADDRESS","reason":"short_reason"}}
]
}}

Rules:
- Do NOT explain anything.
- Do NOT repeat the input.
- Only return JSON.
- JSON must start with '{{' and end with '}}'.

You have to observe the host stats and output the finding. You must follow the Rules and must respond in json file.
host_stats:
{json.dumps(hosts)}

Return JSON.
""".strip()

    # ---- log exactly what LLM saw ----
    with open(SCENE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": now_iso(),
            "model": model_name,
            "scene": scene,
            "prompt": prompt
        }) + "\n")

    # print(prompt) #temp
    return scene, prompt



def build_link_scene_and_prompt(model_name="gpt-oss:20b-cloud", last_k_decisions=10):
    df = pd.read_csv(LINK_CSV)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])

    if df.empty:
        return None, None

    # --- filter last WINDOW_MINUTES ---
    t_end = df["timestamp"].max()
    t_min = t_end - pd.Timedelta(minutes=WINDOW_MINUTES)
    dfw = df[df["timestamp"] >= t_min].copy()

    if dfw.empty:
        return None, None

    # --- build link stats ---
    links = build_link_stats(dfw, trend_points=TREND_POINTS)

    # --- filter only link_id + trends (like hosts) ---
    links = [
        {
            "link_id": l["link_id"],
            "rx_pps_trend": l["rx_pps_trend"],
            "tx_pps_trend": l["tx_pps_trend"],
            "rx_kbps_trend": l["rx_kbps_trend"],
            "tx_kbps_trend": l["tx_kbps_trend"]
        }
        for l in links
    ]

    # --- last K decisions ---
    last_decisions = []
    try:
        with open(DECISION_LOG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    last_decisions.append(json.loads(line))
        last_decisions = last_decisions[-last_k_decisions:]
    except FileNotFoundError:
        last_decisions = []

    scene = {
        "ts": now_iso(),
        "window_minutes": WINDOW_MINUTES,
        "trend_points": TREND_POINTS,
        "window_end_time": str(t_end),
        "counts": {
            "unique_links": int(len(links)),
            "raw_rows_in_window": int(len(dfw)),
        },
        "link_stats": links,
        "last_decisions": last_decisions
    }

    prompt = f"""
You are an SDN network anomaly detection function for LINKS.

Task:
Select link_id values that show abnormal congestion (rising load / spikes).

Indicators of abnormal behavior:
- rx_pps_trend rising / spiking
- tx_pps_trend rising / spiking
- rx_kbps_trend rising / spiking
- tx_kbps_trend rising / spiking

If no link meets these conditions, choose do_nothing.

Return ONLY valid JSON.

Output Schema:
{{
"decision": "reroute | do_nothing",
"links_to_avoid": ["LINK_ID"],
"confidence": 0.0,
"observation": [
{{"link_id":"LINK_ID","reason":"short_reason"}}
]
}}

Rules:
- Do NOT explain anything.
- Do NOT repeat the input.
- Only return JSON.
- JSON must start with '{{' and end with '}}'.

link_stats:
{json.dumps(links)}

Return JSON.
""".strip()

    with open(SCENE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": now_iso(),
            "model": model_name,
            "scene": scene,
            "prompt": prompt
        }) + "\n")

    # print(prompt) # temp
    return scene, prompt, t_end

# ===================== COMPACT FINAL FUSION CELL =====================

# def build_final_prompt(scene, history_summary="", prompt_file=FINAL_PROMPT_FILE):
#     template = load_prompt_template(prompt_file)

#     prompt = template.format(
#         scene_json=json.dumps(scene, ensure_ascii=False),
#         history_summary=history_summary or "None"
#     )

#     return prompt.strip()


# def build_final_prompt(scene):
def build_final_prompt(scene, history_summary=""):  # add parameter #new summary
    history_block = ""
    if history_summary:
        history_block = f"""
    Recent decision history summary (use this to avoid repeating failed patterns and reinforce what worked):
    {history_summary}
    """
    prompt=f"""You are the final SDN security decision layer.

    You receive telemetry about suspected hosts and suspected links.
    Your task is to decide the final Moving Target Defense action.

    Available decisions:

    - "ip": use IP mutation for host-side flooding
    - "rrm": use route mutation for active link flooding / active link exhaustion
    - "do_nothing": no action

    Input telemetry format:

    - host_stats contains host MACs and their rx_pps_trend, tx_pps_trend, rx_kbps_trend, tx_kbps_trend.
    - link_stats contains link IDs and their rx_pps_trend, tx_pps_trend, rx_kbps_trend, tx_kbps_trend.
    - The last value in each trend is the latest/current telemetry value.

    Definitions:

    - Host flooding means a host-level packet-rate abnormality.
    - Use host pps as the main signal for host-side flooding.
    - The signal may appear in tx_pps or rx_pps depending on telemetry direction.
    - High rx_pps usually indicates a flooded victim host.
    - High tx_pps usually indicates a flooding source or compromised high-sending host.
    - Do not confuse the flooding source with the flooded victim.
    - Link flooding means a link is currently near or above its bandwidth capacity.
    - Use link rx_kbps and tx_kbps as the main signals for link congestion.
    - Link pps alone is not enough to trigger RRM.

    Calibration values:

    - In benign observations, most host pps stays around 300-700 pps.
    - Some benign central-host behavior can approach 700-900 pps.
    - Treat 700-1000 pps as an elevated/watch-zone range, not an automatic attack.
    - h1 / MAC 00:00:00:00:00:01 is a known central-host exception.
    - The nominal link bandwidth limit is 7 Mbps = 7000 kbps.
    - Treat these values as calibration context, not blind thresholds.

    Host-defense trigger:

    - Choose "ip" only when a clear host-flooding target exists.
    - A clear host target has pps that is sustained, sharply rising, or clearly beyond benign pps.
    - Prefer rx_pps evidence when selecting the flooded victim host.
    - If only tx_pps is high, treat that host as a possible source, not automatically as the victim.
    - Do not select h1 only because it is higher than other hosts.
    - Include only the clearest host MACs that should receive IP mutation.
    - When final_decision is "ip", final_links must be empty.

    Active link-defense trigger:

    - Choose "rrm" only for active/current link bandwidth congestion.
    - Active congestion means the latest rx_kbps or tx_kbps is above capacity.
    - If no clear host-flooding target exists, but one or more links are currently above capacity, choose "rrm".
    - Include only those currently congested link IDs in final_links.

    Link recovery rule:

    - Do not choose "rrm" just because a link crossed capacity earlier.
    - If a link was above capacity earlier but the latest rx_kbps and latest tx_kbps are below capacity and decreasing, treat it as recovering.
    - For recovering links, choose "do_nothing" unless host flooding triggers "ip".
    - RRM is for active congestion, not already-recovered congestion.

    Important priority rule:

    - Host-side defense has priority over link shuffling when a clear host-flooding target exists.
    - If a clear host-flooding target exists, choose "ip" even if some links are also congested.
    - If links are currently congested but no clear host-flooding target exists, choose "rrm".

    Do-not-overreact rule:

    - Do not choose "ip" only because a host is listed as suspected.
    - Do not choose "ip" for normal benign pps variation.
    - Do not choose "rrm" only because a link pps value increased.
    - Do not choose "rrm" only because a link crossed capacity earlier.
    - Choose an action only when telemetry supports the current trigger.
    - Do not trigger "ip" within benign range of rx_pps.
    - Sudden spike within benign range is normal for the topology.

    Return strict JSON only.
    No markdown.
    No extra text.
    No comments.
    No trailing commas.

    Output schema:
    {{
    "final_decision": "do_nothing | rrm | ip",
    "final_macs": ["MAC_ADDRESS"],
    "final_links": ["LINK_ID"],
    "confidence": 0.0,
    "severity": "low | medium | high | critical",
    "observation": [
    {{
    "type": "host",
    "id": "MAC_ADDRESS",
    "reason": "attack_type=host_flooding | link_flooding | no_attack; short_reason"
    }},
    {{
    "type": "link",
    "id": "LINK_ID",
    "reason": "attack_type=host_flooding | link_flooding | no_attack; short_reason"
    }}
    ]
    }}

    Field rules:

    - final_decision must be exactly one of: "ip", "rrm", "do_nothing".
    - final_macs must contain only MACs that should be acted on.
    - final_links must contain only currently congested links that should be avoided/rerouted.
    - If final_decision is "do_nothing", return empty lists for final_macs and final_links.
    - If final_decision is "ip", include only host MACs selected for IP mutation and return final_links as an empty list.
    - If final_decision is "rrm", include only currently congested link IDs in final_links.
    - If final_decision is "rrm", final_macs may be empty unless related host MACs are clearly available.
    - confidence must be between 0.0 and 1.0.
    - severity must be "low", "medium", "high", or "critical".
    - observation must summarize the detected host and link conditions.
    - Each observation reason must mention one of:
        - attack_type=host_flooding
        - attack_type=link_flooding
        - attack_type=no_attack

    Input:
    {json.dumps(scene, ensure_ascii=False)}

    Return JSON only."""

    # - Do not trigger "ip" within benign range of rx_pps.
    # - Sudden spike within benign range is normal for the topology.
#     prompt=f"""You are the final SDN security decision layer.

# You receive telemetry about suspected hosts and suspected links.
# Your task is to decide the final Moving Target Defense action.

# Available decisions:
# - "ip": use IP mutation for host-side flooding / compromised high-sending host
# - "rrm": use route mutation for active link flooding / active link exhaustion
# - "do_nothing": no action

# Input telemetry format:
# - host_stats contains host MACs and their rx_pps_trend, tx_pps_trend, rx_kbps_trend, tx_kbps_trend.
# - link_stats contains link IDs and their rx_pps_trend, tx_pps_trend, rx_kbps_trend, tx_kbps_trend.
# - The last value in each trend is the latest/current telemetry value.

# Definitions:
# - Host flooding means a host has an abnormal high-receiving packet pattern.
# - Use host tx_pps as the main signal for host-side flooding.
# - A host with very high tx_pps is a flooding host or compromised host.
# - Link flooding means a link is currently near or above its bandwidth capacity.
# - The link bandwidth limit is 9 Mbps = 9000 kbps.
# - Use link rx_kbps and tx_kbps as the main signals for link congestion.
# - Link pps alone is not enough to trigger RRM.

# Benign traffic tolerance:
# - Host tx_pps can vary during normal operation.
# - Many hosts may stay low, but central or highly active hosts can show temporary tx_pps increases.
# - Host tx_pps around 300–700 pps can be tolerable.
# - Some benign central-host behavior can approach 700–900 pps (mac 00:00:00:00:00:01).
# - Treat 700–1000 pps as an elevated/watch-zone range, not an automatic attack.
# - Link pps can also increase during benign operation, so do not use link pps alone for RRM.

# Host-defense trigger:
# - A sudden or sustained host tx_pps rise above 1000 pps is outside the benign tolerance range.
# - Include only those high-tx_pps host MACs in final_macs.
# - When final_decision is "ip", final_links must be empty.

# Active link-defense trigger:
# - Link rx_kbps or tx_kbps below or equal to 9000 kbps is within tolerable capacity.
# - Choose "rrm" only for active/current link congestion.
# - Active/current link congestion means the latest rx_kbps or latest tx_kbps is above 9000 kbps.
# - If no host crosses the host-defense trigger, but one or more links have latest rx_kbps or latest tx_kbps above 9000 kbps, choose "rrm".
# - Include only those currently congested link IDs in final_links.


# Link recovery rule:
# - Do not choose "rrm" just because a link crossed 9000 kbps earlier.
# - If a link was above 9000 kbps earlier but the latest rx_kbps and latest tx_kbps are below 9000 kbps and decreasing, treat it as recovering.
# - For recovering links, choose "do_nothing" unless host tx_pps triggers "ip".
# - RRM is for active congestion, not already-recovered congestion.

# Important priority rule:
# - Host-side defense has priority over link shuffling when a high-tx_pps host is present.
# - If a host has max_tx_pps above 1000 pps, choose "ip" even if some links are also currently above 9000 kbps.
# - If links are currently above 9000 kbps but all host max tx_pps values are 1000 pps or below, choose "rrm".

# Do-not-overreact rule:
# - Do not choose "ip" only because a host is listed as suspected.
# - Do not choose "ip" for host tx_pps in the 300–700 pps tolerance/watch-zone range.
# - Do not choose "rrm" only because a link pps value increased.
# - Do not choose "rrm" only because a link crossed 9000 kbps earlier.
# - Choose an action only when telemetry supports the current trigger.

# Return strict JSON only.
# No markdown.
# No extra text.
# No comments.
# No trailing commas.

# Output schema:
# {{
# "final_decision": "do_nothing | rrm | ip",
# "final_macs": ["MAC_ADDRESS"],
# "final_links": ["LINK_ID"],
# "confidence": 0.0,
# "severity": "low | medium | high | critical",
# "observation": [
#     {{
#     "type": "host",
#     "id": "MAC_ADDRESS",
#     "reason": "attack_type=host_flooding | link_flooding | no_attack; short_reason"
#     }},
#     {{
#     "type": "link",
#     "id": "LINK_ID",
#     "reason": "attack_type=host_flooding | link_flooding | no_attack; short_reason"
#     }}
# ]
# }}

# Field rules:
# - final_decision must be exactly one of: "ip", "rrm", "do_nothing".
# - final_macs must contain only MACs that should be acted on.
# - final_links must contain only currently congested links that should be avoided/rerouted.
# - If final_decision is "do_nothing", return empty lists for final_macs and final_links.
# - If final_decision is "ip", include only high tx_pps host MACs in final_macs and return final_links as an empty list.
# - If final_decision is "rrm", include only currently congested link IDs in final_links.
# - If final_decision is "rrm", final_macs may be empty unless related host MACs are clearly available.
# - confidence must be between 0.0 and 1.0.
# - severity must be "low", "medium", "high", or "critical".
# - observation must summarize the detected host and link conditions.
# - Each observation reason must mention one of:
# - attack_type=host_flooding
# - attack_type=link_flooding
# - attack_type=no_attack

# Recent decision history summary:
# {history_summary}

# Input:
# {scene_json}

# Return JSON only."""
    return prompt