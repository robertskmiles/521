#!/usr/bin/env python3
"""Measure max req/s and CPU-cost-per-request of the local gunicorn worker.

Reads the worker's utime+stime from /proc before/after a saturating closed-loop
of requests, so we get actual CPU seconds spent per request. Compares the cheap
conditional-poll path vs the full item-list path.
"""
import asyncio, json, os, time, sys
from loadtest import Conn, make_target

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
ROOM = "prof"
CLK = os.sysconf("SC_CLK_TCK")


def gunicorn_pids():
    pids = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmd = f.read().replace(b"\x00", b" ").decode("latin1")
        except Exception:
            continue
        if "gunicorn server:app" in cmd:
            pids.append(int(pid))
    return pids


def cpu_ticks(pids):
    total = 0
    for pid in pids:
        try:
            with open(f"/proc/{pid}/stat") as f:
                parts = f.read().split()
            total += int(parts[13]) + int(parts[14])  # utime + stime
        except Exception:
            pass
    return total


async def seed():
    c = Conn(make_target(URL))
    for i in range(80):
        name = f"Track #{i:03d} - a fairly typical item text length"
        await c.request("POST", "/submit",
                        body=json.dumps({"room_id": ROOM, "text": name,
                                         "user_id": "u%d" % (i % 30)}))
    s, b, _ = await c.request("GET", f"/get_items?room_id={ROOM}")
    c.close()
    return json.loads(b)["version"], len(b)


async def bench(path, concurrency, duration, pids):
    stop = time.time() + duration
    counts = [0]
    lat = []

    async def worker():
        conn = Conn(make_target(URL))
        while time.time() < stop:
            try:
                s, b, m = await conn.request("GET", path, timeout=30)
                counts[0] += 1
                lat.append(m)
            except Exception:
                conn.close()
        conn.close()

    t0 = time.time()
    c0 = cpu_ticks(pids)
    await asyncio.gather(*[worker() for _ in range(concurrency)])
    c1 = cpu_ticks(pids)
    el = time.time() - t0
    cpu_s = (c1 - c0) / CLK
    n = counts[0]
    lat.sort()
    p50 = lat[len(lat) // 2]
    p99 = lat[min(len(lat) - 1, int(0.99 * len(lat)))]
    return n, el, cpu_s, p50, p99


async def main():
    pids = gunicorn_pids()
    print("gunicorn pids:", pids)
    ver, nbytes = await seed()
    print(f"seeded room: version={ver}, full-path payload={nbytes} bytes\n")

    cheap = f"/get_items?room_id={ROOM}&v={ver}"     # changed:false, tiny
    full = f"/get_items?room_id={ROOM}&v=-1"         # always changed:true, full list

    for label, path in [("cheap (changed:false)", cheap),
                        ("full  (80-item list) ", full)]:
        n, el, cpu_s, p50, p99 = await bench(path, concurrency=40, duration=8, pids=pids)
        rps = n / el
        cpu_ms = (cpu_s / n) * 1000 if n else 0
        # On 0.1 CPU you get 100ms CPU per wall-second:
        est_throttled = 100.0 / cpu_ms if cpu_ms else 0
        print(f"{label}: {rps:7.0f} req/s on full core | "
              f"{cpu_ms:5.2f} ms CPU/req | p50 {p50:4.0f}ms p99 {p99:4.0f}ms")
        print(f"{'':22}  -> at 0.1 CPU (Render free) ~= {est_throttled:.0f} req/s\n")


if __name__ == "__main__":
    asyncio.run(main())
