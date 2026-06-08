from mininet.net import Mininet
from mininet.node import Controller, RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel
from mininet.link import TCLink
import random
import threading
import time
from functools import partial
from mininet.net import Mininet
from mininet.node import Controller, RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel
from mininet.link import TCLink
import random
import threading
import time

def clear_arp_cache(net):
    """Clear ARP cache on all hosts."""
    for host in net.hosts:
        try:
            # Ensure the host is ready
            if host.shell and not host.waiting:
                host.cmd('ip -s -s neigh flush all')
                print("ARP cache cleared on {}.".format(host.name))
            else:
                print("Host {} is not ready to execute commands.".format(host.name))
        except Exception as e:
            print("Error clearing ARP cache on {}: {}".format(host.name, str(e)))
    print("ARP cache cleared on all hosts.")

def shuffle_ips(net, stop_event):
    """Shuffle IP addresses of all hosts every 3 minutes."""
    while not stop_event.is_set():
        print("\nShuffling IP addresses...")
        hosts = net.hosts
        ips = [host.IP() for host in hosts]
        random.shuffle(ips)
        for host, ip in zip(hosts, ips):
            try:
                host.setIP(ip)
                print("Assigned IP {} to {}".format(ip, host.name))
            except Exception as e:
                print("Error assigning IP {} to {}: {}".format(ip, host.name, str(e)))
        print("IP addresses shuffled.")
        # clear_arp_cache(net)
        time.sleep(180)  # Wait for 3 minutes

def ping_all_from_h1(net, log_file):
    """Ping all other hosts from h1 and log the results."""
    h1 = net.get('h1')
    with open(log_file, 'a') as f:
        for i in range(2, 16):  # h2 to h39
            host = net.get('h%d' % i)
            try:
                result = h1.cmd('ping -c 2 %s' % host.IP())  # Ping 2 times for better accuracy
                if "2 received" in result:
                    status = "success"
                elif "0 received" in result:
                    status = "failed"
                else:
                    status = "partial"
                
                # Extract average latency
                latency = "N/A"
                if "min/avg/max" in result:
                    latency = result.split("min/avg/max/mdev = ")[1].split("/")[1]  # Extract avg latency
                
                # Log the result using % formatting
                log_entry = "Ping from h1 to %s (%s): %s, Avg Latency: %s ms\n" % (
                    host.name, host.IP(), status, latency
                )
                f.write(log_entry)
                print(log_entry.strip())

            except Exception as e:
                error_msg = "Error pinging {} ({}): {}\n".format(host.name, host.IP(), str(e))
                f.write(error_msg)
                print(error_msg.strip())

def post_shuffling_ping_tests(net, log_file, stop_event):
    """Perform post-shuffling ping tests every 2 minutes."""
    while not stop_event.is_set():
        # clear_arp_cache(net)
        # time.sleep(60)
        print("\nPerforming post-shuffling ping tests...")
        ping_all_from_h1(net, log_file)
        time.sleep(240)  # Wait for 2 minutes

def create_network():
    # Create network with RemoteController
    OVSSwitch13 = partial(OVSSwitch, protocols='OpenFlow13')
    net = Mininet(controller=RemoteController, switch=OVSSwitch13, link=TCLink)
    
    # Add ONOS controller
    c0 = net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)
    
    # Add central switch
    central_switch = net.addSwitch('s0')
    
    # Add main switches
    main_switches = []
    for i in range(1, 7):  # switches 1-6
        switch = net.addSwitch('s%d' % i)
        main_switches.append(switch)
        # Connect to central switch
        net.addLink(central_switch, switch)
    
    # Add backup switches
    backup_switches = []
    for i in range(7, 10):  # switches 7-9 (backup switches)
        switch = net.addSwitch('s%d' % i)
        backup_switches.append(switch)
        # Connect to central switch
        net.addLink(central_switch, switch)
    
    # Add hosts and connect them to main switches
    host_count = 0
    for i, switch in enumerate(main_switches):
        # Each main switch gets 6 or 7 hosts
        hosts_per_switch = 7 if i < 3 else 6  # First 3 switches get 7 hosts, others get 6
        
        for j in range(hosts_per_switch):
            host_count += 1
            host = net.addHost('h%d' % host_count)
            net.addLink(host, switch)
    
    # Connect backup switches to main switches
    # Each backup switch connects to two main switches
    for i, backup_switch in enumerate(backup_switches):
        net.addLink(backup_switch, main_switches[i*2])
        net.addLink(backup_switch, main_switches[i*2 + 1])
    
    # Start network
    net.build()
    c0.start()
    
    # Start all switches
    for switch in net.switches:
        switch.start([c0])
        print("%s is connected to the controller" % switch.name)
    
    # Wait for switches to stabilize
    time.sleep(10)  # Wait 10 seconds

    print("Network created with:")
    print("- 39 hosts (h1 to h39)")
    print("- 6 main switches (s1 to s6)")
    print("- 3 backup switches (s7 to s9)")
    print("- 1 central switch (s0)")

    # Wait for the network to converge
    print("\nWaiting for the network to converge...")
    net.waitConnected()
    time.sleep(30)  # Wait 30 seconds for the network to converge

    # Log file for results
    log_file = "ping_results.log"
    with open(log_file, 'w') as f:
        f.write("Network Performance Log\n")
        f.write("=======================\n")

    # Event to stop the IP shuffling and ping test threads
    stop_event = threading.Event()

    # Perform baseline ping tests
    print("\nPerforming baseline ping tests...")
    ping_all_from_h1(net, log_file)

    # Clear ARP cache
    clear_arp_cache(net)
    time.sleep(10)

    # Start IP shuffling in a separate thread
    shuffle_thread = threading.Thread(target=shuffle_ips, args=(net, stop_event))
    shuffle_thread.daemon = True
    shuffle_thread.start()

    # Start post-shuffling ping tests in a separate thread
    ping_thread = threading.Thread(target=post_shuffling_ping_tests, args=(net, log_file, stop_event))
    ping_thread.daemon = True
    ping_thread.start()

    # Start CLI (optional)
    CLI(net)

    # Stop the IP shuffling and ping test threads
    stop_event.set()
    shuffle_thread.join()
    ping_thread.join()

    # Clean up
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    create_network()