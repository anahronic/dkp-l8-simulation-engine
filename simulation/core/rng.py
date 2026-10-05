"""
Deterministic random number generator.

Every simulation component MUST draw randomness exclusively through this
module.  A single seed controls the entire run → full reproducibility.
"""

from __future__ import annotations

import hashlib
import math
import struct
from typing import List, Sequence, Tuple

from simulation.core.detmath import det_cos_2pi, det_log


class DeterministicRNG:
    """
    Seedable PRNG based on a 64-bit xoshiro256** core.

    Why not stdlib ``random``?  Because we need:
    * explicit fork/child streams (zone-level isolation)
    * no hidden global state
    * identical cross-platform output (no C-library transcendental functions)
    """

    def __init__(self, seed: int) -> None:
        self._state = self._seed_to_state(seed)

    # ── seeding ─────────────────────────────────────────────────────────
    @staticmethod
    def _seed_to_state(seed: int) -> List[int]:
        """Expand an arbitrary int into 4 × 64-bit state words."""
        h = hashlib.sha256(seed.to_bytes(32, "little", signed=True)).digest()
        return list(struct.unpack("<4Q", h[:32]))

    # ── core step (xoshiro256**) ────────────────────────────────────────
    @staticmethod
    def _rotl(x: int, k: int) -> int:
        return ((x << k) | (x >> (64 - k))) & 0xFFFFFFFFFFFFFFFF

    def _next_raw(self) -> int:
        s = self._state
        result = (self._rotl((s[1] * 5) & 0xFFFFFFFFFFFFFFFF, 7) * 9) & 0xFFFFFFFFFFFFFFFF
        t = (s[1] << 17) & 0xFFFFFFFFFFFFFFFF

        s[2] ^= s[0]
        s[3] ^= s[1]
        s[1] ^= s[2]
        s[0] ^= s[3]
        s[2] ^= t
        s[3] = self._rotl(s[3], 45)
        return result

    # ── public API ──────────────────────────────────────────────────────
    def uniform(self) -> float:
        """Return float in [0, 1)."""
        return (self._next_raw() >> 11) / (1 << 53)

    def uniform_range(self, lo: float, hi: float) -> float:
        """Return float in [lo, hi)."""
        return lo + (hi - lo) * self.uniform()

    def randint(self, lo: int, hi: int) -> int:
        """Return int in [lo, hi] inclusive."""
        span = hi - lo + 1
        return lo + int(self.uniform() * span) % span

    def gauss(self, mu: float = 0.0, sigma: float = 1.0) -> float:
        """Box-Muller transform with platform-independent log/cos (core.detmath).

        v1 used math.log / math.cos, whose last bits depend on the C library;
        sqrt is correctly rounded by IEEE-754 and is safe.
        """
        u1 = max(1e-300, self.uniform())  # avoid log(0)
        u2 = self.uniform()
        z = math.sqrt(-2.0 * det_log(u1)) * det_cos_2pi(u2)
        return mu + sigma * z

    def choice(self, seq: Sequence):
        """Pick one element uniformly."""
        return seq[self.randint(0, len(seq) - 1)]

    def shuffle(self, lst: list) -> None:
        """In-place Fisher-Yates shuffle."""
        for i in range(len(lst) - 1, 0, -1):
            j = self.randint(0, i)
            lst[i], lst[j] = lst[j], lst[i]

    def fork(self, label: str) -> "DeterministicRNG":
        """Create a child RNG keyed by *label* — for zone isolation."""
        h = hashlib.sha256(label.encode())
        for s in self._state:
            h.update(s.to_bytes(8, "little"))
        child_seed = int.from_bytes(h.digest()[:8], "little")
        return DeterministicRNG(child_seed)

    def state_snapshot(self) -> Tuple[int, ...]:
        return tuple(self._state)
