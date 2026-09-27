"""Event bus — canonical EPA events and FIPA-style subscriptions.

Canonical events (EPA spec §5.1):
    PULSE              — emitted by the agent every tick; drives the EPA update
    ZONE_CHANGED       — a drive or observed variable crossed an algedonic band
    PRESSURE_UPDATED   — emitted every pulse with the current driving_variable
    SENSOR_INVALID     — an observed variable's sensor is absent/stale/impossible
    VIABILITY_BREACHED — a drive crossed its viability limit (operational death)
    SATIATED           — an action reduced the drive's deviation (quality signal g)
    COUPLED            — this drive was moved by another drive's deviation via W
    TENSION_RELEASED   — the pulsatile spring discharged accumulated tension σ

Subscription model (FIPA ACL subscribe/cancel):
    sub_id = emitter.on("ZoneChanged", handler)
    emitter.unsubscribe(sub_id)
    sub_id = emitter.subscribe(source, "ZoneChanged", handler)  # subscribe to another emitter
    emitter.unsubscribe(sub_id)
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ── Canonical event names ─────────────────────────────────────────────────────

PULSE              = "Pulse"
ZONE_CHANGED       = "ZoneChanged"
PRESSURE_UPDATED   = "PressureUpdated"
SENSOR_INVALID     = "SensorInvalid"
VIABILITY_BREACHED = "ViabilityBreached"
SATIATED           = "Satiated"
COUPLED            = "Coupled"
TENSION_RELEASED   = "TensionReleased"


@dataclass
class Subscription:
    """Handle returned by on()/subscribe(). Cancel via emitter.unsubscribe(id)."""
    id:         int
    event_type: Optional[str]      # None = wildcard (on_any)
    handler:    Callable
    source:     Any = None         # emitter this subscription listens to


class EventEmitter:
    """Minimal event bus shared by Drive, ObservedVariable and BinsaiAgent.

    API:
        emitter.on(event_type, handler) -> subscription_id
        emitter.on_any(handler)         -> subscription_id   (receives envelopes)
        emitter.unsubscribe(sub_id)
        emitter.emit(event_type, payload)
        emitter.subscribe(source, event_type, handler) -> subscription_id
    """

    def _init_bus(self) -> None:
        self._bus_handlers:  dict[str, dict[int, Callable]] = {}
        self._bus_any:       dict[int, Callable]            = {}
        self._bus_subs:      dict[int, Subscription]        = {}
        self._bus_id_counter = itertools.count(1)

    # ── Local subscription ──────────────────────────────────────────────────

    def on(self, event_type: str, handler: Callable[[Any], None]) -> int:
        """Register a handler for an event type. Returns a subscription_id."""
        if not hasattr(self, "_bus_handlers"):
            self._init_bus()
        sub_id = next(self._bus_id_counter)
        self._bus_handlers.setdefault(event_type, {})[sub_id] = handler
        self._bus_subs[sub_id] = Subscription(sub_id, event_type, handler, source=self)
        return sub_id

    def on_any(self, handler: Callable[[Any], None]) -> int:
        """Register a wildcard handler — receives {type, source, payload} envelopes."""
        if not hasattr(self, "_bus_any"):
            self._init_bus()
        sub_id = next(self._bus_id_counter)
        self._bus_any[sub_id] = handler
        self._bus_subs[sub_id] = Subscription(sub_id, None, handler, source=self)
        return sub_id

    def off(self, event_type: str, handler: Optional[Callable] = None) -> None:
        """Remove handlers for an event type (all, or one specific handler)."""
        if not hasattr(self, "_bus_handlers"):
            return
        if handler is None:
            self._bus_handlers.pop(event_type, None)
        else:
            self._bus_handlers[event_type] = {
                sid: h for sid, h in self._bus_handlers.get(event_type, {}).items()
                if h != handler
            }

    def unsubscribe(self, subscription_id: int) -> bool:
        """Cancel a subscription by id (FIPA: cancel). Returns True if found."""
        if not hasattr(self, "_bus_subs"):
            return False
        sub = self._bus_subs.pop(subscription_id, None)
        if sub is None:
            return False
        target = sub.source if sub.source is not None else self
        if sub.event_type is None:
            target._bus_any.pop(subscription_id, None)
        else:
            handlers = target._bus_handlers.get(sub.event_type, {})
            handlers.pop(subscription_id, None)
        return True

    # ── Cross-emitter subscription (FIPA: subscribe) ─────────────────────────

    def subscribe(self, source: "EventEmitter", event_type: Optional[str],
                  handler: Callable[[Any], None]) -> int:
        """Subscribe to another emitter's events. Returns a local subscription_id.

        If event_type is None, subscribes to all of source's events (envelopes).
        """
        if not hasattr(self, "_bus_subs"):
            self._init_bus()
        if event_type is None:
            sub_id = source.on_any(handler)
        else:
            sub_id = source.on(event_type, handler)
        # Track locally so unsubscribe() routes to the source emitter
        self._bus_subs[sub_id] = Subscription(sub_id, event_type, handler, source=source)
        return sub_id

    # ── Emission ────────────────────────────────────────────────────────────

    def emit(self, event_type: str, payload: Any) -> None:
        """Emit an event to typed handlers, then to wildcard handlers as an envelope."""
        if not hasattr(self, "_bus_handlers"):
            self._init_bus()
        for handler in list(self._bus_handlers.get(event_type, {}).values()):
            try:
                handler(payload)
            except Exception as e:
                name = getattr(self, "name", repr(self))
                print(f"[{name}] handler error for {event_type}: {e}")

        envelope = {
            "type":       event_type,
            "source":     getattr(self, "aid", getattr(self, "name", None)),
            "agent_name": getattr(self, "name", None),
            "payload":    payload,
        }
        for handler in list(self._bus_any.values()):
            try:
                handler(envelope)
            except Exception as e:
                name = getattr(self, "name", repr(self))
                print(f"[{name}] global handler error for {event_type}: {e}")
