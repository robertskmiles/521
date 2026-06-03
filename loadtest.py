#!/usr/bin/env python3
"""
Stdlib-only async load tester for the letspick app.

Models the *real* client: each virtual user loads the room page once, then runs
the same conditional poll loop as static/script.js (GET /get_items?room_id&v with
1s->15s exponential backoff, reset to 1s whenever the version changes). On top of
that, users occasionally POST an action (/submit or /toggle), which bumps the
room version and snaps every other user back to fast polling -- the thundering
herd this app is most exposed to.

No third-party deps: raw HTTP/1.1 over asyncio (handles http and https).

Usage:
  python3 loadtest.py --url http://127.0.0.1:8000 --users 300 --duration 60
  python3 loadtest.py --url https://letspick.onrender.com --users 200 --duration 120 \
      --ramp 30 --action-interval 45
"""
import asyncio
import ssl
import json
import time
import random
import string
import argparse
from urllib.parse import urlparse
from collections import defaultdict, Counter

def item_text(i):
    return f"Track #{i:03d} - a fairly typical item text length"


def make_target(url):
    p = urlparse(url)
    scheme = p.scheme or "http"
    host = p.hostname
    port = p.port or (443 if scheme == "https" else 80)
    ctx = None
    if scheme == "https":
        ctx = ssl.create_default_context()
    return host, port, ctx


def dechunk(buf):
    """Decode HTTP/1.1 chunked transfer-encoding into the raw body."""
    out = bytearray()
    i = 0
    while i < len(buf):
        nl = buf.find(b"\r\n", i)
        if nl == -1:
            break
        try:
            size = int(buf[i:nl].split(b";")[0], 16)
        except ValueError:
            break
        if size == 0:
            break
        start = nl + 2
        out += buf[start:start + size]
        i = start + size + 2  # skip chunk data + trailing CRLF
    return bytes(out)


class Conn:
    """A persistent keep-alive connection for one virtual user, mirroring how a
    browser reuses its socket across polls. Reconnects transparently if dropped.
    Frames each response by Content-Length, chunked encoding, or close."""

    def __init__(self, target):
        self.target = target
        self.reader = None
        self.writer = None

    async def _connect(self, timeout):
        host, port, ctx = self.target
        self.reader, self.writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=ctx,
                                    server_hostname=host if ctx else None),
            timeout=timeout)

    def close(self):
        if self.writer is not None:
            try:
                self.writer.close()
            except Exception:
                pass
        self.reader = self.writer = None

    async def request(self, method, path, body=None, timeout=30.0):
        # Retry once on a stale reused keep-alive socket (server closed it while
        # idle). Browsers do this transparently; without it an idle backoff past
        # the server's keepalive timeout looks like a spurious error.
        reused = self.writer is not None and not self.writer.is_closing()
        try:
            return await self._send_recv(method, path, body, timeout)
        except (ConnectionError, asyncio.IncompleteReadError, EOFError) as e:
            self.close()
            if reused:
                return await self._send_recv(method, path, body, timeout)
            raise

    async def _send_recv(self, method, path, body=None, timeout=30.0):
        host = self.target[0]
        if self.writer is None or self.writer.is_closing():
            await self._connect(timeout)
        lines = [f"{method} {path} HTTP/1.1", f"Host: {host}",
                 "User-Agent: letspick-loadtest"]
        bb = b""
        if body is not None:
            bb = body.encode()
            lines += ["Content-Type: application/json", f"Content-Length: {len(bb)}"]
        req = ("\r\n".join(lines) + "\r\n\r\n").encode() + bb
        start = time.perf_counter()
        self.writer.write(req)
        await self.writer.drain()

        head = await asyncio.wait_for(self.reader.readuntil(b"\r\n\r\n"), timeout=timeout)
        htext = head.decode("latin1")
        status = int(htext.split("\r\n", 1)[0].split(" ")[1])
        hl = htext.lower()
        body_bytes = b""
        if "transfer-encoding: chunked" in hl:
            while True:
                szline = await asyncio.wait_for(self.reader.readuntil(b"\r\n"), timeout=timeout)
                size = int(szline.strip().split(b";")[0], 16)
                if size == 0:
                    await asyncio.wait_for(self.reader.readexactly(2), timeout=timeout)
                    break
                chunk = await asyncio.wait_for(self.reader.readexactly(size + 2), timeout=timeout)
                body_bytes += chunk[:-2]
        else:
            cl = None
            for ln in htext.split("\r\n")[1:]:
                if ln.lower().startswith("content-length:"):
                    cl = int(ln.split(":", 1)[1].strip())
                    break
            if cl is not None:
                body_bytes = await asyncio.wait_for(self.reader.readexactly(cl), timeout=timeout)
            else:
                body_bytes = await asyncio.wait_for(self.reader.read(), timeout=timeout)
        elapsed = (time.perf_counter() - start) * 1000.0
        if "connection: close" in hl:
            self.close()
        return status, body_bytes, elapsed


