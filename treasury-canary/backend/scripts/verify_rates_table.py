"""Behavioral check for the EWM rate table: load static.html in headless
chromium with the API stubbed and assert the rates fetch actually FIRES and
the table RENDERS, on both the direct /ewm/ base and the proxied /exit/ base.

Exists because string gates passed for two commits while the fetch sat in
dead code after a `return` inside refreshBoard() (counter-agent find,
2026-08-11). String presence is not reachability; this script is the
reachability check. Not wired into pytest to keep CI free of a browser
dependency - run manually after touching static.html's script block:

    python scripts/verify_rates_table.py
"""
import asyncio
import os
import sys

from playwright.async_api import async_playwright

HTML_PATH = os.path.join(os.path.dirname(__file__), "..", "app", "ewm",
                         "static.html")
CHROMIUM = os.environ.get("VERIFY_CHROMIUM", "/opt/pw-browsers/chromium")

BOARD = {"headline": {}, "plan": None, "inputs": {}, "rows": [], "auto": {},
         "vs_cohort": {}}
RATES = {"weights": {"polymarket": .5, "kalshi": .3, "futures": .2},
         "buckets": ["cut25", "hold"],
         "labels": {"cut25": "-25bp", "hold": "hold"},
         "meetings": [{"date": "2026-09-16",
                       "blend": {"cut25": 0.62, "hold": 0.38},
                       "sources": {"polymarket": {"cut25": 0.6},
                                   "kalshi": {}, "futures": {}}}]}


async def check_base(pw, base: str) -> None:
    html = open(HTML_PATH).read()
    reqs: list[str] = []
    launch = {"executable_path": CHROMIUM} if os.path.exists(CHROMIUM) else {}
    browser = await pw.chromium.launch(**launch)
    page = await browser.new_page()

    async def route(r):
        u = r.request.url
        reqs.append(u)
        if "api/ewm/rates" in u:
            await r.fulfill(json=RATES)
        elif "api/ewm/board" in u:
            await r.fulfill(json=BOARD)
        elif u.rstrip("/").endswith(base.strip("/")):
            await r.fulfill(body=html, content_type="text/html")
        else:
            await r.fulfill(json={})

    await page.route("**/*", route)
    await page.goto(f"https://stub.local{base}")
    await page.wait_for_timeout(1200)
    tbl = await page.eval_on_selector("#ratetbl", "e=>e.innerHTML")
    await browser.close()

    api = [u.split("stub.local/")[-1] for u in reqs if "api/" in u]
    want = f"{base.strip('/')}/api/ewm/rates"
    assert want in api, f"{base}: rates fetch missing/escaped prefix: {api}"
    assert "Sep 16" in tbl and "62.0%" in tbl, \
        f"{base}: table did not render: {tbl[:200]}"
    print(f"PASS {base}: fetches {api}, table renders")


async def main() -> None:
    async with async_playwright() as pw:
        await check_base(pw, "/ewm/")    # direct service URL
        await check_base(pw, "/exit/")   # genomics reverse-proxy prefix


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        sys.exit(1)
