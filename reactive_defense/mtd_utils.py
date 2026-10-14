from collections import deque
import csv
import os
IP_HISTORY_FILE = "ip_history.csv"
ROUTE_HISTORY_FILE = "route_history.csv"
# ROUTE_HISTORY_SIZE = 10
ROUTE_HISTORY_SIZE = 15

HOST_TO_SWITCH = {
    "h1": "s1",

    "h2": "s2", "h3": "s2", "h4": "s2", "h5": "s2", "h6": "s2", "h7": "s2", "h8": "s2",

    "h9": "s3", "h10": "s3", "h11": "s3", "h12": "s3", "h13": "s3", "h14": "s3", "h15": "s3",

    "h16": "s4", "h17": "s4", "h18": "s4", "h19": "s4", "h20": "s4", "h21": "s4",

    "h22": "s5", "h23": "s5", "h24": "s5", "h25": "s5", "h26": "s5", "h27": "s5",

    "h28": "s6", "h29": "s6", "h30": "s6", "h31": "s6", "h32": "s6", "h33": "s6",

    "h34": "s7", "h35": "s7", "h36": "s7", "h37": "s7", "h38": "s7", "h39": "s7", "h40": "s7",
}
SKIP_HOSTS = {}
all_hosts = [f"h{i}" for i in range(1, 41) if f"h{i}" not in SKIP_HOSTS]
# IP helper
class HostIPQueueManager:
    # def __init__(self, host_count=40, queue_size=10):
    def __init__(self, host_count=40, queue_size=15):
        self.host_count = host_count
        self.queue_size = queue_size
        self.queues = {}
        self.current_ips = {}

        for i in range(1, host_count + 1):
            host = f"h{i}"
            self.queues[host] = deque(maxlen=queue_size)
            self.current_ips[host] = None

    def set_host_ips(self, host, ip_list):
        if host not in self.queues:
            raise ValueError(f"Unknown host: {host}")

        self.queues[host].clear()
        for ip in ip_list[:self.queue_size]:
            self.queues[host].append(ip)

        if len(self.queues[host]) > 0:
            self.current_ips[host] = self.queues[host][-1]
        else:
            self.current_ips[host] = None

    def set_all_hosts_ips(self, host_ip_map):
        for host, ip_list in host_ip_map.items():
            self.set_host_ips(host, ip_list)

    def get_current_ips(self):
        return dict(self.current_ips)

    def get_all_host_ips(self):
        return {host: list(q) for host, q in self.queues.items()}

    def get_host_ips(self, host):
        if host not in self.queues:
            raise ValueError(f"Unknown host: {host}")
        return list(self.queues[host])

    def update_host_queue(self, host, new_ip):
        if host not in self.queues:
            raise ValueError(f"Unknown host: {host}")

        self.queues[host].append(new_ip)
        self.current_ips[host] = new_ip

    # /////////
    def save_to_csv(self, filename=IP_HISTORY_FILE):
        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["host", "history"])
            for host in sorted(self.queues.keys(), key=lambda x: int(x[1:])):
                writer.writerow([host, ",".join(map(str, self.queues[host]))])

    def load_from_csv(self, filename=IP_HISTORY_FILE):
        if not os.path.exists(filename):
            print(f"[LOAD] file not found: {filename}")
            return

        print(f"[LOAD] loading from {filename}")
        
        with open(filename, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                host = row["host"].strip()
                history = row["history"].strip()

                if host not in self.queues:
                    continue

                ip_list = []
                if history:
                    ip_list = [x.strip() for x in history.split(",") if x.strip()]

                self.set_host_ips(host, ip_list)
    # /////////

class RouteHistoryManager:
    # def __init__(self, hosts, queue_size=10):
    def __init__(self, hosts, queue_size=15):
        self.queue_size = queue_size
        self.queues = {}

        for i in range(len(hosts)):
            for j in range(i + 1, len(hosts)):
                a, b = hosts[i], hosts[j]
                key = self._pair_key(a, b)
                self.queues[key] = deque(maxlen=queue_size)

    def _pair_key(self, a, b):
        return tuple(sorted((a, b)))

    def update_pair(self, a, b, option_value):
        key = self._pair_key(a, b)
        if key not in self.queues:
            self.queues[key] = deque(maxlen=self.queue_size)
        self.queues[key].append(option_value)

    def get_pair_history(self, a, b):
        key = self._pair_key(a, b)
        return list(self.queues.get(key, []))

    def get_all_histories(self):
        return {f"{a},{b}": list(q) for (a, b), q in self.queues.items()}

    def save_to_csv(self, filename=ROUTE_HISTORY_FILE):
        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["host_a", "host_b", "history"])
            for (a, b), q in sorted(self.queues.items(), key=lambda x: (int(x[0][0][1:]), int(x[0][1][1:]))):
                writer.writerow([a, b, ",".join(map(str, q))])

    def load_from_csv(self, filename=ROUTE_HISTORY_FILE):
        if not os.path.exists(filename):
            return

        with open(filename, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                a = row["host_a"].strip()
                b = row["host_b"].strip()
                history = row["history"].strip()

                key = self._pair_key(a, b)
                if key not in self.queues:
                    self.queues[key] = deque(maxlen=self.queue_size)

                self.queues[key].clear()
                if history:
                    for x in history.split(","):
                        x = x.strip()
                        if x:
                            self.queues[key].append(int(x))

    #update others with 0
    def update_cycle(self, selected_routes):
        """
        Update route history for ONE RRM cycle.

        selected_routes example:
            [
                ("h2", "h34", 2),
                ("h3", "h33", 4)
            ]

        Meaning:
            - h2,h34 gets 2 appended
            - h3,h33 gets 4 appended
            - every other host pair gets 0 appended

        This guarantees every pair gets exactly ONE new value per cycle.
        """

        # Convert selected routes into a lookup dictionary
        # Example:
        #   ("h2", "h34") -> 2
        #   ("h3", "h33") -> 4
        selected_map = {}

        for a, b, opt in selected_routes:
            key = self._pair_key(a, b)   # keeps pair order consistent
            selected_map[key] = int(opt)

        # Now update every known host pair once
        for key in self.queues.keys():

            # If this pair was selected, append its option number.
            # If not selected, append 0.
            value = selected_map.get(key, 0)

            self.queues[key].append(value)

def repeat_ip_history():
    """
    Append one timeline step to IP history without changing any IP.
    Each host repeats its current/latest IP.
    """

    ip_manager = HostIPQueueManager(queue_size=ROUTE_HISTORY_SIZE)

    for i in range(1, 41):
        ip_manager.set_host_ips(f"h{i}", [i])

    ip_manager.load_from_csv()

    current_ips = ip_manager.get_current_ips()

    for h in all_hosts:
        ip_manager.update_host_queue(h, current_ips.get(h))

    ip_manager.save_to_csv()

    print("[IP HISTORY] repeated last IP values.")

def repeat_route_history():
    """
    Append one timeline step to route history without changing any route.
    Each host pair repeats its current/latest route option.
    """

    route_manager = RouteHistoryManager(
        all_hosts,
        queue_size=ROUTE_HISTORY_SIZE,
    )

    route_manager.load_from_csv()

    for key, q in route_manager.queues.items():
        last_value = q[-1] if len(q) > 0 else 0
        q.append(last_value)

    route_manager.save_to_csv()

    print("[ROUTE HISTORY] repeated last route values.")