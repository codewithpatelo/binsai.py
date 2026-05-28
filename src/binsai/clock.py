"""Discrete step clock for tick-based simulation.

The clock is the heartbeat of the world. Each tick() increments the counter;
all stochastic subsystems receive the same seed-derived RNG to keep runs
byte-for-byte reproducible across resets with the same seed.
"""

from __future__ import annotations

import random


class StepClock:
    """Monotonically increasing discrete tick counter.

    Usage:
        clock = StepClock(seed=42)
        t = clock.tick()   # returns new tick number
        clock.now()        # current tick without advancing
    """

    def __init__(self, seed: int = 0) -> None:
        self._t:   int           = 0
        self._rng: random.Random = random.Random(seed)
        self._seed = seed

    def tick(self) -> int:
        """Advance clock by one tick. Returns new tick number."""
        self._t += 1
        return self._t

    def now(self) -> int:
        """Current tick without advancing."""
        return self._t

    def rng(self) -> random.Random:
        """Shared RNG seeded from the clock seed. Same seed → same sequence."""
        return self._rng

    def reset(self) -> None:
        """Reset to t=0 with original seed — needed for ablation comparisons."""
        self._t   = 0
        self._rng = random.Random(self._seed)

    def __repr__(self) -> str:
        return f"StepClock(t={self._t}, seed={self._seed})"
