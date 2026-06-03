import time
import numpy as np
import pandas as pd


HOST_PPS_THRESHOLD = 1000
HOST_KBPS_THRESHOLD = 1000
HOST_STATIC_POINTS = 3

LINK_KBPS_THRESHOLD = 9000
LINK_PPS_THRESHOLD = 300
LINK_STATIC_POINTS = 3

HOST_SPIKE_FACTOR = 1.5
LINK_SPIKE_FACTOR = 1.25

HOST_DROP_FACTOR = 1.5
LINK_DROP_FACTOR = 1.5
HOST_MIN_MEANINGFUL_PPS = 100
HOST_MIN_MEANINGFUL_KBPS = 1000

LINK_MIN_MEANINGFUL_PPS = 100
LINK_MIN_MEANINGFUL_KBPS = 1000

def _clean(values):
    return [float(v) for v in values if pd.notna(v)]


def _count_above(values, threshold):
    values = _clean(values)
    return sum(v >= threshold for v in values)


def _has_spike_anywhere(values, factor, min_value):
    values = _clean(values)

    if len(values) < 3:
        return False

    for i in range(1, len(values)):
        prev = values[:i]
        prev_avg = sum(prev) / len(prev)
        current = values[i]

        if current < min_value:
            continue

        if prev_avg <= 0:
            if current >= min_value:
                return True
        elif current >= factor * prev_avg:
            return True

    return False


def _has_drop_anywhere(values, factor, min_prev_avg):
    values = _clean(values)

    if len(values) < 3:
        return False

    for i in range(1, len(values)):
        prev = values[:i]
        prev_avg = sum(prev) / len(prev)
        current = values[i]

        if prev_avg < min_prev_avg:
            continue

        if current <= prev_avg / factor:
            return True

    return False


def code_filter_hosts(hosts):
    flagged_macs = []

    for h in hosts:
        tx_pps = h["tx_pps_trend"]
        rx_pps = h["rx_pps_trend"]
        tx_kbps = h["tx_kbps_trend"]
        rx_kbps = h["rx_kbps_trend"]

        static_high = (
            _count_above(tx_pps, HOST_PPS_THRESHOLD) >= HOST_STATIC_POINTS
            or _count_above(rx_pps, HOST_PPS_THRESHOLD) >= HOST_STATIC_POINTS
            or _count_above(tx_kbps, HOST_KBPS_THRESHOLD) >= HOST_STATIC_POINTS
            or _count_above(rx_kbps, HOST_KBPS_THRESHOLD) >= HOST_STATIC_POINTS
        )

        has_spike = (
            _has_spike_anywhere(tx_pps, HOST_SPIKE_FACTOR, HOST_MIN_MEANINGFUL_PPS)
            or _has_spike_anywhere(rx_pps, HOST_SPIKE_FACTOR, HOST_MIN_MEANINGFUL_PPS)
            or _has_spike_anywhere(tx_kbps, HOST_SPIKE_FACTOR, HOST_MIN_MEANINGFUL_KBPS)
            or _has_spike_anywhere(rx_kbps, HOST_SPIKE_FACTOR, HOST_MIN_MEANINGFUL_KBPS)
        )

        has_drop = (
            _has_drop_anywhere(tx_pps, HOST_DROP_FACTOR, HOST_MIN_MEANINGFUL_PPS)
            or _has_drop_anywhere(rx_pps, HOST_DROP_FACTOR, HOST_MIN_MEANINGFUL_PPS)
            or _has_drop_anywhere(tx_kbps, HOST_DROP_FACTOR, HOST_MIN_MEANINGFUL_KBPS)
            or _has_drop_anywhere(rx_kbps, HOST_DROP_FACTOR, HOST_MIN_MEANINGFUL_KBPS)
        )

        if static_high or has_spike or has_drop:
            flagged_macs.append(h["mac"])

    out1 = {
        "decision": "ip_shuffle" if flagged_macs else "do_nothing",
        "macs_to_shuffle": flagged_macs,
        "confidence": 0.90 if flagged_macs else 0.0,
        "observation": []
    }

    return out1, flagged_macs


def code_filter_links(links):
    flagged_links = []

    for l in links:
        rx_kbps = l["rx_kbps_trend"]
        tx_kbps = l["tx_kbps_trend"]
        rx_pps = l["rx_pps_trend"]
        tx_pps = l["tx_pps_trend"]

        static_high = (
            _count_above(rx_kbps, LINK_KBPS_THRESHOLD) >= LINK_STATIC_POINTS
            or _count_above(tx_kbps, LINK_KBPS_THRESHOLD) >= LINK_STATIC_POINTS
            or _count_above(rx_pps, LINK_PPS_THRESHOLD) >= LINK_STATIC_POINTS
            or _count_above(tx_pps, LINK_PPS_THRESHOLD) >= LINK_STATIC_POINTS
        )

        has_spike = (
            _has_spike_anywhere(rx_kbps, LINK_SPIKE_FACTOR, LINK_MIN_MEANINGFUL_KBPS)
            or _has_spike_anywhere(tx_kbps, LINK_SPIKE_FACTOR, LINK_MIN_MEANINGFUL_KBPS)
            or _has_spike_anywhere(rx_pps, LINK_SPIKE_FACTOR, LINK_MIN_MEANINGFUL_PPS)
            or _has_spike_anywhere(tx_pps, LINK_SPIKE_FACTOR, LINK_MIN_MEANINGFUL_PPS)
        )

        # has_drop = (
        #     _has_drop_anywhere(rx_kbps, LINK_DROP_FACTOR, LINK_MIN_MEANINGFUL_KBPS)
        #     or _has_drop_anywhere(tx_kbps, LINK_DROP_FACTOR, LINK_MIN_MEANINGFUL_KBPS)
        #     or _has_drop_anywhere(rx_pps, LINK_DROP_FACTOR, LINK_MIN_MEANINGFUL_PPS)
        #     or _has_drop_anywhere(tx_pps, LINK_DROP_FACTOR, LINK_MIN_MEANINGFUL_PPS)
        # )
        has_drop = False

        if static_high or has_spike or has_drop:
            flagged_links.append(l["link_id"])

    out2 = {
        "decision": "reroute" if flagged_links else "do_nothing",
        "links_to_avoid": flagged_links,
        "confidence": 0.90 if flagged_links else 0.0,
        "observation": []
    }

    return out2, flagged_links