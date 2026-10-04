"""Seed derivation helpers.

``random.Random`` (Mersenne Twister) is deterministic for a given seed, so the
engine and agents always create their own seeded instances instead of using
the global ``random`` module. ``derive_seed`` mixes a base seed with a salt so
independent streams (map layout, core spawns, each agent) never correlate.
"""

from __future__ import annotations

import random

_MASK = 0xFFFFFFFF


def derive_seed(seed: int, salt: int) -> int:
    """Return a well-mixed 32-bit seed (murmur3 finaliser)."""
    h = (seed ^ ((salt + 0x9E3779B9) * 0x85EBCA6B)) & _MASK
    h ^= h >> 16
    h = (h * 0x7FEB352D) & _MASK
    h ^= h >> 15
    h = (h * 0x846CA68B) & _MASK
    h ^= h >> 16
    return h


def make_rng(seed: int, salt: int = 0) -> random.Random:
    return random.Random(derive_seed(seed, salt))
