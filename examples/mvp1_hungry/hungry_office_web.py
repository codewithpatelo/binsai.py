"""
MVP 1 Demo: Web Browser Version 🌐🏢🧠⚡

Demo visual en navegador usando HTML5 Canvas + JavaScript generado por Python.
Sirve la simulación en localhost para visualización en tiempo real.

Usage:
    python hungry_office_web.py
    # Abre http://localhost:8080 en tu navegador

Incluye:
    - Canvas 320x200 pixel art escalado
    - Agentes 8-bit animados
    - Barras de drives en tiempo real
    - Speech bubbles
    - Controles web (play/pause/reset)
"""

from __future__ import annotations

import json
import random
import sys
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from dataclasses import asdict

sys.path.insert(0, "../../src")

from binsai import BinsaiAgent, Drives


class SimulationState:
    """Shared state between simulation and web server."""
    
    def __init__(self):
        self.agents: list[dict] = []
        self.entities: list[dict] = []
        self.frame = 0
        self.running = True
        self.paused = False
        self.messages: list[str] = []
        self.lock = threading.Lock()
        
    def update(self, visual_agents: list, entities: list, frame: int):
        """Update state from simulation thread."""
        with self.lock:
            self.agents = []
            for va in visual_agents:
                agent_data = {
                    "name": va.binsai_agent.name,
                    "x": va.x,
                    "y": va.y,
                    "role": va.role,
                    "sprite_color": va.sprite_color,
                    "drives": va.binsai_agent.drives.to_dict(),
                    "bubbles": [
                        {"text": b.text, "remaining": b.duration - (time.time() - b.created_at)}
                        for b in va._bubbles if not b.is_expired()
                    ],
                    "wobble": va._wobble,
                }
                self.agents.append(agent_data)
            
            self.entities = [
                {"type": type(e).__name__, "x": e.x, "y": e.y, 
                 "width": getattr(e, 'width', 20), "height": getattr(e, 'height', 16),
                 "name": getattr(e, 'name', ''), "color": getattr(e, 'color', 4)}
                for e in entities
            ]
            self.frame = frame
    
    def to_json(self) -> str:
        """Export state as JSON."""
        with self.lock:
            return json.dumps({
                "agents": self.agents,
                "entities": self.entities,
                "frame": self.frame,
                "running": self.running,
                "paused": self.paused,
                "messages": self.messages[-5:],  # Last 5 messages
            })


# Global state shared between threads
STATE = SimulationState()


class RequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for serving the web interface."""
    
    def do_GET(self):
        """Handle GET requests."""
        path = self.path
        
        if path == "/" or path == "/index.html":
            self._serve_html()
        elif path == "/api/state":
            self._serve_state()
        elif path.startswith("/api/"):
            self._handle_api(path)
        else:
            self._serve_404()
    
    def _serve_html(self):
        """Serve the main HTML page."""
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(HTML_PAGE.encode())
    
    def _serve_state(self):
        """Serve current simulation state as JSON."""
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(STATE.to_json().encode())
    
    def _handle_api(self, path: str):
        """Handle API commands."""
        global STATE
        
        if path == "/api/pause":
            STATE.paused = not STATE.paused
            self._serve_json({"paused": STATE.paused})
        elif path == "/api/reset":
            self._serve_json({"status": "reset_requested"})
        else:
            self._serve_404()
    
    def _serve_json(self, data: dict):
        """Serve JSON response."""
        self.send_response(200)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def _serve_404(self):
        """Serve 404 error."""
        self.send_response(404)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Not found")
    
    def log_message(self, format, *args):
        """Suppress request logging."""
        pass


# HTML + JavaScript page
HTML_PAGE = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>MVP 1: Hungry Agents Office 🏢🧠⚡</title>
    <style>
        body {
            background: #1a1a2e;
            color: #eee;
            font-family: 'Courier New', monospace;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 20px;
            margin: 0;
        }
        h1 {
            color: #00d4aa;
            margin: 0 0 10px 0;
            font-size: 18px;
        }
        .subtitle {
            color: #888;
            font-size: 12px;
            margin-bottom: 20px;
        }
        #canvas-container {
            position: relative;
            border: 3px solid #00d4aa;
            border-radius: 4px;
            box-shadow: 0 0 20px rgba(0, 212, 170, 0.3);
        }
        canvas {
            image-rendering: pixelated;
            image-rendering: crisp-edges;
            background: #0f0f1a;
        }
        #controls {
            margin-top: 15px;
            display: flex;
            gap: 10px;
        }
        button {
            background: #16213e;
            color: #00d4aa;
            border: 1px solid #00d4aa;
            padding: 8px 16px;
            font-family: inherit;
            cursor: pointer;
            border-radius: 4px;
            font-size: 12px;
        }
        button:hover {
            background: #00d4aa;
            color: #1a1a2e;
        }
        #info {
            margin-top: 15px;
            font-size: 11px;
            color: #666;
        }
        .drive-legend {
            display: flex;
            gap: 15px;
            margin-top: 10px;
            font-size: 11px;
        }
        .drive-item {
            display: flex;
            align-items: center;
            gap: 5px;
        }
        .drive-bar {
            width: 20px;
            height: 8px;
            border-radius: 2px;
        }
        .low { background: #e74c3c; }
        .nominal { background: #2ecc71; }
        .high { background: #00d4aa; }
    </style>
</head>
<body>
    <h1>🏢 MVP 1: Hungry Agents Office 🧠⚡</h1>
    <div class="subtitle">δ_metabolic + δ_safety regulate agent behavior</div>
    
    <div id="canvas-container">
        <canvas id="simCanvas" width="320" height="200"></canvas>
    </div>
    
    <div id="controls">
        <button onclick="togglePause()">⏯ Pause/Play</button>
        <button onclick="resetSim()">🔄 Reset</button>
    </div>
    
    <div class="drive-legend">
        <div class="drive-item"><div class="drive-bar low"></div> δ LOW (critical)</div>
        <div class="drive-item"><div class="drive-bar nominal"></div> δ nominal</div>
        <div class="drive-item"><div class="drive-bar high"></div> δ HIGH (abundant)</div>
    </div>
    
    <div id="info">Frame: <span id="frame">0</span> | Agents: <span id="agentCount">0</span></div>

    <script>
        const canvas = document.getElementById('simCanvas');
        const ctx = canvas.getContext('2d');
        const scale = 3;
        
        // Scale canvas for pixel art look
        canvas.style.width = (320 * scale) + 'px';
        canvas.style.height = (200 * scale) + 'px';
        
        let state = { agents: [], entities: [], frame: 0 };
        
        // Color palette (matching pyxel)
        const COLORS = {
            bg: '#0f0f1a',
            desk: '#34495e',
            deskDark: '#2c3e50',
            screen: '#00d4aa',
            zoneMeeting: 'rgba(52, 152, 219, 0.2)',
            zoneBreak: 'rgba(231, 76, 60, 0.2)',
            zoneCollab: 'rgba(46, 204, 113, 0.2)',
            text: '#ecf0f1',
            bubble: '#2c3e50',
            driveLow: '#e74c3c',
            driveNominal: '#2ecc71',
            driveHigh: '#00d4aa',
        };
        
        // Agent sprites (8x8)
        const SPRITES = {
            developer: [
                "........",
                "..XXXX..",
                ".XXXXXX.",
                "..XXXX..",
                ".X.XX.X.",
                "XXXXXXXX",
                ".XX..XX.",
                ".XX..XX.",
            ],
            analyst: [
                "........",
                "..XXXX..",
                ".XXXXXX.",
                "..XXXX..",
                ".XXXXXX.",
                "XXXXXXXX",
                "..XXXX..",
                ".XX..XX.",
            ],
        };
        
        function drawSprite(ctx, x, y, sprite, color, wobble = 0) {
            const pixelSize = 2;
            const offsetY = Math.sin(wobble) * 2;
            
            ctx.fillStyle = color;
            for (let row = 0; row < 8; row++) {
                for (let col = 0; col < 8; col++) {
                    if (sprite[row] && sprite[row][col] === 'X') {
                        ctx.fillRect(
                            x - 8 + col * pixelSize,
                            y - 16 + row * pixelSize + offsetY,
                            pixelSize,
                            pixelSize
                        );
                    }
                }
            }
        }
        
        function drawRoundedRect(ctx, x, y, w, h, color, radius = 4) {
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.roundRect(x, y, w, h, radius);
            ctx.fill();
        }
        
        function drawSpeechBubble(ctx, x, y, text) {
            const maxWidth = 120;
            const lines = [];
            let line = '';
            
            // Simple word wrap
            const words = text.split(' ');
            for (const word of words) {
                if ((line + word).length * 6 < maxWidth) {
                    line += word + ' ';
                } else {
                    lines.push(line);
                    line = word + ' ';
                }
            }
            lines.push(line);
            
            const lineHeight = 12;
            const bubbleWidth = Math.min(maxWidth, text.length * 6 + 10);
            const bubbleHeight = lines.length * lineHeight + 8;
            const bx = x - bubbleWidth / 2;
            const by = y - bubbleHeight - 25;
            
            // Background
            drawRoundedRect(ctx, bx, by, bubbleWidth, bubbleHeight, COLORS.bubble);
            
            // Pointer triangle
            ctx.fillStyle = COLORS.bubble;
            ctx.beginPath();
            ctx.moveTo(x - 5, by + bubbleHeight);
            ctx.lineTo(x, by + bubbleHeight + 6);
            ctx.lineTo(x + 5, by + bubbleHeight);
            ctx.fill();
            
            // Text
            ctx.fillStyle = COLORS.text;
            ctx.font = '10px monospace';
            lines.forEach((l, i) => {
                ctx.fillText(l.trim(), bx + 5, by + 14 + i * lineHeight);
            });
        }
        
        function drawDriveBars(ctx, x, y, drives) {
            const barWidth = 24;
            const barHeight = 4;
            const spacing = 7;
            
            Object.entries(drives).slice(0, 3).forEach(([name, drive], i) => {
                const value = drive.value;
                const zone = drive.zone;
                
                // Background
                ctx.fillStyle = '#34495e';
                ctx.fillRect(x - barWidth/2, y - 30 + i * spacing, barWidth, barHeight);
                
                // Fill
                let color = COLORS.driveNominal;
                if (zone === 'low') color = COLORS.driveLow;
                if (zone === 'high') color = COLORS.driveHigh;
                
                ctx.fillStyle = color;
                ctx.fillRect(x - barWidth/2, y - 30 + i * spacing, barWidth * value, barHeight);
            });
        }
        
        function drawDesk(ctx, entity) {
            const { x, y, width, height, color } = entity;
            
            // Table top
            ctx.fillStyle = COLORS.desk;
            ctx.fillRect(x, y, width, 4);
            
            // Legs
            ctx.fillStyle = COLORS.deskDark;
            ctx.fillRect(x + 2, y + 4, 2, height - 4);
            ctx.fillRect(x + width - 4, y + 4, 2, height - 4);
            
            // Monitor
            ctx.fillStyle = '#1a1a2e';
            ctx.fillRect(x + 4, y - 6, 8, 6);
            ctx.fillStyle = COLORS.screen;
            ctx.fillRect(x + 5, y - 5, 6, 4);
        }
        
        function drawZone(ctx, entity) {
            const { x, y, width, height, name, color } = entity;
            
            // Stippled pattern
            ctx.fillStyle = color;
            for (let dx = 0; dx < width; dx += 8) {
                for (let dy = 0; dy < height; dy += 8) {
                    if ((dx + dy) % 16 === 0) {
                        ctx.fillRect(x + dx, y + dy, 2, 2);
                    }
                }
            }
            
            // Label
            ctx.fillStyle = '#888';
            ctx.font = '9px monospace';
            ctx.fillText(name, x + 2, y - 4);
        }
        
        function draw() {
            // Clear
            ctx.fillStyle = COLORS.bg;
            ctx.fillRect(0, 0, 320, 200);
            
            // Draw entities (background)
            state.entities.forEach(entity => {
                if (entity.type === 'Desk') drawDesk(ctx, entity);
                if (entity.type === 'Zone') drawZone(ctx, entity);
            });
            
            // Draw agents
            state.agents.forEach(agent => {
                const { x, y, role, sprite_color, drives, bubbles, wobble } = agent;
                
                // Sprite
                const sprite = SPRITES[role] || SPRITES.developer;
                const color = sprite_color === 11 ? '#00d4aa' : 
                             sprite_color === 8 ? '#e74c3c' : 
                             sprite_color === 12 ? '#3498db' : '#9b59b6';
                drawSprite(ctx, x, y, sprite, color, wobble);
                
                // Name
                ctx.fillStyle = COLORS.text;
                ctx.font = '9px monospace';
                ctx.fillText(agent.name, x - agent.name.length * 3, y + 6);
                
                // Drive bars
                drawDriveBars(ctx, x, y, drives);
                
                // Speech bubbles
                bubbles.forEach(bubble => {
                    if (bubble.remaining > 0) {
                        drawSpeechBubble(ctx, x, y, bubble.text);
                    }
                });
            });
            
            // UI overlay
            ctx.fillStyle = COLORS.text;
            ctx.font = '10px monospace';
            ctx.fillText('Hungry Agents Office 🏢', 10, 15);
            ctx.fillText(`Frame: ${state.frame}`, 10, 185);
        }
        
        async function fetchState() {
            try {
                const resp = await fetch('/api/state');
                state = await resp.json();
                document.getElementById('frame').textContent = state.frame;
                document.getElementById('agentCount').textContent = state.agents.length;
            } catch (e) {
                console.error('Failed to fetch state:', e);
            }
        }
        
        async function togglePause() {
            await fetch('/api/pause');
        }
        
        async function resetSim() {
            await fetch('/api/reset');
        }
        
        // Main loop
        function loop() {
            draw();
            requestAnimationFrame(loop);
        }
        
        // Fetch state periodically
        setInterval(fetchState, 100); // 10fps state updates
        
        // Start
        loop();
    </script>
</body>
</html>
'''


def run_simulation():
    """Run simulation in background thread."""
    from binsai.simulation.entities import VisualAgent, Desk, Zone, SpeechBubble
    from binsai.simulation.environment import OfficeEnvironment
    
    # Create agents
    ana = BinsaiAgent(
        name="Ana",
        drives=Drives.from_names(["metabolic", "safety"]),
        metadata={"personality": "optimistic", "role": "developer"}
    )
    
    bruno = BinsaiAgent(
        name="Bruno",
        drives=Drives.from_names(["metabolic", "safety"]),
        metadata={"personality": "skeptical", "role": "analyst"}
    )
    
    # Create visual agents manually (no pyxel needed)
    visual_ana = VisualAgent(ana, x=50, y=80, role="developer", sprite_color=11)
    visual_bruno = VisualAgent(bruno, x=200, y=100, role="analyst", sprite_color=8)
    
    visual_agents = [visual_ana, visual_bruno]
    
    # Create entities
    entities = [
        Desk(40, 90, 24, 16, 4),
        Desk(190, 110, 24, 16, 4),
        Zone(120, 60, 80, 60, "Meeting", 3),
        Zone(260, 20, 50, 40, "Break", 9),
    ]
    
    # Debate messages
    debate_messages = [
        ("Ana", "La consciencia emerge de la integración de información."),
        ("Bruno", "Sin cuerpo, sin emoción, sin relación con el mundo."),
        ("Ana", "Un sistema suficientemente complejo puede tener experiencia subjetiva."),
        ("Bruno", "Procesar símbolos ≠ experimentar qualia."),
        ("Ana", "¿No somos nosotros también procesos computacionales?"),
        ("Bruno", "La consciencia requiere encarnación (embodiment)."),
    ]
    
    message_idx = 0
    last_message_time = time.time()
    
    frame = 0
    while STATE.running:
        if not STATE.paused:
            frame += 1
            
            # Update agents
            for va in visual_agents:
                va.update()
                
                # Idle wobble animation
                va._wobble += 0.1
            
            # Send messages periodically
            if time.time() - last_message_time > 4:
                if message_idx < len(debate_messages):
                    name, text = debate_messages[message_idx]
                    for va in visual_agents:
                        if va.binsai_agent.name == name:
                            va.say(text, duration=3.5)
                            # Consume tokens
                            va.binsai_agent.emit("token_consumed", {"cost": 0.05})
                            # Occasional error
                            if random.random() < 0.2:
                                va.binsai_agent.emit("error", {"type": "semantic"})
                    message_idx += 1
                    last_message_time = time.time()
            
            # Update shared state
            STATE.update(visual_agents, entities, frame)
        
        time.sleep(1/60)  # 60fps simulation


def main():
    """Legacy wrapper. Delegates to unified simulation runner in web mode."""
    from binsai.simulation.runner import main as runner_main
    import sys as _sys
    _sys.argv = [_sys.argv[0], "--mode", "web"]
    runner_main()


if __name__ == "__main__":
    main()
