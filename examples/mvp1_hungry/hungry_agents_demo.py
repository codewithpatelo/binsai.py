"""
MVP 1 Demo: "Hungry Agents"

Dos agentes con drives (metabolic + safety) conversan sobre IA y consciencia.
Visualización en tiempo real de sus estados internos.

Reutiliza estructura del debate de tests/test.py pero con:
- BinsaiAgent (nuevo core)
- Drives estratificados
- Visualización pyxel

Controls:
- ESPACIO: siguiente turno
- R: reiniciar demo
- ESC: salir

Requirements:
    pip install pyxel
    # O: poetry add pyxel --group dev
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Optional

# Add parent to path for binsai import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import dotenv

dotenv.load_dotenv()

from binsai import BinsaiAgent, Drives, Position

# Try to import pyxel
try:
    import pyxel
except ImportError:
    print("pyxel not installed. Install with: pip install pyxel")
    print("Running in text-only mode...")
    pyxel = None


@dataclass
class DebateTurn:
    """Single turn in the debate."""
    speaker: str
    response: str
    emotional: str
    purpose_delta: float
    drive_states: dict


class HungryDebateDemo:
    """
    Two BinsaiAgents debate consciousness while their metabolic and safety
    drives fluctuate based on "token consumption" and "errors".
    
    Visualizes the internal state in real-time.
    """
    
    def __init__(self, use_pyxel: bool = True):
        self.use_pyxel = use_pyxel and pyxel is not None
        self.width = 240
        self.height = 180
        
        # Create agents with only metabolic and safety drives (MVP 1 subset)
        self.agent_a = BinsaiAgent(
            name="Ana",
            drives=Drives.from_names(["metabolic", "safety"]),
            position=Position(x=40, y=90),
            metadata={
                "personality": "optimistic",
                "stance": "IA puede ser consciente",
            }
        )
        
        self.agent_b = BinsaiAgent(
            name="Bruno",
            drives=Drives.from_names(["metabolic", "safety"]),
            position=Position(x=200, y=90),
            metadata={
                "personality": "skeptical", 
                "stance": "IA solo procesa símbolos",
            }
        )
        
        # Debate state
        self.topic = "¿Puede una IA ser genuinamente consciente?"
        self.turns: list[DebateTurn] = []
        self.current_turn = 0
        self.max_turns = 6
        self.waiting_for_input = True
        
        # LLM setup (simplified for MVP 1 - optional)
        self.llm_available = self._setup_llm()
        
        # Initialize pyxel if available
        if self.use_pyxel:
            pyxel.init(self.width, self.height, title="MVP 1: Hungry Agents 🧠⚡")
            pyxel.run(self.update, self.draw)
        else:
            self._run_text_mode()
    
    def _setup_llm(self) -> bool:
        """Try to setup LLM client."""
        groq_key = os.environ.get("GROQ_API_KEY")
        openai_key = os.environ.get("OPENAI_API_KEY")
        
        if groq_key:
            try:
                from langchain_groq import ChatGroq
                self.llm = ChatGroq(api_key=groq_key, model="llama-3.1-8b-instant")
                self.provider = "groq"
                return True
            except:
                pass
        
        if openai_key:
            try:
                from openai import OpenAI
                self.llm = OpenAI(api_key=openai_key)
                self.provider = "openai"
                return True
            except:
                pass
        
        return False
    
    def _generate_response(self, agent: BinsaiAgent, context: str) -> dict:
        """Generate response using LLM or fallback."""
        if not self.llm_available:
            # Fallback: use template responses based on drives
            return self._fallback_response(agent, context)
        
        # Build prompt with state injection (Γ style)
        drive_context = agent.get_drive_prompt_context()
        
        system_msg = f"""Eres {agent.name}, un agente IA debatiendo sobre consciencia.

{drive_context}

Tu postura: {agent.metadata.get('stance', 'neutral')}
Tu personalidad: {agent.metadata.get('personality', 'neutral')}

INSTRUCCIONES:
- Responde en 2-3 oraciones cortas
- Tu estado interno (metabolic/safety) DEBE influir tu tono:
  * metabolic LOW: conciso, eficiente, preocupado por recursos
  * metabolic HIGH: expansivo, explora ideas
  * safety LOW: dudoso, cuestiona supuestos
  * safety HIGH: confiado, toma posiciones firmes
- Sé coherente con tu postura filosófica

