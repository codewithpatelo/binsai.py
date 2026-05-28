"""FIPA-like Agent Communication Language envelopes.

Heritage: Langpify message transport (2025) → Binsai (2026).
Every inter-entity message — human→agent, agent→agent, agent→human —
travels as an ACLMessage. Internal agent events (drive crossings, action
completions) are NOT ACL: they are agent-private and never appear on the wire.

Subset of FIPA-ACL we use in MVP1:
    REQUEST  — sender asks receiver to perform an action
    INFORM   — sender shares a fact (e.g. response to a REQUEST)
    REFUSE   — receiver declines a REQUEST it cannot/will not perform
    AGREE    — receiver acknowledges it will attempt the REQUEST
    FAILURE  — receiver attempted but failed

Reserved for MVP2+: QUERY_IF, PROPOSE, ACCEPT_PROPOSAL, NOT_UNDERSTOOD, CFP.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Performative(Enum):
    REQUEST = "request"
    INFORM  = "inform"
    REFUSE  = "refuse"
    AGREE   = "agree"
    FAILURE = "failure"


@dataclass
class ACLMessage:
    """FIPA-ACL message envelope.

    Required:
        performative — communicative act
        sender       — agent id of the originator
        receiver     — agent id of the intended recipient
        content      — payload (free-form dict; ontology defines schema)

    Optional:
        conversation_id — links related messages (REQUEST/INFORM pairs)
        in_reply_to     — message_id this is responding to
        language        — encoding of content (e.g. "json")
        ontology        — semantic domain (e.g. "binsai/inbox-v1")
        protocol        — interaction protocol (e.g. "fipa-request")
    """
    performative:    Performative
    sender:          str
    receiver:        str
    content:         dict[str, Any]
    conversation_id: str           = field(default_factory=lambda: str(uuid.uuid4()))
    message_id:      str           = field(default_factory=lambda: str(uuid.uuid4()))
    in_reply_to:     Optional[str] = None
    language:        str           = "json"
    ontology:        str           = "binsai/inbox-v1"
    protocol:        str           = "fipa-request"
    t_sent:          float         = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "performative":    self.performative.value,
            "sender":          self.sender,
            "receiver":        self.receiver,
            "content":         self.content,
            "conversation_id": self.conversation_id,
            "message_id":      self.message_id,
            "in_reply_to":     self.in_reply_to,
            "language":        self.language,
            "ontology":        self.ontology,
            "protocol":        self.protocol,
            "t_sent":          self.t_sent,
        }

    def reply(self, performative: Performative, content: dict[str, Any]) -> "ACLMessage":
        """Construct a reply that preserves conversation_id and threads via in_reply_to."""
        return ACLMessage(
            performative=performative,
            sender=self.receiver,
            receiver=self.sender,
            content=content,
            conversation_id=self.conversation_id,
            in_reply_to=self.message_id,
            ontology=self.ontology,
            protocol=self.protocol,
        )


@dataclass
class Mailbox:
    """Per-agent inbox with lifecycle-aware routing.

    The agent's sensors read from `inbox` only when ACTIVE. When SUSPENDED,
    incoming messages either go to `buffered` (default) or are dropped,
    depending on `policy_when_suspended`.
    """
    owner_aid: str
    inbox:     list[ACLMessage] = field(default_factory=list)
    buffered:  list[ACLMessage] = field(default_factory=list)   # arrived during SUSPENDED
    sent:      list[ACLMessage] = field(default_factory=list)
    policy_when_suspended: str = "buffer"   # "buffer" | "drop" | "refuse"

    def deliver(self, msg: ACLMessage, is_suspended: bool) -> Optional[ACLMessage]:
        """Route an incoming message according to lifecycle policy.

        Returns an ACLMessage if the policy generates an immediate reply
        (e.g. REFUSE when policy == "refuse"); otherwise None.
        """
        if msg.receiver != self.owner_aid:
            return None
        if is_suspended:
            if self.policy_when_suspended == "drop":
                return None
            if self.policy_when_suspended == "refuse":
                return msg.reply(
                    Performative.REFUSE,
                    {"reason": "agent suspended", "retry_after": "wake"},
                )
            # default: buffer
            self.buffered.append(msg)
            return None
        self.inbox.append(msg)
        return None

    def drain_inbox(self) -> list[ACLMessage]:
        """Consume all active messages (called each tick by the agent sensor)."""
        msgs = self.inbox
        self.inbox = []
        return msgs

    def flush_buffer_to_inbox(self) -> int:
        """Move buffered messages into the active inbox (called on wake).

        Returns the number of messages re-activated.
        """
        n = len(self.buffered)
        self.inbox.extend(self.buffered)
        self.buffered = []
        return n

    def record_sent(self, msg: ACLMessage) -> None:
        self.sent.append(msg)
        if len(self.sent) > 200:
            self.sent = self.sent[-200:]
