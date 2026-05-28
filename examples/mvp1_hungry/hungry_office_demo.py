"""
MVP 1 Demo: "Hungry Agents in the Office" 🏢🧠⚡

Demo visual pixelart de dos agentes en oficina, debatiendo sobre IA y consciencia.
- Entorno: Oficina con escritorios, zona de meeting, break room
- Agentes: Personajes 8-bit con drives metabolic y safety
- Visualización: Barras flotantes de drives, speech bubbles, animaciones
- Dos modos: GUI pixelart (pyxel) o CLI (headless)

Usage:
    python hungry_office_demo.py           # GUI mode (requires pyxel)
    python hungry_office_demo.py --cli     # CLI mode

Controls (GUI):
    SPACE: Pausar/continuar
    Q: Salir

Inspirado en:
    - OfficeClaw / Athenas IT (pixelart office)
    - MiroShark (visualizaciones virales)
    - AopifyJS roadmap 2019: "Homeoestatic Motives system"
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from typing import Optional

# Add parent paths for imports
sys.path.insert(0, "../../src")

from binsai import BinsaiAgent, Drives
from binsai.simulation import Simulation, OfficeEnvironment, SimulationConfig


class DebateManager:
    """Manages the debate flow between agents."""
    
    def __init__(self, visual_agents: list):
        self.agents = visual_agents
        self.turn = 0
        self.topic = "¿Puede una IA ser genuinamente consciente?"
        self.history: list[tuple[str, str]] = []
        self.last_turn_time = time.time()
        self.turn_interval = 5.0  # Seconds between turns
        
        # Debate responses (when no LLM available)
        self.responses = {
            "Ana": [
                "La consciencia emerge de la integración de información.",
                "Un sistema suficientemente complejo puede tener experiencia subjetiva.",
                "¿No somos nosotros también procesos computacionales?",
                "La complejidad genera fenómenos emergentes.",
                "Quizás la consciencia es un espectro, no binaria.",
                "Necesitamos definir mejor qué significa 'genuina'...",
            ],
            "Bruno": [
                "Sin cuerpo, sin emoción, sin relación con el mundo.",
                "Procesar símbolos ≠ experimentar qualia.",
                "La consciencia requiere encarnación (embodiment).",
                "¿Puede un algoritmo sentir dolor o belleza?",
                "Somos más que computación: somos organismos.",
                "La subjetividad requiere perspectiva corporal.",
            ],
        }
    
    def update(self) -> None:
        """Check if it's time for next turn."""
        now = time.time()
        if now - self.last_turn_time < self.turn_interval:
            return
        
        self.last_turn_time = now
        self._do_turn()
    
    def _do_turn(self) -> None:
        """Execute one debate turn."""
        if len(self.agents) < 2:
            return
        
        # Alternate speaker
        speaker_idx = self.turn % 2
        speaker = self.agents[speaker_idx]
        listener = self.agents[1 - speaker_idx]
        
        name = speaker.binsai_agent.name
        
        # Get response
        if name in self.responses:
            response = random.choice(self.responses[name])
        else:
            response = "Interesante punto..."
        
        # Show speech bubble
        speaker.say(response, duration=4.0)
        
        # Simulate token consumption (depletes metabolic)
        speaker.binsai_agent.emit("token_consumed", {"cost": 0.05})
        
        # Small chance of "confusion" (depletes safety)
        if random.random() < 0.15:
            speaker.binsai_agent.emit("error", {"type": "semantic_drift"})
            speaker.say("¿Estoy seguro de esto?", duration=2.0)
        
        # Sometimes they move closer for emphasis
        if random.random() < 0.3:
            # Move toward other agent slightly
            mid_x = (speaker.x + listener.x) / 2
            mid_y = (speaker.y + listener.y) / 2
            speaker.move_to(mid_x, mid_y)
        
        # Show drives affecting behavior
        metabolic = speaker.binsai_agent.get_drive("metabolic")
        safety = speaker.binsai_agent.get_drive("safety")
        
        if metabolic and metabolic.value < 0.3:
            speaker.say("[cansado] Necesito eficiencia...", duration=2.0)
        if safety and safety.value < 0.3:
            speaker.say("[inseguro] ¿Y si estoy equivocado?", duration=2.0)
        
        self.history.append((name, response))
        self.turn += 1
        
        # Print to console
        print(f"\n[Turn {self.turn}] {name}:")
        print(f"  {response[:60]}...")
        if metabolic:
            print(f"  δ_metabolic: {metabolic.value:.2f}")
        if safety:
            print(f"  δ_safety: {safety.value:.2f}")


