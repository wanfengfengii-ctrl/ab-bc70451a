"""Meridian grid restoration solver.

A water-damaged nautical chart leaves ``n`` (5..10) surviving meridian traces
at integer x-positions, recorded left to right.  The goal is to restore one
common meridian grid: strictly increasing integer serial offsets
``k_1 < ... < k_n`` (``k_1 = 0`` without loss of generality, the start position
absorbs any global shift), a positive common spacing ``d > 0`` and a start
position ``s`` such that every trace deviation ``|s + k_i * d - x_i|`` stays
within the allowed tolerance.

Among all feasible restorations the solver optimises, in lexicographic order:

1. the maximum deviation ``max_i |s + k_i d - x_i|`` (minimised);
2. the sum of squared deviations (minimised);
3. the sequence of per-gap missing-meridian counts ``k_{i+1} - k_i - 1``
   (lexicographically minimised).

The search is a *global* arbitration over all index assignments consistent
with the per-gap missing-count upper bounds — never a per-segment nearest
rounding.  All arithmetic uses :class:`fractions.Fraction`, so the
lexicographic tie-breaking is exact and never corrupted by floating-point
rounding.
"""

from __future__ import annotations

import math
from fractions import Fraction
from itertools import combinations

__all__ = [
    "SearchLimitExceeded",
    "restore",
    "min_cheb",
    "select_best",
    "cheb_value",
    "constrained_least_squares",
]

# Safety budget for the exact branch-and-bound searches.  With the interval
# propagation below, realistic inputs explore only a tiny fraction of this.
_NODE_LIMIT = 1_000_000


class SearchLimitExceeded(RuntimeError):
    """Raised when an exact search exceeds its safety node budget."""


# ---------------------------------------------------------------------------
# Exact line-fitting primitives
# ---------------------------------------------------------------------------


def _triple_error(k1, k2, k3, x1, x2, x3):
    """Chebyshev (min-max) error of the best line through three points.

    The optimal line equioscillates with errors ``+e, -e, +e`` (or the negated
    pattern); solving the three equations yields ``e`` exactly.
    """
    num = (x2 - x1) * (k3 - k2) - (x3 - x2) * (k2 - k1)
    return abs(Fraction(num, 2 * (k3 - k1)))


def cheb_value(ks, xs):
    """Exact minimum over ``(s, d)`` of ``max_i |s + ks[i] * d - xs[i]|``.

    Lines form a 2-dimensional Haar family, so by the alternation theorem the
    optimum equals the maximum equioscillation error over all point triples.
    """
    best = Fraction(0)
    for a, b, c in combinations(range(len(ks)), 3):
        e = _triple_error(ks[a], ks[b], ks[c], xs[a], xs[b], xs[c])
        if e > best:
            best = e
    return best


def constrained_least_squares(ks, xs, t):
    """Minimise ``sum (s + k_i d - x_i)^2`` subject to every ``|r_i| <= t``.

    Returns ``(q, s, d)`` as exact fractions.  The feasible set is a convex
    polygon in ``(s, d)`` and the objective is convex quadratic, so the
    optimum is either the unconstrained least-squares point, the minimiser
    along exactly one active residual bound, or a vertex where two residual
    bounds are active — all enumerated exactly below.
    """
    n = len(ks)
    kf = [Fraction(k) for k in ks]
    xf = [Fraction(x) for x in xs]
    t = Fraction(t)
    best = None

    def consider(s, d):
        nonlocal best
        if d <= 0:  # the common spacing must be positive
            return
        residuals = [s + k * d - x for k, x in zip(kf, xf)]
        if all(-t <= r <= t for r in residuals):
            q = sum((r * r for r in residuals), Fraction(0))
            if best is None or q < best[0]:
                best = (q, s, d)

    # Unconstrained least squares (normal equations, 2x2 exact solve).
    s0 = Fraction(n)
    s1 = sum(kf)
    s2 = sum((k * k for k in kf), Fraction(0))
    t0 = sum(xf)
    t1 = sum((k * x for k, x in zip(kf, xf)), Fraction(0))
    det = s0 * s2 - s1 * s1
    consider((t0 * s2 - s1 * t1) / det, (s0 * t1 - s1 * t0) / det)

    # Exactly one active residual bound: r_i = sigma * t.
    for i in range(n):
        for sigma in (Fraction(1), Fraction(-1)):
            # s = x_i + sigma*t - k_i*d  ->  one-variable quadratic in d.
            a = [kf[j] - kf[i] for j in range(n)]
            b = [xf[i] + sigma * t - xf[j] for j in range(n)]
            den = sum((v * v for v in a), Fraction(0))
            if den == 0:
                continue
            d = -sum((a[j] * b[j] for j in range(n)), Fraction(0)) / den
            consider(xf[i] + sigma * t - kf[i] * d, d)

    # Two active residual bounds (a vertex of the feasible polygon).
    for i, j in combinations(range(n), 2):
        for si in (Fraction(1), Fraction(-1)):
            for sj in (Fraction(1), Fraction(-1)):
                d = (xf[j] + sj * t - xf[i] - si * t) / (kf[j] - kf[i])
                consider(xf[i] + si * t - kf[i] * d, d)

    if best is None:
        raise SearchLimitExceeded("no positive-spacing least-squares solution")
    return best


