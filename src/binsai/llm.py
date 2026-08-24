"""LLM backend abstraction — swappable provider with dry-run fallback.

Provides:
    LLMBackend — protocol (call method)
    DeepSeekBackend — real DeepSeek API via OpenAI-compatible client
    DryRunBackend — deterministic synthetic responses + realistic telemetry
    get_backend — factory that auto-falls-back to DryRunBackend if no API key
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass
class LLMTelemetry:
    """Provider-agnostic observables from an LLM call."""
    prompt_tokens:     int   = 0
    completion_tokens: int   = 0
    total_tokens:      int   = 0
    cost_usd:          float = 0.0
    latency_ms:        int   = 0
    context_chars:     int   = 0
    provider:          str   = ""
    model:             str   = ""
    tier:              str   = "main"


class LLMBackend(Protocol):
    """A callable LLM backend."""

    @property
    def name(self) -> str: ...

    def call(
        self,
        system: str,
        user: str,
        cfg: Optional["ModelConfig"] = None,
        max_tokens: int | None = None,
    ) -> tuple[str, LLMTelemetry]: ...


# ── Model routing types ───────────────────────────────────────────────────────

@dataclass
class ModelConfig:
    """What model to call and whether to enable thinking mode."""
    model:    str  = "deepseek-v4-flash"
    thinking: bool = False

    @property
    def tier_key(self) -> str:
        if self.thinking:
            return self.model + "-thinking"
        return self.model


# ── Pricing ───────────────────────────────────────────────────────────────────

PROVIDER_RATES: dict[str, dict[str, float]] = {
    "deepseek-v4-flash": {"input": 0.14e-6, "output": 0.28e-6},
    "deepseek-v4-pro":   {"input": 0.50e-6, "output": 2.00e-6},
}

MODEL_TIERS: dict[str, str] = {
    "deepseek-v4-flash":          "weak",
    "deepseek-v4-flash-thinking": "main",
    "deepseek-v4-pro":            "strong",
}

MAX_TOKENS_BY_TIER: dict[str, int] = {
    "weak":   256,
    "main":   1500,
    "strong": 2000,
}

DEFAULT_ROUTING: dict[str, ModelConfig] = {
    "weak":   ModelConfig(model="deepseek-v4-flash", thinking=False),
    "main":   ModelConfig(model="deepseek-v4-flash", thinking=True),
    "strong": ModelConfig(model="deepseek-v4-pro",   thinking=False),
}


# ── DeepSeek backend ──────────────────────────────────────────────────────────

class DeepSeekBackend:
    """Real DeepSeek API via OpenAI-compatible client."""

    name = "deepseek"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self._api_key:
            raise EnvironmentError(
                "DEEPSEEK_API_KEY not set. Export the variable or add it to .env."
            )
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise ImportError("openai package required: pip install openai") from exc
            self._client = OpenAI(
                api_key=self._api_key,
                base_url="https://api.deepseek.com",
            )
        return self._client

    def call(
        self,
        system: str,
        user: str,
        cfg: ModelConfig | None = None,
        max_tokens: int | None = None,
    ) -> tuple[str, LLMTelemetry]:
        if cfg is None:
            cfg = ModelConfig()
        if max_tokens is None:
            tier = MODEL_TIERS.get(cfg.tier_key, "main")
            max_tokens = MAX_TOKENS_BY_TIER.get(tier, 512)

        kwargs: dict = dict(
            model=cfg.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
        )
        if cfg.thinking:
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
        else:
            kwargs["temperature"] = 0
            kwargs["response_format"] = {"type": "json_object"}

        t0 = time.perf_counter()
        response = self._get_client().chat.completions.create(**kwargs)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        content = response.choices[0].message.content or ""
        usage = response.usage
        pt = usage.prompt_tokens if usage else 0
        ct = usage.completion_tokens if usage else 0
        tt = usage.total_tokens if usage else (pt + ct)

        rates = PROVIDER_RATES.get(cfg.model, {"input": 0.0, "output": 0.0})
        cost = pt * rates["input"] + ct * rates["output"]

        telemetry = LLMTelemetry(
            prompt_tokens=pt,
            completion_tokens=ct,
            total_tokens=tt,
            cost_usd=cost,
            latency_ms=latency_ms,
            context_chars=len(system) + len(user),
            provider="deepseek",
            model=cfg.tier_key,
            tier=MODEL_TIERS.get(cfg.tier_key, "main"),
        )
        return content, telemetry


# ── Dry-run backend (deterministic, no API key needed) ────────────────────────

_DRY_TASKS = [
    "Revisar conciliacion bancaria Q3",
    "Preparar cierre de IVA mensual",
    "Actualizar amortizacion de activos",
    "Consolidar cuentas por pagar",
    "Verificar diferencia de inventario",
    "Calcular provision de impuestos",
    "Ajustar flujo de caja semanal",
    "Revisar revaluo de moneda extranjera",
    "Preparar informe de deterioro de activos",
    "Conciliar cuentas por cobrar vencidas",
]

_DRY_RESPONSES = [
    "Revisado. La conciliacion del Q3 muestra una diferencia de $12,400 en la cuenta 4201. Sugiero verificar los asientos del 15/09.",
    "El cierre de IVA esta al 95%. Falta confirmar 3 facturas de proveedores del exterior. Plazo: viernes.",
    "Amortizaciones actualizadas hasta agosto. Detecte un activo dado de baja que seguia en planilla. Corregido.",
    "Cuentas por pagar consolidadas. Hay 2 facturas vencidas del proveedor Martinez que requieren autorizacion de pago urgente.",
    "La diferencia de inventario es por 47 unidades del SKU-8842. El almacen confirma que fue un error de conteo. Ajusto en sistema.",
    "Provision de impuestos calculada: $158,200 para el trimestre. Incluye ganancias, IVA saldo tecnico, e ingresos brutos.",
    "Flujo de caja proyectado: saldo positivo hasta noviembre. Recomiendo adelantar el pago de aguinaldos para aprovechar el descuento por pago anticipado.",
    "Revaluo de moneda: el dolar paso de $850 a $920, impacto de $34,500 en la posicion neta. Registro el ajuste contable.",
    "Informe de deterioro: 2 activos con valor recuperable menor al valor en libros. Total deterioro estimado: $89,000. Adjunto el analisis por UGE.",
    "Cuentas por cobrar: 8 clientes con mas de 60 dias de mora. Recomiendo iniciar gestion de cobranza para los 3 de mayor monto.",
]

_DRY_PROACTS = [
    "Alerta temprana: el consumo de tokens del equipo esta un 30% por debajo del presupuesto. Hay margen para acelerar tareas pendientes.",
    "Sugerencia: detecte un patron en las consultas de cierre mensual. Propongo automatizar la generacion del reporte preliminar los dias 28.",
    "Recordatorio: la auditoria externa empieza en 2 semanas. Recomiendo priorizar la documentacion de conciliaciones y ajustes del ultimo trimestre.",
    "Analisis predictivo: con la tasa de tareas actual, el backlog de cuentas por pagar se resolvera en 3 dias habiles. Sin cuellos de botella detectados.",
]

_DRY_THOUGHTS = [
    "La demanda requiere analisis de partidas contables con posible error de imputacion. Conviene revisar primero el mayor contable para identificar la cuenta origen del descuadre, luego cruzar con los comprobantes del periodo. La dificultad es moderada porque el volumen de transacciones es acotado.",
    "Tarea de consolidacion con multiples fuentes de datos. El riesgo principal es la inconsistencia entre sistemas (ERP vs planilla manual). Conviene empezar por los saldos de cierre del mes anterior como base, luego incorporar movimientos del periodo. Priorizar cuentas de mayor exposicion.",
    "Consulta simple de estado de cuenta. Respuesta directa con verificacion rapida en el sistema. Sin complejidades ocultas. Tiempo estimado: 5 minutos.",
]


class DryRunBackend:
    """Deterministic synthetic LLM — no API key, no network, reproducible."""

    name = "dry-run"

    def __init__(self, seed: int = 42) -> None:
        import random as _random
        self._rng = _random.Random(seed)
        self._call_count = 0

    def _hash(self, system: str, user: str) -> int:
        """Deterministic hash of input for reproducible variety."""
        h = hashlib.md5((system + user).encode()).hexdigest()
        return int(h[:8], 16)

    def call(
        self,
        system: str,
        user: str,
        cfg: ModelConfig | None = None,
        max_tokens: int | None = None,
    ) -> tuple[str, LLMTelemetry]:
        self._call_count += 1
        h = self._hash(system, user)
        local = self._rng

        # Determine what kind of response to generate from the user prompt
        is_appraisal = '"d"' in user and '"kind"' in system and '"why"' in system
        is_respond_fast = 'Demand topic:' in user and 'Respond briefly' in user
        is_respond_slow = 'Demand topic:' in user and 'Think step by step' in user
        is_proact = 'Write a brief INFORM' in user
        is_consolidation = 'memory consolidation module' in system

        # Pick model info for telemetry
        model = cfg.model if cfg else "deepseek-v4-flash"
        thinking = cfg.thinking if cfg else False
        tier_key = model + ("-thinking" if thinking else "")
        tier = MODEL_TIERS.get(tier_key, "main")

        # Token counts — realistic ranges per tier
        if is_appraisal:
            pt, ct = 80 + h % 40, 15 + h % 15
        elif is_respond_fast:
            pt, ct = 120 + h % 60, 40 + h % 40
        elif is_respond_slow:
            pt, ct = 250 + h % 100, 100 + h % 150
        elif is_proact:
            pt, ct = 150 + h % 80, 60 + h % 80
        elif is_consolidation:
            pt, ct = 100 + h % 40, 30 + h % 30
        else:
            pt, ct = 150 + h % 100, 50 + h % 100

        # Build synthetic response
        if is_appraisal:
            d_val = 0.2 + (h % 60) / 100.0  # 0.20–0.79
            kinds = ["trivial", "trivial", "moderate", "moderate", "moderate", "hard"]
            kind = kinds[h % len(kinds)]
            response = json.dumps({"d": round(d_val, 2), "kind": kind, "why": _DRY_RESPONSES[h % len(_DRY_RESPONSES)][:60]})
        elif is_respond_fast:
            response = json.dumps({
                "response": _DRY_RESPONSES[h % len(_DRY_RESPONSES)],
                "confidence": round(0.6 + (h % 40) / 100.0, 2),
                "tasks_to_do": [_DRY_TASKS[h % len(_DRY_TASKS)], _DRY_TASKS[(h + 1) % len(_DRY_TASKS)]],
            })
        elif is_respond_slow:
            response = json.dumps({
                "thought": _DRY_THOUGHTS[h % len(_DRY_THOUGHTS)],
                "response": _DRY_RESPONSES[h % len(_DRY_RESPONSES)],
                "confidence": round(0.7 + (h % 30) / 100.0, 2),
                "tasks_to_do": [_DRY_TASKS[h % len(_DRY_TASKS)], _DRY_TASKS[(h + 1) % len(_DRY_TASKS)], _DRY_TASKS[(h + 2) % len(_DRY_TASKS)]],
            })
        elif is_proact:
            response = json.dumps({
                "inform": _DRY_PROACTS[h % len(_DRY_PROACTS)],
                "priority": ["low", "medium", "high"][h % 3],
                "tasks_to_do": [_DRY_TASKS[(h + 3) % len(_DRY_TASKS)]],
            })
        elif is_consolidation:
            response = json.dumps({
                "summary": f"Consolidated {1 + h % 5} recent actions and {h % 4} pending topics into compact summary.",
                "key_topics": [_DRY_TASKS[h % len(_DRY_TASKS)][:30]],
            })
        else:
            response = json.dumps({"response": _DRY_RESPONSES[h % len(_DRY_RESPONSES)], "tasks_to_do": []})

        # Cost
        rates = PROVIDER_RATES.get(model, {"input": 0.0, "output": 0.0})
        cost = pt * rates["input"] + ct * rates["output"]

        # Synthetic latency (realistic: 50–200 ms)
        latency = 50 + h % 150

        telemetry = LLMTelemetry(
            prompt_tokens=pt,
            completion_tokens=ct,
            total_tokens=pt + ct,
            cost_usd=round(cost, 8),
            latency_ms=latency,
            context_chars=len(system) + len(user),
            provider="dry-run",
            model=tier_key,
            tier=tier,
        )
        return response, telemetry


# ── Factory ───────────────────────────────────────────────────────────────────

def get_backend(dry_run: bool = False, seed: int = 42) -> LLMBackend:
    """Create the appropriate LLM backend.

    Priority:
        1. If dry_run=True, always use DryRunBackend.
        2. If DEEPSEEK_API_KEY is set, use DeepSeekBackend.
        3. Otherwise, fall back to DryRunBackend with a warning.
    """
    if dry_run:
        return DryRunBackend(seed=seed)

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if api_key:
        return DeepSeekBackend(api_key=api_key)

    import warnings
    warnings.warn(
        "DEEPSEEK_API_KEY not set — falling back to DryRunBackend. "
        "LLM calls will use synthetic responses with realistic telemetry. "
        "Set DEEPSEEK_API_KEY or pass dry_run=False explicitly to use the real API."
    )
    return DryRunBackend(seed=seed)
