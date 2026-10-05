"""
Platform-independent elementary functions.

CPython's math.log and math.cos call the platform C library, whose last bits
differ between implementations.  The v2 bench observed this directly: the
same input_id gave a different result_id on Windows (MSVC CRT) and Linux
(glibc 2.35) because Box–Muller noise differed in the last bit.

The functions below use only +, −, ×, ÷ and math.frexp/ldexp (exact), in a
fixed order, so IEEE-754 binary64 arithmetic gives the same bits on every
platform.  Accuracy is about 1e-15 relative, ample for simulated sensor noise.
"""

from __future__ import annotations

import math

_SQRT_HALF = 0.7071067811865476
_LN2_HI = 6.93147180369123816490e-01    # fdlibm split of ln 2
_LN2_LO = 1.90821492927058770002e-10
_TWO_PI = 6.283185307179586

# 1 / (2k + 1) for the atanh series, k = 0..13
_ATANH = [1.0 / (2 * k + 1) for k in range(14)]
# Taylor coefficients (−1)^k / (2k)! and (−1)^k / (2k + 1)!, k = 0..10
_COS = [(1.0 if k % 2 == 0 else -1.0) / math.factorial(2 * k) for k in range(11)]
_SIN = [(1.0 if k % 2 == 0 else -1.0) / math.factorial(2 * k + 1) for k in range(11)]


def det_log(x: float) -> float:
    """Natural logarithm for x > 0."""
    if not x > 0.0:
        raise ValueError("det_log requires x > 0")
    m, e = math.frexp(x)               # x = m · 2^e, m in [0.5, 1)
    if m < _SQRT_HALF:
        m *= 2.0
        e -= 1                         # m in [√½, √2)
    f = (m - 1.0) / (m + 1.0)          # |f| ≤ 0.1716
    f2 = f * f
    s = 0.0
    for c in reversed(_ATANH):         # Horner: f · Σ f^(2k) / (2k+1)
        s = s * f2 + c
    return e * _LN2_HI + (e * _LN2_LO + 2.0 * f * s)


def _cos_poly(x: float) -> float:
    x2 = x * x
    s = 0.0
    for c in reversed(_COS):
        s = s * x2 + c
    return s


def _sin_poly(x: float) -> float:
    x2 = x * x
    s = 0.0
    for c in reversed(_SIN):
        s = s * x2 + c
    return x * s


def det_cos_2pi(u: float) -> float:
    """cos(2π·u) for u in [0, 1); reductions are exact (Sterbenz)."""
    if not 0.0 <= u < 1.0:
        raise ValueError("det_cos_2pi requires 0 <= u < 1")
    if u > 0.5:
        u = 1.0 - u                    # cos(2π(1−u)) = cos(2πu)
    sign = 1.0
    if u > 0.25:
        u = 0.5 - u                    # cos(2π(½−u)) = −cos(2πu)
        sign = -1.0
    if u <= 0.125:
        return sign * _cos_poly(_TWO_PI * u)
    return sign * _sin_poly(_TWO_PI * (0.25 - u))   # cos θ = sin(π/2 − θ)


def ipow(x: float, n: int) -> float:
    """x ** n for integer n ≥ 0 by repeated squaring (no C pow)."""
    if n < 0:
        raise ValueError("ipow requires n >= 0")
    result, base = 1.0, x
    while n:
        if n & 1:
            result *= base
        base *= base
        n >>= 1
    return result