# ---------------------------------------------------------------------------
# Interval propagation over future serial offsets
# ---------------------------------------------------------------------------


def _suffix_max_gaps(max_missing):
    """``S[i] = sum_{t>=i} (max_missing[t] + 1)`` — max index span from gap i on."""
    n = len(max_missing)
    suffix = [0] * (n + 1)
    for i in range(n - 1, -1, -1):
        suffix[i] = suffix[i + 1] + max_missing[i] + 1
    return suffix


def _triple_bounds(ks_fixed, xs, pos, bound):
    """Interval for ``k_pos`` implied by triples of fixed points and ``bound``.

    For fixed ``a < b`` and a future position ``pos``, requiring the triple
    error to stay within ``bound`` is a pair of linear inequalities in
    ``k_pos``.  Returns ``(lo, hi)`` as exact fractions (either may be
    ``None`` when unbounded), or ``None`` when the intersection is empty.
    """
    lo = None
    hi = None
    x_l = xs[pos]
    for a, b in combinations(range(len(ks_fixed)), 2):
        ka, kb = ks_fixed[a], ks_fixed[b]
        xa, xb = xs[a], xs[b]
        big_a = xb - xa  # > 0 because x is strictly increasing
        # triple numerator N(k) = big_a * k - c  with  |N| <= 2*bound*(k - ka)
        c = big_a * kb + (x_l - xb) * (kb - ka)
        # k * (big_a + 2B) >= c + 2B*ka
        v = Fraction(c + 2 * bound * ka, big_a + 2 * bound)
        lo = v if lo is None or v > lo else lo
        # k * (big_a - 2B) <= c - 2B*ka
        den = big_a - 2 * bound
        num = c - 2 * bound * ka
        if den > 0:
            v = Fraction(num, den)
            hi = v if hi is None or v < hi else hi
        elif den == 0:
            if num < 0:
                return None
        else:
            v = Fraction(num, den)
            lo = v if lo is None or v > lo else lo
    if lo is not None and hi is not None and lo > hi:
        return None
    return lo, hi