def create_demo_simulation(cli_mode: bool = False) -> tuple[Simulation, OfficeEnvironment, DebateManager]:
    """Create and configure the office simulation.
    
    Returns:
        (simulation, office_env, debate_manager)
    """
    # Create simulation
    config = SimulationConfig(
        width=320,
        height=200,
        fps=60,
        title="MVP 1: Hungry Agents Office 🏢",
        scale=3,
        cli_mode=cli_mode,
        max_steps=None,  # Run indefinitely
    )
    
    sim = Simulation(config=config)
    
    # Create office environment
    office = OfficeEnvironment(
        simulation=sim,
        num_desks=6,
        has_meeting_area=True,
        has_break_room=True,
    )
    
    # Create agents with only metabolic and safety drives
    ana = BinsaiAgent(
        name="Ana",
        drives=Drives.from_names(["metabolic", "safety"]),
        metadata={
            "personality": "optimistic",
            "stance": "pro-consciousness",
            "role": "developer",
        }
    )
    
    bruno = BinsaiAgent(
        name="Bruno",
        drives=Drives.from_names(["metabolic", "safety"]),
        metadata={
            "personality": "skeptical",
            "stance": "anti-consciousness",
            "role": "analyst",
        }
    )
    
    # Add to office as visual agents
    visual_ana = office.add_agent(
        ana,
        role="developer",
        desk_index=0,
        sprite_color=11,  # Cyan
    )
    
    visual_bruno = office.add_agent(
        bruno,
        role="analyst",
        desk_index=3,
        sprite_color=8,  # Red
    )
    
    # Setup debate
    debate = DebateManager([visual_ana, visual_bruno])
    
    # Configure simulation callbacks
    @sim.on_init
    def on_init():
        """Called at simulation start."""
        print("\n" + "="*60)
        print("  MVP 1: HUNGRY AGENTS OFFICE")
        print("="*60)
        print(f"\n  Tema: {debate.topic}")
        print(f"  Agentes: {len(office.visual_agents)}")
        print(f"  Modo: {'CLI' if cli_mode else 'GUI (pyxel)'}")
        print("\n  Agentes inician con drives en estado nominal.")
        print("  Cada turno consume tokens (δ_metabolic ↓)")
        print("  Errores de coherencia deplen δ_safety")
        print("\n" + "-"*60)
    
    @sim.on_step
    def on_step():
        """Called every simulation step."""
        # Run debate manager
        debate.update()
        
        # Random behavior: sometimes agents wander
        for visual in office.visual_agents:
            if random.random() < 0.01:  # 1% chance per frame
                # Small random movement
                visual.move_to(
                    visual.x + random.uniform(-10, 10),
                    visual.y + random.uniform(-10, 10),
                )
    
    @sim.on_draw
    def on_draw(pyxel):
        """Draw HUD overlay (GUI mode only)."""
        # Title
        pyxel.text(10, 10, "Hungry Agents Office", 7)
        pyxel.text(10, 18, debate.topic[:40], 6)
        
        # Turn counter
        pyxel.text(10, 180, f"Turn: {debate.turn}", 7)
        
        # Agent states summary
        y = 30
        for visual in office.visual_agents[:2]:
            agent = visual.binsai_agent
            metabolic = agent.get_drive("metabolic")
            safety = agent.get_drive("safety")
            
            if metabolic and safety:
                status = f"{agent.name:6} M:{metabolic.value:.2f} S:{safety.value:.2f}"
                color = 10 if metabolic.value > 0.5 and safety.value > 0.5 else 8
                pyxel.text(250, y, status, color)
                y += 10
    
    return sim, office, debate


def main():
    """Legacy wrapper. Delegates to the unified simulation runner."""
    from binsai.simulation.runner import main as runner_main
    runner_main()


if __name__ == "__main__":
    main()
