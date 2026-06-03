#!/usr/bin/env python3
"""Drive the local server over its rate budget and watch poll_after react."""
import asyncio, json, time
from loadtest import Conn, make_target

URL = "http://127.0.0.1:8000"
ROOM = "ctl"


async def poll_after():
    c = Conn(make_target(URL))
    s, b, _ = await c.request("GET", f"/get_items?room_id={ROOM}&v=-1")
    c.close()
    return json.loads(b).get("poll_after")


async def main():
    # seed
    c = Conn(make_target(URL))
    await c.request("POST", "/submit", body=json.dumps({"room_id": ROOM, "text": "A", "user_id": "u"}))
    c.close()
    print("idle poll_after:", await poll_after())

    # hammer well over the 75 req/s budget for ~8s
    stop = time.time() + 8
    async def worker():
        conn = Conn(make_target(URL))
        while time.time() < stop:
            try:
                await conn.request("GET", f"/get_items?room_id={ROOM}&v=-1", timeout=30)
            except Exception:
                conn.close()
        conn.close()
    drivers = [asyncio.create_task(worker()) for _ in range(60)]
    # sample poll_after while under load
    for _ in range(7):
        await asyncio.sleep(1)
        print("under load poll_after:", await poll_after())
    await asyncio.gather(*drivers)

    # watch it decay after load stops
    for _ in range(6):
        await asyncio.sleep(1)
        print("recovering poll_after:", await poll_after())


asyncio.run(main())