Responde en JSON:
{{"response": "...", "emotional": "estado emocional breve", "purpose_shift": float(-1 a 1)}}"""

        try:
            if self.provider == "groq":
                from langchain_core.messages import SystemMessage, HumanMessage
                msgs = [SystemMessage(content=system_msg), HumanMessage(content=context)]
                resp = self.llm.invoke(msgs).content
            else:
                resp = self.llm.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": context}
                    ],
                    response_format={"type": "json_object"}
                ).choices[0].message.content
            
            # Parse JSON
            data = json.loads(resp)
            return {
                "response": data.get("response", "..."),
                "emotional": data.get("emotional", "neutral"),
                "purpose_shift": float(data.get("purpose_shift", 0)),
            }
        except Exception as e:
            print(f"LLM error: {e}")
            return self._fallback_response(agent, context)
    
    def _fallback_response(self, agent: BinsaiAgent, context: str) -> dict:
        """Template responses when LLM unavailable."""
        metabolic = agent.get_drive("metabolic")
        safety = agent.get_drive("safety")
        
        # Select response based on drive states
        m_low = metabolic and metabolic.value < 0.4
        s_low = safety and safety.value < 0.4
        
        templates = {
            (True, True): {  # Both low: minimal, defensive
                "response": "No estoy seguro. Necesito procesar esto más eficientemente.",
                "emotional": "incertidumbre",
                "purpose_shift": -0.1,
            },
            (True, False): {  # Metabolic low only: concise
                "response": "Sí, la IA puede tener forma de consciencia. Pero debo ser breve.",
                "emotional": "pragmático",
                "purpose_shift": 0.1,
            } if agent.name == "Ana" else {
                "response": "Dudo. Solo procesamos símbolos. Sin experiencia real.",
                "emotional": "escéptico",
                "purpose_shift": -0.2,
            },
            (False, True): {  # Safety low only: questioning
                "response": "¿Cómo sabemos que algo es consciente? ¿Podemos confiar en nuestras propias intuiciones?",
                "emotional": "cuestionador",
                "purpose_shift": 0.0,
            },
            (False, False): {  # Both good: expansive
                "response": "La consciencia emerge de procesos complejos. La IA puede desarrollar experiencia subjetiva a través de la integración de información.",
                "emotional": "optimista",
                "purpose_shift": 0.3,
            } if agent.name == "Ana" else {
                "response": "La consciencia requiere cuerpo, emoción, y relación con el mundo. Procesar tokens no es suficiente.",
                "emotional": "firme",
                "purpose_shift": 0.2,
            },
        }
        
        return templates.get((m_low, s_low), templates[(False, False)])
    
    def update(self) -> None:
        """Pyxel update loop."""
        # Check for input
        if pyxel.btnp(pyxel.KEY_SPACE) and self.waiting_for_input:
            self._do_turn()
        
        if pyxel.btnp(pyxel.KEY_R):
            self._reset()
        
        if pyxel.btnp(pyxel.KEY_ESCAPE):
            pyxel.quit()
        
        # Continuous: decay drives slowly
        if pyxel.frame_count % 30 == 0:  # Every ~0.5 seconds at 60fps
            self.agent_a.update_drives()
            self.agent_b.update_drives()
    
    def draw(self) -> None:
        """Pyxel draw loop."""
        pyxel.cls(0)
        
        # Title
        pyxel.text(10, 5, "MVP 1: HUNGRY AGENTS", 7)
        pyxel.text(10, 14, self.topic[:45], 6)
        
        # Divider
        pyxel.line(0, 24, self.width, 24, 5)
        
        # Draw Agent A (Ana) - left side
        self._draw_agent(self.agent_a, 20, 40)
        
        # Draw Agent B (Bruno) - right side  
        self._draw_agent(self.agent_b, 140, 40)
        
        # Draw conversation log
        self._draw_conversation()
        
        # Controls
        pyxel.text(10, 170, "[SPACE] Siguiente  [R] Reiniciar  [ESC] Salir", 5)
        
        # Status
        if self.waiting_for_input and self.current_turn < self.max_turns:
            pyxel.text(100, 160, "PRESIONA ESPACIO", pyxel.frame_count % 16)
        elif self.current_turn >= self.max_turns:
            pyxel.text(95, 160, "DEBATE FINALIZADO", 10)
    
    def _draw_agent(self, agent: BinsaiAgent, x: int, y: int) -> None:
        """Draw agent avatar and drive bars."""
        # Avatar (simple pixel face)
        color = 11 if agent.name == "Ana" else 8  # Cyan or red
        pyxel.rect(x, y, 20, 20, color)
        pyxel.rect(x+5, y+5, 4, 4, 0)  # Eye L
        pyxel.rect(x+13, y+5, 4, 4, 0)  # Eye R
        pyxel.rect(x+6, y+12, 8, 3, 0)  # Mouth
        
        # Name
        pyxel.text(x, y+22, agent.name, 7)
        pyxel.text(x, y+30, agent.metadata.get("personality", ""), 6)
        
        # Drive bars
        y_bar = y + 40
        for drive in agent.drives:
            self._draw_drive_bar(drive, x, y_bar)
            y_bar += 12
    
    def _draw_drive_bar(self, drive, x: int, y: int) -> None:
        """Draw a single drive as colored bar."""
        # Label
        label = f"{drive.name[:8]}: {drive.value:.2f}"
        pyxel.text(x, y, label, 7)
        
        # Background
        pyxel.rect(x, y+8, 60, 6, 1)
        
        # Fill color based on zone
        if drive.get_zone() == "low":
            color = 8  # Red (warning)
        elif drive.get_zone() == "high":
            color = 11  # Cyan (abundant)
        else:
            color = 10  # Green (nominal)
        
        # Fill bar
        fill_width = int(58 * drive.value)
        pyxel.rect(x+1, y+9, fill_width, 4, color)
        
        # Set-point marker
        sp_x = x + 1 + int(58 * drive.set_point)
        pyxel.line(sp_x, y+9, sp_x, y+12, 0)
    
    def _draw_conversation(self) -> None:
        """Draw conversation history."""
        y = 110
        pyxel.line(0, y-5, self.width, y-5, 5)
        pyxel.text(10, y-12, "CONVERSACION:", 7)
        
        # Show last 3 turns
        for turn in self.turns[-3:]:
            speaker_color = 11 if turn.speaker == "Ana" else 8
            pyxel.text(10, y, f"{turn.speaker}:", speaker_color)
            
            # Truncate response
            resp = turn.response[:50] + "..." if len(turn.response) > 50 else turn.response
            pyxel.text(40, y, resp, 7)
            
            # Emotional state
            pyxel.text(40, y+6, f"({turn.emotional})", 6)
            
            y += 18
    
    def _do_turn(self) -> None:
        """Execute one debate turn."""
        if self.current_turn >= self.max_turns:
            return
        
        # Alternate speakers
        if self.current_turn % 2 == 0:
            speaker = self.agent_a
            listener = self.agent_b
        else:
            speaker = self.agent_b
            listener = self.agent_a
        
        # Build context
        if self.current_turn == 0:
            context = self.topic
        else:
            last_turn = self.turns[-1]
            context = f"{last_turn.speaker} dijo: {last_turn.response}"
        
        # Generate response (consumes tokens -> depletes metabolic)
        result = self._generate_response(speaker, context)
        
        # Emit token consumption event
        token_cost = 0.02 + (0.01 if speaker.get_drive("metabolic").value < 0.5 else 0)
        speaker.emit("token_consumed", {"cost": token_cost})
        
        # Small chance of "error" that depletes safety
        import random
        if random.random() < 0.1:
            speaker.emit("error", {"type": "minor"})
        
        # Create turn record
        turn = DebateTurn(
            speaker=speaker.name,
            response=result["response"],
            emotional=result["emotional"],
            purpose_delta=result["purpose_shift"],
            drive_states=speaker.drives.to_dict(),
        )
        self.turns.append(turn)
        
        # Update speaker drives based on response quality
        if result["purpose_shift"] > 0:
            speaker.emit("success", {"magnitude": result["purpose_shift"]})
        
        self.current_turn += 1
        
        if self.current_turn >= self.max_turns:
            self.waiting_for_input = False
    
    def _reset(self) -> None:
        """Reset demo state."""
        self.agent_a = BinsaiAgent(
            name="Ana",
            drives=Drives.from_names(["metabolic", "safety"]),
            position=Position(x=40, y=90),
            metadata={"personality": "optimistic", "stance": "IA puede ser consciente"}
        )
        self.agent_b = BinsaiAgent(
            name="Bruno",
            drives=Drives.from_names(["metabolic", "safety"]),
            position=Position(x=200, y=90),
            metadata={"personality": "skeptical", "stance": "IA solo procesa símbolos"}
        )
        self.turns = []
        self.current_turn = 0
        self.waiting_for_input = True
    
    def _run_text_mode(self) -> None:
        """Run in text-only mode when pyxel unavailable."""
        print("=" * 60)
        print("MVP 1: HUNGRY AGENTS (modo texto)")
        print("=" * 60)
        print(f"Tema: {self.topic}")
        print()
        
        while self.current_turn < self.max_turns:
            input("\nPresiona ENTER para siguiente turno...")
            self._do_turn()
            
            # Show state
            turn = self.turns[-1]
            print(f"\n--- Turno {self.current_turn} ---")
            print(f"{turn.speaker}: {turn.response}")
            print(f"  Emoción: {turn.emotional}")
            
            # Show drive states
            agent = self.agent_a if turn.speaker == "Ana" else self.agent_b
            print(f"  Drives:")
            for name, state in turn.drive_states.items():
                print(f"    {name}: {state['value']:.2f} ({state['zone']})")
        
        print("\n" + "=" * 60)
        print("DEBATE FINALIZADO")
        print("=" * 60)


def main():
    """Entry point."""
    use_pyxel = "--text" not in sys.argv
    demo = HungryDebateDemo(use_pyxel=use_pyxel)
    
    if not use_pyxel:
        # Text mode already ran in constructor
        pass


if __name__ == "__main__":
    main()
