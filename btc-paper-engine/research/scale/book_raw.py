"""Raw l2Book level capture (READ-ONLY, public info endpoint, no credentials,
no orders) so refill/replenishment rate can be measured level-by-level.
Usage: python3 book_raw.py <out.jsonl> [minutes] [period_s]"""
import json, subprocess, sys, time
INFO = "https://api.hyperliquid.xyz/info"
out, mins, per = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
dl = time.time() + mins * 60
with open(out, "w") as f:
    while time.time() < dl:
        t0 = time.time()
        r = subprocess.run(["curl", "-sS", "--max-time", "15", "-X", "POST", INFO,
                            "-H", "Content-Type: application/json",
                            "-d", '{"type":"l2Book","coin":"BTC"}'],
                           capture_output=True, text=True)
        try:
            d = json.loads(r.stdout)
            f.write(json.dumps({"t": d["time"], "levels": d["levels"]}) + "\n"); f.flush()
        except Exception:
            pass
        time.sleep(max(0.0, per - (time.time() - t0)))
