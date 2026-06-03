import pandas as pd
import time
import os
from collections import defaultdict, deque

CSV_FILE = "link_stats_onos.csv"
OUT_FILE = "link_trends.txt"

WINDOW = 50       # keep last 50 values
SLEEP_SEC = 2

link_history = defaultdict(lambda: {
    "rx_pps": deque(maxlen=WINDOW),
    "tx_pps": deque(maxlen=WINDOW),
    "rx_mbps": deque(maxlen=WINDOW),
    "tx_mbps": deque(maxlen=WINDOW),
})

last_processed = 0

while True:
    try:
        if not os.path.exists(CSV_FILE):
            print(f"Waiting for {CSV_FILE}...")
            time.sleep(SLEEP_SEC)
            continue

        df = pd.read_csv(CSV_FILE)
        df.columns = df.columns.str.strip()

        # handle file reset
        if len(df) < last_processed:
            last_processed = 0
            link_history.clear()

        new_rows = df.iloc[last_processed:]

        if not new_rows.empty:
            for _, row in new_rows.iterrows():
                link = row["link_id"]

                link_history[link]["rx_pps"].append(float(row["rx_pps"]))
                link_history[link]["tx_pps"].append(float(row["tx_pps"]))
                link_history[link]["rx_mbps"].append(float(row["rx_mbps"]))
                link_history[link]["tx_mbps"].append(float(row["tx_mbps"]))

            last_processed = len(df)

            # ===== WRITE TXT =====
            with open(OUT_FILE, "w") as f:
                for link in sorted(link_history.keys()):
                    vals = link_history[link]

                    f.write(f"{link}\n")
                    f.write(f"  rx_pps : {list(vals['rx_pps'])}\n")
                    f.write(f"  tx_pps : {list(vals['tx_pps'])}\n")
                    f.write(f"  rx_mbps: {list(vals['rx_mbps'])}\n")
                    f.write(f"  tx_mbps: {list(vals['tx_mbps'])}\n")
                    f.write("\n")

            print(f"Updated {OUT_FILE}")

        time.sleep(SLEEP_SEC)

    except KeyboardInterrupt:
        print("\nStopped.")
        break
    except Exception as e:
        print("Error:", e)
        time.sleep(SLEEP_SEC)