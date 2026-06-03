#!/usr/bin/env python3
"""Measure the live server's raw throughput ceiling by hammering it with more
concurrency than it can serve (ignoring poll_after). Reveals true capacity."""
import asyncio, json, time, sys
from loadtest import Conn, make_target

URL = sys.argv[1] if len(sys.argv) > 1 else "https://letspick.onrender.com"
ROOM = "lt-ceiling-2026"


async def main():
    t = make_target(URL)
    c = Conn(t)
    await c.request("POST", "/submit", body=json.dumps({"room_id": ROOM, "text": "A", "user_id": "x"}))
    c.close()

    N, DUR = 50, 12
    stop = time.time() + DUR
    counts = [0]
    lat = []

    async def worker():
        conn = Conn(t)
        while time.time() < stop:
            try:
                s, b, m = await conn.request("GET", f"/get_items?room_id={ROOM}&v=-1", timeout=30)
                counts[0] += 1
                lat.append(m)
            except Exception:
                conn.close()
        conn.close()

    t0 = time.time()
    await asyncio.gather(*[worker() for _ in range(N)])
    el = time.time() - t0
    lat.sort()
    p = lambda q: lat[min(len(lat) - 1, int(q * len(lat)))] if lat else 0
    print(f"CEILING: {counts[0]/el:.0f} req/s sustained "
          f"(p50 {p(.5):.0f}ms p99 {p(.99):.0f}ms, {N} hammering conns)")


asyncio.run(main())
