"""Platform-independent log/cos/pow (cross-platform determinism, item 6 of the 2026-10-04 check)."""

import math

import pytest

from simulation.core.detmath import det_cos_2pi, det_log, ipow
from simulation.core.rng import DeterministicRNG


@pytest.mark.parametrize("x", [1e-300, 1e-12, 0.001, 0.25, 0.5, 0.7071, 0.75, 0.999999, 1.0, 2.0, 1e6])
def test_log_close_to_libm(x):
    assert det_log(x) == pytest.approx(math.log(x), rel=1e-14, abs=1e-15)


def test_log_on_many_uniforms():
    rng = DeterministicRNG(1)
    for _ in range(20000):
        u = max(1e-300, rng.uniform())
        assert abs(det_log(u) - math.log(u)) <= 1e-14 * max(1.0, abs(math.log(u)))


def test_cos_close_to_libm():
    rng = DeterministicRNG(2)
    for u in [0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 0.999999] + [rng.uniform() for _ in range(20000)]:
        assert abs(det_cos_2pi(u) - math.cos(2 * math.pi * u)) <= 2e-15


def test_ipow_exact_for_small_cases():
    assert ipow(0.9, 0) == 1.0
    assert ipow(0.5, 10) == 0.5 ** 10          # powers of two are exact
    assert ipow(0.9, 7) == pytest.approx(0.9 ** 7, rel=1e-15)


def test_gauss_moments():
    rng = DeterministicRNG(3)
    xs = [rng.gauss() for _ in range(50000)]
    mean = math.fsum(xs) / len(xs)
    var = math.fsum((x - mean) ** 2 for x in xs) / len(xs)
    assert abs(mean) < 0.02 and abs(var - 1.0) < 0.03


def test_gauss_bits_pinned():
    """Same bits on every platform: CI runs this on Linux, Windows and macOS."""
    rng = DeterministicRNG(42)
    assert [rng.gauss().hex() for _ in range(3)] == GAUSS_42


GAUSS_42 = ['0x1.9068541e0deb5p-1', '0x1.8c0ffbb4a5257p-1', '-0x1.cad5fafd6f7b8p-1']  # pinned 2026-10-05 (Windows MSVC = Linux glibc)