def _ceil_frac(v):
    return -((-v.numerator) // v.denominator)


def _floor_frac(v):
    return v.numerator // v.denominator


# ---------------------------------------------------------------------------
# Branch-and-bound searches over gap compositions
# ---------------------------------------------------------------------------


def _heuristic_value(xs, max_missing):
    """Cheap incumbent: round ideal serial offsets for many total spans."""
    n = len(xs)
    span = xs[-1] - xs[0]
    best = None
    k_lo_total = n - 1
    k_hi_total = sum(m + 1 for m in max_missing)
    for total in range(k_lo_total, k_hi_total + 1):
        raw = [0] * n
        for i in range(1, n):
            ideal = Fraction((xs[i] - xs[0]) * total, span)
            raw[i] = math.floor(ideal + Fraction(1, 2))
        raw[n - 1] = total
        candidates = [raw]
        # Forward-clamped repair is always a feasible composition.
        repaired = [0] * n
        for i in range(1, n):
            lo = repaired[i - 1] + 1
            hi = repaired[i - 1] + max_missing[i - 1] + 1
            repaired[i] = min(max(raw[i], lo), hi)
        candidates.append(repaired)
        for ks in candidates:
            if all(
                1 <= ks[i + 1] - ks[i] <= max_missing[i] + 1 for i in range(n - 1)
            ):
                value = cheb_value(ks, xs)
                if best is None or value < best:
                    best = value
                    if best == 0:
                        return best
    return best


def _search(xs, max_missing, bound, on_leaf, improve_only, node_limit=_NODE_LIMIT):
    """Depth-first enumeration of serial offsets in increasing (lex) order.

    ``bound`` is an exact fraction.  With ``improve_only=True`` (phase 1) only
    leaves strictly better than ``bound`` are reported and ``bound`` is
    tightened to the best leaf found; otherwise (phase 2 / enumeration) every
    leaf whose Chebyshev value is at most ``bound`` is reported.

    Returns the number of leaves reported.
    """
    n = len(xs)
    suffix = _suffix_max_gaps(max_missing)
    state = {"nodes": 0, "leaves": 0, "bound": bound}

    def recurse(ks, lower):
        current = state["bound"]
        if current is not None:
            # Phase 1 keeps only strict improvements; phase 2 keeps every
            # composition within the optimal bound.
            if (improve_only and lower >= current) or (
                not improve_only and lower > current
            ):
                return
        state["nodes"] += 1
        if state["nodes"] > node_limit:
            raise SearchLimitExceeded("exact search exceeded its node budget")
        pos = len(ks)
        if pos == n:
            state["leaves"] += 1
            on_leaf(ks, lower)
            if improve_only:
                state["bound"] = lower
            return
        last = ks[-1]
        j = pos - 1  # index of the last fixed position
        lo_k = last + 1
        hi_k = last + max_missing[j] + 1
        limit = state["bound"]
        if limit is not None and len(ks) >= 2:
            # Interval propagation: shrink every future position's range.
            for fut in range(pos, n):
                glo = last + (fut - j)
                ghi = last + suffix[j] - suffix[fut]
                interval = _triple_bounds(ks, xs, fut, limit)
                if interval is None:
                    return
                ilo, ihi = interval
                if ilo is not None:
                    glo = max(glo, _ceil_frac(ilo))
                if ihi is not None:
                    ghi = min(ghi, _floor_frac(ihi))
                if glo > ghi:
                    return
                if fut == pos:
                    lo_k, hi_k = glo, ghi
        for k in range(lo_k, hi_k + 1):
            new_lower = lower
            for a, b in combinations(range(len(ks)), 2):
                e = _triple_error(ks[a], ks[b], k, xs[a], xs[b], xs[pos])
                if e > new_lower:
                    new_lower = e
            recurse(ks + [k], new_lower)
            if improve_only and state["bound"] == 0:
                return

    recurse([0], Fraction(0))
    return state["leaves"]


def min_cheb(xs, max_missing):
    """Exact minimum of the Chebyshev deviation over all legal compositions."""
    incumbent = _heuristic_value(xs, max_missing)
    if incumbent == 0:
        return Fraction(0)
    holder = {"best": incumbent}

    def on_leaf(_ks, lower):
        holder["best"] = lower

    _search(xs, max_missing, incumbent, on_leaf, improve_only=True)
    best = holder["best"]
    if best is None:  # pragma: no cover - heuristic always finds a composition
        raise SearchLimitExceeded("no legal serial assignment exists")
    return best


def select_best(xs, max_missing, t):
    """Among compositions with Chebyshev value ``t``, minimise squared error.

    Returns ``(q, ks, s, d)``.  Leaves are enumerated in lexicographic order
    of the serial offsets (hence of the missing-count sequence) and the best
    is only replaced on a strict improvement of ``q``, so ties resolve to the
    lexicographically smallest missing-count sequence.
    """
    best = {"value": None}

    def on_leaf(ks, _lower):
        q, s, d = constrained_least_squares(ks, xs, t)
        if best["value"] is None or q < best["value"][0]:
            best["value"] = (q, list(ks), s, d)

    leaves = _search(xs, max_missing, t, on_leaf, improve_only=False)
    if leaves == 0 or best["value"] is None:  # pragma: no cover - t is feasible
        raise SearchLimitExceeded("no composition achieves the optimal deviation")
    return best["value"]


def enumerate_feasible(xs, max_missing, tol):
    """All serial-offset compositions whose Chebyshev value fits ``tol``."""
    found = []

    def on_leaf(ks, _lower):
        found.append(list(ks))

    _search(xs, max_missing, tol, on_leaf, improve_only=False)
    return found


# ---------------------------------------------------------------------------
# Top-level restoration
# ---------------------------------------------------------------------------


def _diagnose(xs, max_missing, tol):
    """Locate the first trace whose error constraint cannot be satisfied.

    Prefixes are checked left to right; the first infeasible prefix pinpoints
    the offending trace.  The report includes the serial range already
    determined for the previous trace (over all feasible prefix restorations)
    and the candidate serial interval the failing trace could still occupy.
    """
    for j in range(3, len(xs) + 1):
        t_j = min_cheb(xs[:j], max_missing[: j - 1])
        if t_j > tol:
            feasible = enumerate_feasible(xs[: j - 1], max_missing[: j - 2], tol)
            lasts = [ks[-1] for ks in feasible]
            prev_lo, prev_hi = min(lasts), max(lasts)
            gap = max_missing[j - 2]
            return {
                "trace": j,
                "x": xs[j - 1],
                "requiredTolerance": t_j,
                "previousSerialRange": (prev_lo + 1, prev_hi + 1),
                "candidateSerialRange": (prev_lo + 2, prev_hi + gap + 2),
            }
    raise SearchLimitExceeded("infeasible instance without infeasible prefix")


def restore(xs, max_missing, tolerance):
    """Restore one common meridian grid from the surviving traces.

    ``xs`` — strictly increasing integer x-positions (5..10);
    ``max_missing`` — per-gap upper bounds on missing meridians (len n-1);
    ``tolerance`` — allowed positioning error (exact ``Fraction``).

    Returns a JSON-ready dict with either the optimal restoration
    (``feasible: True``) or a diagnosis of the first unsatisfiable trace
    (``feasible: False``).
    """
    xs = [int(v) for v in xs]
    max_missing = [int(v) for v in max_missing]
    tol = Fraction(tolerance)
    n = len(xs)

    t = min_cheb(xs, max_missing)
    if t > tol:
        failure = _diagnose(xs, max_missing, tol)
        return {
            "feasible": False,
            "failure": {
                "trace": failure["trace"],
                "x": failure["x"],
                "requiredTolerance": float(failure["requiredTolerance"]),
                "previousSerialRange": list(failure["previousSerialRange"]),
                "candidateSerialRange": list(failure["candidateSerialRange"]),
                "message": (
                    f"第 {failure['trace']} 条残迹（x={failure['x']}）无法满足误差约束："
                    f"相邻已确定的经线序号区间为 "
                    f"[{failure['previousSerialRange'][0]}, {failure['previousSerialRange'][1]}]，"
                    f"该残迹可用的候选序号区间为 "
                    f"[{failure['candidateSerialRange'][0]}, {failure['candidateSerialRange'][1]}]，"
                    f"但所需最小定位误差为 {float(failure['requiredTolerance']):.6g}，"
                    f"超过允许限值 {float(tol):.6g}。"
                ),
            },
        }

    q, ks, s, d = select_best(xs, max_missing, t)
    fitted = [s + d * k for k in ks]
    deviations = [f - x for f, x in zip(fitted, xs)]
    missing = [ks[i + 1] - ks[i] - 1 for i in range(n - 1)]
    return {
        "feasible": True,
        "spacing": float(d),
        "start": float(s),
        "maxDeviation": float(t),
        "sumSquaredDeviations": float(q),
        "traces": [
            {
                "position": i + 1,
                "x": xs[i],
                "serial": ks[i] + 1,
                "fitted": float(fitted[i]),
                "deviation": float(deviations[i]),
            }
            for i in range(n)
        ],
        "missing": missing,
    }