async def do_request(target, method, path, body=None, timeout=30.0):
    """One request over a fresh connection (Connection: close, read to EOF).
    Returns (status_code, body_bytes, elapsed_ms)."""
    host, port, ctx = target
    start = time.perf_counter()
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port, ssl=ctx,
                                server_hostname=host if ctx else None),
        timeout=timeout)
    try:
        lines = [f"{method} {path} HTTP/1.1",
                 f"Host: {host}",
                 "Connection: close",
                 "User-Agent: letspick-loadtest"]
        body_bytes = b""
        if body is not None:
            body_bytes = body.encode()
            lines.append("Content-Type: application/json")
            lines.append(f"Content-Length: {len(body_bytes)}")
        req = ("\r\n".join(lines) + "\r\n\r\n").encode() + body_bytes
        writer.write(req)
        await writer.drain()
        data = await asyncio.wait_for(reader.read(), timeout=timeout)
        elapsed = (time.perf_counter() - start) * 1000.0
        sep = data.find(b"\r\n\r\n")
        head = data[:sep].decode("latin1") if sep != -1 else data.decode("latin1")
        status = int(head.split("\r\n", 1)[0].split(" ")[1])
        bdy = data[sep + 4:] if sep != -1 else b""
        # Render's proxy uses chunked transfer-encoding; de-chunk so JSON parses.
        if "transfer-encoding: chunked" in head.lower():
            bdy = dechunk(bdy)
        return status, bdy, elapsed
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


class Stats:
    def __init__(self):
        self.lat = defaultdict(list)      # label -> [ms]
        self.status = Counter()           # http status -> count
        self.errors = Counter()           # error kind -> count
        self.adds = 0
        self.votes = 0
        self.changed_bytes = []           # payload size of "changed" polls

    def ok(self, label, ms, status):
        self.lat[label].append(ms)
        self.status[status] += 1

    def err(self, kind):
        self.errors[kind] += 1


def rand_id(n=8):
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(n))


async def submit(conn, room, uid, text, stats, req_timeout, label):
    payload = json.dumps({"room_id": room, "text": text, "user_id": uid})
    try:
        st, _, ms = await conn.request("POST", "/submit", body=payload, timeout=req_timeout)
        stats.ok(label, ms, st)
        return True
    except asyncio.TimeoutError:
        stats.err("timeout")
        conn.close()
    except Exception:
        stats.err("conn")
        conn.close()
    return False


async def preseed(target, room, n_items, stats, req_timeout):
    """Create n_items distinct entries and spread some early votes, so the room
    starts at a realistic list length / submitter density instead of empty."""
    conn = Conn(target)
    seeders = [rand_id() for _ in range(min(40, max(1, n_items)))]
    for i in range(n_items):
        await submit(conn, room, random.choice(seeders), item_text(i),
                     stats, req_timeout, "seed")
        # a few extra votes on this item so submitter lists aren't all length 1
        for _ in range(random.randint(0, 3)):
            await submit(conn, room, random.choice(seeders), item_text(i),
                         stats, req_timeout, "seed")
    conn.close()


async def virtual_user(target, room, stats, stop, action_interval, req_timeout,
                       n_items, add_ratio, counter, min_poll=1.0):
    uid = rand_id()
    conn = Conn(target)
    # Initial page load, like opening the room in a browser.
    try:
        st, _, ms = await conn.request("GET", f"/{room}", timeout=req_timeout)
        stats.ok("page", ms, st)
    except asyncio.TimeoutError:
        stats.err("timeout")
        conn.close()
    except Exception:
        stats.err("conn")
        conn.close()

    version = None  # first poll omits v -> forces a full sync, like the client
    floor = min_poll  # effective poll floor: max(min_poll, server's poll_after)
    wait = floor
    # exponential inter-action gaps; some users act, the long tail rarely does
    next_action = time.time() + random.expovariate(1.0 / action_interval)

    while not stop.is_set():
        # ---- poll ----
        q = f"/get_items?room_id={room}" + (f"&v={version}" if version is not None else "")
        try:
            st, body, ms = await conn.request("GET", q, timeout=req_timeout)
            stats.ok("poll", ms, st)
            if st == 200:
                try:
                    resp = json.loads(body)
                    # Honor the server's adaptive rate hint, like script.js does.
                    pa = resp.get("poll_after")
                    floor = max(min_poll, pa / 1000.0) if pa else min_poll
                    if resp.get("changed", True):
                        version = resp.get("version", version)
                        wait = floor
                        if "items" in resp:
                            stats.changed_bytes.append(len(body))
                    else:
                        version = resp.get("version", version)
                        wait = min(max(wait * 1.5, floor), 15.0)
                except Exception:
                    wait = min(wait * 1.5, 15.0)
            else:
                wait = min(wait * 1.5, 15.0)
        except asyncio.TimeoutError:
            stats.err("timeout")
            conn.close()
            wait = floor
        except Exception:
            stats.err("conn")
            conn.close()
            wait = floor

        # ---- maybe act: add a NEW item, or vote on an existing one ----
        # Both bump the room version (-> herd resets), but only an add grows N.
        if time.time() >= next_action and not stop.is_set():
            if random.random() < add_ratio:
                counter["n"] += 1
                if await submit(conn, room, uid, item_text(counter["n"]),
                                stats, req_timeout, "action"):
                    stats.adds += 1
            else:
                # vote == submit an existing item text (appends uid to submitters)
                existing = random.randint(0, max(0, counter["n"]))
                if await submit(conn, room, uid, item_text(existing),
                                stats, req_timeout, "action"):
                    stats.votes += 1
            next_action = time.time() + random.expovariate(1.0 / action_interval)

        # sleep until next poll (interruptible by stop), with ±15% jitter to
        # avoid lockstep polling -- matching script.js.
        try:
            await asyncio.wait_for(stop.wait(), timeout=wait * (0.85 + random.random() * 0.3))
        except asyncio.TimeoutError:
            pass


