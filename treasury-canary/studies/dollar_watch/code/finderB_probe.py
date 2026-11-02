"""Generic endpoint prober. usage: python3 -I probe.py RAWDIR NAME URL [NAME URL ...]
Saves body to RAWDIR/NAME.raw and prints one JSON line per probe with status,
content-type, bytes, and for FRED-style 2-col CSVs the first/last obs."""
import sys, json, os, csv, io, time
import httpx
raw = sys.argv[1]; os.makedirs(raw, exist_ok=True)
args = sys.argv[2:]
out = []
for name, url in zip(args[::2], args[1::2]):
    rec = {"name": name, "url": url}
    t0 = time.time()
    try:
        r = httpx.get(url, timeout=40, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 treasury-canary-probe (casey.rondin@gmail.com)"})
        rec["status"] = r.status_code
        rec["ctype"] = r.headers.get("content-type", "")[:60]
        rec["bytes"] = len(r.content)
        rec["secs"] = round(time.time() - t0, 1)
        with open(os.path.join(raw, name + ".raw"), "wb") as f:
            f.write(r.content)
        txt = r.content[:200000].decode("utf-8", "replace")
        rec["head"] = txt[:160].replace("\n", "\\n")
        # FRED-style csv parse
        if "csv" in rec["ctype"] or url.endswith(".csv") or "fredgraph" in url:
            rows = [x for x in csv.reader(io.StringIO(r.content.decode("utf-8", "replace"))) if x]
            rec["rows"] = len(rows) - 1
            if len(rows) > 2 and len(rows[1]) >= 2:
                rec["first"] = rows[1][:2]
                good = [x for x in rows[1:] if len(x) >= 2 and x[1] not in (".", "", "NA")]
                if good:
                    rec["last"] = good[-1][:2]
                    rec["n_obs"] = len(good)
    except Exception as e:
        rec["error"] = repr(e)[:200]
    out.append(rec)
    print(json.dumps(rec), flush=True)
