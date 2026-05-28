"""FastAPI WebSocket bridge for MVP1 "Inbox bajo presión" demo."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from ..world.world import World, WorldConfig

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent.parent.parent.parent.parent / "static"

_NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}


def _frame_to_dict(frame: Any) -> dict:
    d = dataclasses.asdict(frame)
    d["type"] = "frame"
    return d


class _NoCacheMiddleware(BaseHTTPMiddleware):
    """Force no-cache on ALL responses — demo must always show latest code."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        # Strip ETag/Last-Modified so browser cannot do conditional GET
        for h in ("etag", "last-modified"):
            if h in response.headers:
                del response.headers[h]
        return response


def create_app(config: WorldConfig | None = None) -> FastAPI:
    app = FastAPI(title="Binsai MVP1")
    app.add_middleware(_NoCacheMiddleware)

    world      = World(config or WorldConfig())
    running    = False
    connections: set[WebSocket] = set()

    async def broadcast(data: dict) -> None:
        dead: set[WebSocket] = set()
        for ws in list(connections):
            try:
                await ws.send_json(data)
            except Exception:
                dead.add(ws)
        connections.difference_update(dead)

    async def simulation_loop() -> None:
        nonlocal running
        loop = asyncio.get_event_loop()
        while True:
            if running:
                frame = await loop.run_in_executor(None, world.step)
                await broadcast(_frame_to_dict(frame))
                await asyncio.sleep(1.0 / world.config.speed)
            else:
                await asyncio.sleep(0.05)

    @app.on_event("startup")
    async def _startup() -> None:
        asyncio.create_task(simulation_loop())

    @app.websocket("/ws/sim")
    async def ws_endpoint(websocket: WebSocket) -> None:
        nonlocal running
        await websocket.accept()
        connections.add(websocket)
        logger.info("Client connected. Total: %d", len(connections))

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "message": "invalid JSON"})
                    continue

                cmd = msg.get("cmd", "")

                if cmd == "start":
                    running = True
                elif cmd == "pause":
                    running = False
                elif cmd == "reset":
                    running = False
                    world.reset()
                    await broadcast({"type": "control", "event": "reset"})
                elif cmd == "toggle_ablation":
                    new_val = world.toggle_ablation()
                    await broadcast({
                        "type":        "control",
                        "event":       "ablation_toggled",
                        "ablation_off": new_val,
                    })
                elif cmd == "set_speed":
                    val = float(msg.get("value", 2.0))
                    world.config.speed = max(0.1, min(val, 20.0))
                elif cmd == "set_lambda_demand":
                    val = float(msg.get("value", 0.5))
                    world.set_lambda_demand(max(0.0, min(val, 5.0)))
                elif cmd == "toggle_ablation_agent":
                    aid = msg.get("aid", "")
                    try:
                        new_val = world.toggle_ablation_agent(aid)
                        await broadcast({
                            "type":        "control",
                            "event":       "agent_ablation_toggled",
                            "aid":         aid,
                            "ablation_off": new_val,
                        })
                    except ValueError as e:
                        await websocket.send_json({"type": "error", "message": str(e)})
                elif cmd == "set_budgets":
                    cost    = float(msg.get("cost_per_call_usd",   0.001))
                    latency = float(msg.get("latency_per_call_ms", 4000))
                    tokens  = int(  msg.get("tokens_per_call",     300))
                    for a in world.agents:
                        a.budgets.cost_per_call_usd   = max(1e-6, cost)
                        a.budgets.latency_per_call_ms = max(100,  int(latency))
                        a.budgets.tokens_per_call     = max(10,   tokens)
                        a.budgets._window             = []
                else:
                    await websocket.send_json({"type": "error", "message": f"unknown cmd: {cmd}"})

        except WebSocketDisconnect:
            connections.discard(websocket)
            logger.info("Client disconnected. Total: %d", len(connections))

    # HTML routes MUST be registered BEFORE the static mount so they take precedence.
    # StaticFiles returns 304 (cached) for HTML; these routes force no-cache headers.
    if STATIC_DIR.exists():
        @app.get("/")
        async def root() -> HTMLResponse:
            return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"), headers=_NO_CACHE)

        @app.get("/static/index.html")
        async def static_index() -> HTMLResponse:
            return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"), headers=_NO_CACHE)

        # Mount after routes — explicit routes take precedence in Starlette's router
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app


def run(host: str = "localhost", port: int = 8765, config: WorldConfig | None = None) -> None:
    import uvicorn
    app = create_app(config)
    uvicorn.run(app, host=host, port=port, log_level="info")
