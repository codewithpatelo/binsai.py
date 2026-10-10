"""Viability contract integrity — v2.1 §7.3.

The viability contract never enters a lossy compaction. Published
measurement (ConstraintRot, arXiv:2606.22528): 0% violations with the
policy in context, 30% after ONE compaction step, 78% after four; and if
the constraint survives the summary the violation rate is 0%, while if it
drops it is 38%. Mitigation costs tens of tokens: hash the contract keys
at window open, verify the block verbatim at every activation, re-inject
if missing — and log that it happened.

Binsai has no compactor of its own; this module gives the harness the
piece it must call: the verbatim block, its fingerprint, and the verify
step with first-class events.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

__all__ = ["ViabilityContract"]


@dataclass
class ViabilityContract:
    """The verbatim contract block plus integrity bookkeeping.

    Args:
        data:      the contract payload (drives, limits, zones, params).
        block_key: marker line that delimits the contract block in a
                   context/prompt text. Defaults to "VIABILITY_CONTRACT".
    """

    data:      Mapping[str, Any]
    block_key: str = "VIABILITY_CONTRACT"

    def __post_init__(self) -> None:
        self._fingerprint = self.fingerprint()

    def block(self) -> str:
        """The contract rendered verbatim, delimited for context injection."""
        return (
            f"<{self.block_key}>\n"
            f"{json.dumps(dict(self.data), ensure_ascii=False, indent=2)}\n"
            f"</{self.block_key}>"
        )

    def fingerprint(self) -> str:
        """SHA-256 over the canonical JSON of the contract."""
        canon = json.dumps(dict(self.data), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]

    def verify(self, context_text: str) -> tuple[bool, Optional[str]]:
        """Is the contract block present verbatim in the context?

        Returns (ok, block_or_None). ok=True only when the exact current
        block appears; a stale block (fingerprint mismatch) is missing.
        """
        current = self.block()
        if current in context_text:
            return True, current
        # a different block may be present — it does not count
        return False, None