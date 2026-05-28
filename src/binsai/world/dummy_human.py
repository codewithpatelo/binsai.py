"""DummyHuman — stochastic demand generator for MVP1 demo.

Emits Poisson-distributed FIPA REQUEST envelopes each tick, targeting agents
uniformly at random. The human does NOT assess demand difficulty — that is the
agent's appraisal act. The payload carries only what a real sender would know:
who is being asked, what topic is at hand, and a natural-language message body.

Invariant (tested): over many ticks, target distribution is uniform.
"""

from __future__ import annotations

import math
import random
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..acl import ACLMessage, Performative

if TYPE_CHECKING:
    from ..agent import BinsaiAgent

HUMAN_AID = "dummy_human"

# Accounting-firm demand topics — concrete, realistic, stress-inducing
_TOPICS = [
    "conciliacion_bancaria",
    "amortizacion_activos",
    "cierre_iva",
    "varianza_nomina",
    "asignacion_costos",
    "cuentas_por_pagar",
    "cuentas_por_cobrar",
    "provision_impuestos",
    "transferencia_intercompany",
    "devengado_intereses",
    "diferencia_inventario",
    "revaluo_moneda",
    "flujo_de_caja",
    "deterioro_activos",
    "ajuste_presupuesto",
]

# Messages mix Spanish/English — feel of a bilingual accounting firm under pressure
_PHRASES = [
    "{name}, ¿podés revisar la {topic} del Q3 antes del viernes?",
    "Urgente — {name}, la {topic} tiene una diferencia que no cierra.",
    "{name}: el auditor pidió la {topic} para mañana 9am.",
    "Hey {name}, necesito la {topic} actualizada para el board.",
    "{name}, ¿cerraste la {topic}? El contador está esperando.",
    "Atención {name}: hay un error en la {topic}, revisá antes del cierre.",
    "{name}, consolidá la {topic} con los datos de esta semana.",
    "El cliente pregunta por la {topic} — {name}, ¿cuándo tenemos algo?",
    "{name}: la {topic} no cuadra con el mayor, necesito que lo veas hoy.",
    "ASAP {name} — el socio necesita la {topic} para la reunión de las 3.",
]


@dataclass
class Demand:
    """Thin wrapper kept for backward-compatibility and world.py routing.

    The canonical message is `envelope` (an ACLMessage). The flat fields
    mirror its content for easy access by world.py and the WebSocket frame.
    No `difficulty` field — that is the agent's appraisal, not ours.
    """
    id:          str
    target_aid:  str
    target_name: str
    topic:       str
    message:     str          # natural-language body (shown in human speech bubble)
    t_emitted:   int
    t_received:  int | None = None
    envelope:    ACLMessage | None = None   # the canonical FIPA envelope

    def mark_received(self, t: int) -> None:
        self.t_received = t


class DummyHuman:
    """Generates ACL REQUEST messages at Poisson rate, uniform target selection.

    Args:
        targets:       BinsaiAgent instances that can receive demands.
        lambda_demand: Expected demands per tick (Poisson mean).
        rng:           Seeded random.Random for reproducibility.
    """

    def __init__(
        self,
        targets:       list["BinsaiAgent"],
        lambda_demand: float              = 0.5,
        rng:           random.Random | None = None,
    ) -> None:
        if not targets:
            raise ValueError("DummyHuman requires at least one target agent.")
        self.targets       = targets
        self.lambda_demand = lambda_demand
        self._rng          = rng or random.Random()
        self._total_sent   = 0

    def _poisson_sample(self) -> int:
        """Knuth's algorithm — exact for small λ."""
        L = math.exp(-self.lambda_demand)
        k, p = 0, 1.0
        while p > L:
            k += 1
            p *= self._rng.random()
        return k - 1

    def tick(self, t: int) -> list[Demand]:
        """Generate demands for this tick (may be empty list)."""
        n = self._poisson_sample()
        demands: list[Demand] = []

        for _ in range(n):
            target  = self._rng.choice(self.targets)
            topic   = self._rng.choice(_TOPICS)
            phrase  = self._rng.choice(_PHRASES)
            message = phrase.format(name=target.name, topic=topic)

            envelope = ACLMessage(
                performative=Performative.REQUEST,
                sender=HUMAN_AID,
                receiver=target.aid,
                content={
                    "topic":   topic,
                    "message": message,
                },
                ontology="binsai/inbox-v1",
                protocol="fipa-request",
            )

            demand = Demand(
                id=envelope.message_id[:8],
                target_aid=target.aid,
                target_name=target.name,
                topic=topic,
                message=message,
                t_emitted=t,
                envelope=envelope,
            )
            demands.append(demand)
            self._total_sent += 1

        return demands

    @property
    def total_sent(self) -> int:
        return self._total_sent
