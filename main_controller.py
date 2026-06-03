from ip_shuffle_endpoint import ip_shuffle_endpoint
from route_mutate_endpoint import route_shuffle_endpoint
import time , random

from collections import deque

import csv
import os
IP_HISTORY_FILE = "ip_history.csv"
ROUTE_HISTORY_FILE = "route_history.csv"
ROUTE_HISTORY_SIZE = 10   # or 5 if you want 5


HOST_TO_SWITCH = {
    "h1": "s1",

    "h2": "s2", "h3": "s2", "h4": "s2", "h5": "s2", "h6": "s2", "h7": "s2", "h8": "s2",

    "h9": "s3", "h10": "s3", "h11": "s3", "h12": "s3", "h13": "s3", "h14": "s3", "h15": "s3",

    "h16": "s4", "h17": "s4", "h18": "s4", "h19": "s4", "h20": "s4", "h21": "s4",

    "h22": "s5", "h23": "s5", "h24": "s5", "h25": "s5", "h26": "s5", "h27": "s5",

    "h28": "s6", "h29": "s6", "h30": "s6", "h31": "s6", "h32": "s6", "h33": "s6",

    "h34": "s7", "h35": "s7", "h36": "s7", "h37": "s7", "h38": "s7", "h39": "s7", "h40": "s7",
}


SKIP_HOSTS = {"h40"}

all_hosts = [f"h{i}" for i in range(1, 41) if f"h{i}" not in SKIP_HOSTS]

# IP helper
class HostIPQueueManager:
    def __init__(self, host_count=40, queue_size=10):
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
            return

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
    def __init__(self, hosts, queue_size=10):
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
# IP helper
# ip_manager = HostIPQueueManager()

# # Example: initialize h1..h40 with 10 IPs each
# for i in range(1, 41):
#     host = f"h{i}"
#     ip_list = [i + 100 * k for k in range(10)]
#     ip_manager.set_host_ips(host, ip_list)

# # 1) get current IPs of h1..h40
# current_ips = ip_manager.get_current_ips()
# print("Current IPs:")
# print(current_ips)

# # 2) get all 10 IPs of all hosts
# all_host_ips = ip_manager.get_all_host_ips()
# print("\nAll host IP queues:")
# print(all_host_ips)

# # 3) get only h1's 10 IPs
# print("\nh1 queue:")
# print(ip_manager.get_host_ips("h1"))



# route helper


# route helper



# ip_shuffle_endpoint(
#     host="h1,h2,h3",
#     ips="10,20,30",
#     interval=15,
#     no_block_pid=True
# )

# route_shuffle_endpoint(
#     specific_multiple=True,
#     hosts="h1,h2;h1,h7",
#     opt="3;4"
# )

# def run_random_shuffle(ip_manager, host_count=40):
def run_random_shuffle(ip_manager, route_manager, host_count=40):
    mode = random.choice(["ip", "route"])

    if mode == "ip":
        print("\nIP shuffling")
        # all_hosts = [f"h{i}" for i in range(1, host_count + 1)]
        k = random.randint(1, 5)
        selected_hosts = random.sample(all_hosts, k)

        used_ips = set()
        for ip in ip_manager.get_current_ips().values():
            if ip is not None:
                used_ips.add(int(str(ip).split(".")[-1]))

        for host in selected_hosts:
            old_ip = ip_manager.current_ips.get(host)
            if old_ip is not None:
                used_ips.discard(int(str(old_ip).split(".")[-1]))

        available_ips = [i for i in range(1, 255) if i not in used_ips]
        new_ips = random.sample(available_ips, k)

        shuffled_map = dict(zip(selected_hosts, new_ips))

        ip_shuffle_endpoint(
            host=",".join(selected_hosts),
            ips=",".join(map(str, new_ips)),
            interval=30,
            no_block_pid=True
        )

        # append for all 40 hosts every round
        for host in all_hosts:
            if host in shuffled_map:
                ip_manager.update_host_queue(host, shuffled_map[host])
            else:
                last_ip = ip_manager.current_ips.get(host)
                if last_ip is not None:
                    ip_manager.update_host_queue(host, last_ip)
        ip_manager.save_to_csv()

        print("[IP SHUFFLE]", shuffled_map)

    else:
        pair_count = random.randint(1, 3)
        pairs = []
        seen_unordered = set()

        while len(pairs) < pair_count:
            a, b = random.sample(all_hosts, 2)

            if HOST_TO_SWITCH[a] == HOST_TO_SWITCH[b]:
                continue

            key = tuple(sorted((a, b)))
            if key in seen_unordered:
                continue

            seen_unordered.add(key)
            pairs.append((a, b))

        # opts = [random.randint(1, 4) for _ in pairs]
        opts = [random.randint(1, 3) for _ in pairs]


        route_shuffle_endpoint(
            specific_multiple=True,
            hosts=";".join([f"{a},{b}" for a, b in pairs]),
            opt=";".join(map(str, opts))
        )

        shuffled_route_map = {
            tuple(sorted((a, b))): opt for (a, b), opt in zip(pairs, opts)
        }

        for (a, b) in route_manager.queues.keys():
            if (a, b) in shuffled_route_map:
                route_manager.update_pair(a, b, shuffled_route_map[(a, b)])
            else:
                route_manager.update_pair(a, b, 0)

        route_manager.save_to_csv()

        print("[ROUTE SHUFFLE]", pairs, opts)

# main()
# ip_manager = HostIPQueueManager()
# for i in range(1, 41):
#     ip_manager.set_host_ips(f"h{i}", [i])


# while True:
#     run_random_shuffle(ip_manager)
#     print(ip_manager.get_all_host_ips())
#     time.sleep(30)

ip_manager = HostIPQueueManager()
for i in range(1, 41):
    ip_manager.set_host_ips(f"h{i}", [i])

ip_manager.load_from_csv()

route_manager = RouteHistoryManager(all_hosts, queue_size=ROUTE_HISTORY_SIZE)
route_manager.load_from_csv()

while True:
    run_random_shuffle(ip_manager, route_manager)
    print(ip_manager.get_all_host_ips())
    # print(route_manager.get_all_histories())
    time.sleep(30)