def pct(vals, p):
    if not vals:
        return 0.0
    s = sorted(vals)
    k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
    return s[k]


def report(stats, wall, users):
    # req/s reflects the steady window only (pre-seed runs before the clock starts)
    in_window = sum(len(v) for k, v in stats.lat.items() if k != "seed")
    total = sum(len(v) for v in stats.lat.values())
    cb = stats.changed_bytes
    print("\n" + "=" * 64)
    print(f"  RESULTS  ({users} users, {wall:.1f}s wall)")
    print("=" * 64)
    print(f"  requests:        {in_window}  ({in_window / wall:.1f} req/s)"
          f"   [+{total - in_window} pre-seed]")
    print(f"  actions:         {stats.adds} adds + {stats.votes} votes")
    if cb:
        print(f"  changed-poll payload: p50 {pct(cb,50)/1024:.1f}KB  "
              f"max {max(cb)/1024:.1f}KB  ({len(cb)} full responses)")
    print(f"  http status:     {dict(stats.status)}")
    print(f"  errors:          {dict(stats.errors) if stats.errors else 'none'}")
    print(f"\n  {'label':<8}{'count':>8}{'p50':>9}{'p90':>9}{'p99':>9}{'max':>9}   (ms)")
    print("  " + "-" * 58)
    for label in ("page", "poll", "action", "seed"):
        v = stats.lat.get(label)
        if not v:
            continue
        print(f"  {label:<8}{len(v):>8}{pct(v,50):>9.0f}{pct(v,90):>9.0f}"
              f"{pct(v,99):>9.0f}{max(v):>9.0f}")
    print("=" * 64)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--users", type=int, default=200)
    ap.add_argument("--duration", type=float, default=60.0, help="seconds of steady load")
    ap.add_argument("--ramp", type=float, default=10.0, help="seconds to ramp all users in")
    ap.add_argument("--room", default="loadtest")
    ap.add_argument("--action-interval", type=float, default=45.0,
                    help="avg seconds between a user's actions (lower = busier room)")
    ap.add_argument("--items", type=int, default=80,
                    help="distinct items to pre-seed before the test (list length)")
    ap.add_argument("--add-ratio", type=float, default=0.2,
                    help="fraction of actions that add a NEW item vs vote on existing")
    ap.add_argument("--timeout", type=float, default=30.0, help="per-request timeout (s)")
    ap.add_argument("--min-poll", type=float, default=1.0,
                    help="client's minimum poll interval (script.js floor is 1.0s)")
    args = ap.parse_args()

    target = make_target(args.url)
    stats = Stats()
    stop = asyncio.Event()

    # Warmup / cold-start probe (Render free tier spins down when idle).
    print(f"warming up {args.url} ...")
    try:
        st, _, ms = await do_request(target, "GET", f"/{args.room}", timeout=90.0)
        print(f"  first hit: HTTP {st} in {ms:.0f} ms"
              + ("  (likely cold start)" if ms > 1500 else ""))
    except Exception as e:
        print(f"  WARNING: warmup failed: {e!r}")

    counter = {"n": 0}  # shared running index of distinct items created
    if args.items > 0:
        print(f"pre-seeding {args.items} items ...")
        await preseed(target, args.room, args.items, stats, args.timeout)
        counter["n"] = args.items

    print(f"ramping {args.users} users over {args.ramp}s, then {args.duration}s steady "
          f"(action ~{args.action_interval}s/user, add-ratio {args.add_ratio})")
    tasks = []
    t0 = time.perf_counter()
    for i in range(args.users):
        tasks.append(asyncio.create_task(
            virtual_user(target, args.room, stats, stop,
                         args.action_interval, args.timeout,
                         args.items, args.add_ratio, counter, args.min_poll)))
        if args.ramp > 0:
            await asyncio.sleep(args.ramp / args.users)

    await asyncio.sleep(args.duration)
    stop.set()
    await asyncio.gather(*tasks, return_exceptions=True)
    wall = time.perf_counter() - t0
    report(stats, wall, args.users)


if __name__ == "__main__":
    asyncio.run(main())
