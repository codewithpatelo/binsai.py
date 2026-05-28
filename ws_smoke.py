import asyncio
import json
import websockets

async def main():
    async with websockets.connect("ws://localhost:8765/ws/sim") as ws:
        await ws.send(json.dumps({"cmd": "start"}))
        frames = []
        for _ in range(5):
            raw = await asyncio.wait_for(ws.recv(), timeout=30)
            msg = json.loads(raw)
            if msg.get("type") == "frame":
                frames.append(msg)
                ag = msg["agents"][0]
                print(f"tick={msg['tick']}  {ag['name']} delta={ag['delta']}  zone={ag['zone']}  action={ag['action']}")
        print(f"\nGot {len(frames)} frames OK")
        for f in frames:
            for ev in f.get("events", []):
                if ev.get("type") == "action.complete":
                    p = ev["payload"]
                    print(f"  action.complete: {p.get('agent')} -> {p.get('action')} | result={p.get('result')}")

asyncio.run(main())
