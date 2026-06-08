import csv
import datetime
import time
import re
import json


def parse_ping(output):
    loss = None
    rtt_avg = None

    loss_match = re.search(r'(\d+(?:\.\d+)?)% packet loss', output)
    if loss_match:
        loss = float(loss_match.group(1))

    rtt_match = re.search(
        r'rtt min/avg/max/(?:mdev|stddev) = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)',
        output
    )
    if rtt_match:
        rtt_avg = float(rtt_match.group(2))

    return rtt_avg, loss


def safe_json_load(output):
    try:
        start = output.find("{")
        end = output.rfind("}")

        if start != -1 and end != -1:
            return json.loads(output[start:end + 1])

    except Exception as e:
        print("JSON parse error:", e)

    return None


def parse_tcp_iperf(output):
    data = safe_json_load(output)

    if data is None:
        return None

    end = data.get("end", {})

    if "sum_received" in end:
        bps = end["sum_received"].get("bits_per_second")
    elif "sum_sent" in end:
        bps = end["sum_sent"].get("bits_per_second")
    else:
        bps = None

    if bps is None:
        return None

    return bps / 1000000.0


def parse_udp_iperf(output):
    data = safe_json_load(output)

    if data is None:
        return None, None, None

    end = data.get("end", {})

    udp_sum = (
        end.get("sum")
        or end.get("sum_received")
        or end.get("sum_sent")
        or {}
    )

    bps = udp_sum.get("bits_per_second")
    jitter_ms = udp_sum.get("jitter_ms")
    lost_percent = udp_sum.get("lost_percent")

    throughput_mbps = bps / 1000000.0 if bps is not None else None

    return throughput_mbps, jitter_ms, lost_percent


def capture_all_host_metrics(
    net,
    output_csv="h1_to_all_metrics.csv",
    ping_count=5,
    iperf_duration=5,
    udp_bandwidth="5M",
    port=5001,
    src_host_name="h1"
):
    src = net.get(src_host_name)

    fieldnames = [
        "timestamp",
        "src_host",
        "src_ip",
        "dst_host",
        "dst_ip",
        "rtt_avg_ms",
        "ping_packet_loss_percent",
        "tcp_throughput_mbps",
        "udp_throughput_mbps",
        "udp_jitter_ms",
        "udp_packet_loss_percent"
    ]

    print("\n========== Starting {}-to-all metric capture ==========".format(src_host_name))
    print("Output file:", output_csv)

    with open(output_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for dst in net.hosts:
            if dst == src:
                continue

            print("Testing {} -> {}".format(src.name, dst.name))

            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Ping: RTT + packet loss
            ping_output = src.cmd("ping -c {} {}".format(ping_count, dst.IP()))
            rtt_avg_ms, ping_loss_percent = parse_ping(ping_output)

            #new
            dst.cmd("pkill -f iperf3 || true")
            time.sleep(0.3)
            
            # TCP iperf3: throughput
            dst.cmd("pkill -f 'iperf3 -s' || true")
            time.sleep(0.2)

            dst.cmd("iperf3 -s -p {} -D".format(port))
            time.sleep(0.5)

            tcp_output = src.cmd(
                "iperf3 -c {} -p {} -t {} -J".format(
                    dst.IP(),
                    port,
                    iperf_duration
                )
            )

            tcp_throughput_mbps = parse_tcp_iperf(tcp_output)

            dst.cmd("pkill -f 'iperf3 -s' || true")
            time.sleep(0.2)

            # UDP iperf3: throughput + jitter + loss
            dst.cmd("iperf3 -s -p {} -D".format(port))
            time.sleep(0.5)

            udp_output = src.cmd(
                "iperf3 -c {} -p {} -u -b {} -t {} -J".format(
                    dst.IP(),
                    port,
                    udp_bandwidth,
                    iperf_duration
                )
            )

            udp_throughput_mbps, udp_jitter_ms, udp_loss_percent = parse_udp_iperf(
                udp_output
            )

            dst.cmd("pkill -f 'iperf3 -s' || true")
            time.sleep(0.2)

            row = {
                "timestamp": timestamp,
                "src_host": src.name,
                "src_ip": src.IP(),
                "dst_host": dst.name,
                "dst_ip": dst.IP(),
                "rtt_avg_ms": rtt_avg_ms,
                "ping_packet_loss_percent": ping_loss_percent,
                "tcp_throughput_mbps": tcp_throughput_mbps,
                "udp_throughput_mbps": udp_throughput_mbps,
                "udp_jitter_ms": udp_jitter_ms,
                "udp_packet_loss_percent": udp_loss_percent
            }

            writer.writerow(row)
            f.flush()

            print(
                "  RTT={} ms | PingLoss={}% | TCP={} Mbps | UDP={} Mbps | Jitter={} ms | UDPLoss={}%".format(
                    rtt_avg_ms,
                    ping_loss_percent,
                    tcp_throughput_mbps,
                    udp_throughput_mbps,
                    udp_jitter_ms,
                    udp_loss_percent
                )
            )

    print("\n========== Metric capture complete ==========")
    print("Saved to:", output_csv)