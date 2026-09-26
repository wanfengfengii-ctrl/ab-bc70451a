"""Unit tests for the exact meridian-grid restoration solver."""

from __future__ import annotations

import random
from fractions import Fraction
from itertools import combinations, product

import pytest

from app import solver
from app.solver import (
    cheb_value,
    constrained_least_squares,
    min_cheb,
    restore,
    select_best,
)

TOL = Fraction(1, 2)


# ---------------------------------------------------------------------------
# Deterministic scenarios
# ---------------------------------------------------------------------------


def test_exact_grid_without_missing_lines():
    r = restore([0, 5, 10, 15, 20], [1, 1, 1, 1], Fraction(1, 2))
    assert r["feasible"] is True
    assert [t["serial"] for t in r["traces"]] == [1, 2, 3, 4, 5]
    assert r["spacing"] == pytest.approx(5.0)
    assert r["start"] == pytest.approx(0.0)
    assert r["maxDeviation"] == 0.0
    assert r["sumSquaredDeviations"] == 0.0
    assert r["missing"] == [0, 0, 0, 0]
    assert all(t["deviation"] == 0.0 for t in r["traces"])


def test_forced_missing_line_is_filled():
    # The gap between the 2nd and 3rd trace spans two grid steps.
    r = restore([0, 10, 30, 40, 50], [0, 1, 0, 0], Fraction(2, 5))
    assert r["feasible"] is True
    assert [t["serial"] for t in r["traces"]] == [1, 2, 4, 5, 6]
    assert r["missing"] == [0, 1, 0, 0]
    assert r["spacing"] == pytest.approx(10.0)
    assert r["maxDeviation"] == 0.0


def test_missing_sequence_is_lexicographically_minimal():
    # Both spacing 10 (no missing lines) and spacing 5 (one missing line per
    # gap) fit exactly; the lexicographically smaller missing sequence wins.
    r = restore([0, 10, 20, 30, 40], [2, 2, 2, 2], Fraction(1, 4))
    assert r["feasible"] is True
    assert r["missing"] == [0, 0, 0, 0]
    assert r["spacing"] == pytest.approx(10.0)


def test_max_deviation_is_minimised_before_least_squares():
    # Unconstrained least squares would need max deviation 0.6; the
    # lexicographic objective first pushes the maximum down to 0.5.
    r = restore([0, 10, 21, 31, 40], [1, 1, 1, 1], Fraction(2))
    assert r["feasible"] is True
    assert r["maxDeviation"] == pytest.approx(0.5)
    assert r["sumSquaredDeviations"] == pytest.approx(1.25)
    for t in r["traces"]:
        assert abs(t["deviation"]) <= r["maxDeviation"] + 1e-9
        assert t["fitted"] == pytest.approx(t["x"] + t["deviation"])


def test_global_arbitration_beats_per_segment_rounding():
    # Per-segment nearest rounding of x/d0 would misplace serials here; the
    # global optimum keeps every deviation within tolerance.
    xs = [0, 11, 19, 31, 39, 50]
    r = restore(xs, [1] * 5, Fraction(3, 2))
    assert r["feasible"] is True
    assert r["maxDeviation"] <= 1.5
    serials = [t["serial"] for t in r["traces"]]
    assert serials == sorted(serials) and len(set(serials)) == len(serials)


def test_infeasible_reports_first_failing_trace():
    r = restore([0, 10, 11, 20, 30], [0, 0, 0, 0], Fraction(1, 2))
    assert r["feasible"] is False
    failure = r["failure"]
    assert failure["trace"] == 3
    assert failure["x"] == 11
    assert failure["requiredTolerance"] == pytest.approx(2.25)
    assert failure["previousSerialRange"] == [2, 2]
    assert failure["candidateSerialRange"] == [3, 3]
    assert "第 3 条残迹" in failure["message"]


def test_infeasible_reports_determined_serial_interval():
    # The first two traces may occupy serials (1,2) or (1,3); the third trace
    # then has candidates but none meets the tolerance.
    r = restore([0, 10, 11, 25, 40], [1, 1, 1, 1], Fraction(1, 2))
    assert r["feasible"] is False
    failure = r["failure"]
    assert failure["trace"] == 3
    assert failure["previousSerialRange"] == [2, 3]
    assert failure["candidateSerialRange"] == [3, 5]
    assert failure["requiredTolerance"] == pytest.approx(4 / 3)


def test_prefix_monotonicity_of_failure():
    # Traces 1..3 are feasible, adding the 4th (x=13) breaks the tolerance.
    r = restore([0, 10, 20, 13, 40], [0, 0, 0, 0], Fraction(1, 2))
    assert r["feasible"] is False
    assert r["failure"]["trace"] == 4


# ---------------------------------------------------------------------------
# Independent cross-check of the Chebyshev value via LP vertex enumeration
# ---------------------------------------------------------------------------


def _cheb_by_vertex_enumeration(ks, xs):
    """Brute-force exact LP solve: the optimum of

        min t  s.t.  -t <= x_i - s - k_i d <= t

    sits at a vertex defined by three active bound constraints.
    """
    n = len(ks)
    constraints = []  # (k_i, x_i, sign): s + k_i d + sign*t = x_i
    for i in range(n):
        constraints.append((ks[i], xs[i], 1))
        constraints.append((ks[i], xs[i], -1))
    best = None

    def det3(m):
        return (
            m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
        )

    # Solve each 3x3 active-constraint system with exact arithmetic.
    for (k1, x1, s1), (k2, x2, s2), (k3, x3, s3) in combinations(constraints, 3):
        # rows: s + k*d + sign*t = x
        a = [[1, k1, s1], [1, k2, s2], [1, k3, s3]]
        det = det3(a)
        if det == 0:
            continue
        bx, bd, bt = (
            [[x1, a[0][1], a[0][2]], [x2, a[1][1], a[1][2]], [x3, a[2][1], a[2][2]]],
            [[1, x1, a[0][2]], [1, x2, a[1][2]], [1, x3, a[2][2]]],
            [[1, k1, x1], [1, k2, x2], [1, k3, x3]],
        )
        s = Fraction(det3(bx), det)
        d = Fraction(det3(bd), det)
        t = Fraction(det3(bt), det)
        if t < 0:
            continue
        if all(abs(s + k * d - x) <= t for k, x in zip(ks, xs)):
            if best is None or t < best:
                best = t
    return best if best is not None else Fraction(0)


def test_cheb_value_matches_lp_vertices():
    rng = random.Random(20260926)
    for _ in range(60):
        n = rng.randint(3, 7)
        xs = sorted(rng.sample(range(0, 200), n))
        ks = sorted(rng.sample(range(0, 30), n))
        assert cheb_value(ks, xs) == _cheb_by_vertex_enumeration(ks, xs)


# ---------------------------------------------------------------------------
# Agreement with an exhaustive brute-force reference implementation
# ---------------------------------------------------------------------------


def _brute_force_restore(xs, max_missing, tol):
    """Naive enumeration of every composition — the reference behaviour."""
    n = len(xs)
    best = None
    for gaps in product(*[range(1, m + 2) for m in max_missing]):
        ks = [0]
        for g in gaps:
            ks.append(ks[-1] + g)
        t = cheb_value(ks, xs)
        if t > tol:
            continue
        q, s, d = constrained_least_squares(ks, xs, t)
        missing = tuple(g - 1 for g in gaps)
        key = (t, q, missing)
        if best is None or key < best[0]:
            best = (key, ks, s, d)
    return best


def test_restore_matches_brute_force_on_random_instances():
    rng = random.Random(1234567)
    for case in range(80):
        n = rng.randint(5, 7)
        max_missing = [rng.randint(0, 2) for _ in range(n - 1)]
        xs = sorted(rng.sample(range(0, 120), n))
        tol = Fraction(rng.randint(1, 6), 2)
        expected = _brute_force_restore(xs, max_missing, tol)
        got = restore(xs, max_missing, tol)
        if expected is None:
            assert got["feasible"] is False, f"case {case}: {xs} {max_missing}"
            continue
        (t, q, missing), ks, s, d = expected
        assert got["feasible"] is True, f"case {case}: {xs} {max_missing}"
        assert got["maxDeviation"] == pytest.approx(float(t))
        assert got["sumSquaredDeviations"] == pytest.approx(float(q))
        assert tuple(got["missing"]) == missing
        assert [tr["serial"] for tr in got["traces"]] == [k + 1 for k in ks]
        assert got["spacing"] == pytest.approx(float(d))
        assert got["start"] == pytest.approx(float(s))


def test_constrained_least_squares_is_optimal_numeric_check():
    # Fine-grid numeric falsification of the exact constrained LS solution.
    rng = random.Random(777)
    for _ in range(25):
        n = rng.randint(4, 7)
        ks = sorted(rng.sample(range(0, 24), n))
        xs = sorted(rng.sample(range(0, 200), n))
        t = cheb_value(ks, xs)
        q, s, d = constrained_least_squares(ks, xs, t)
        tf = float(t)
        sf, df, qf = float(s), float(d), float(q)
        for _ in range(4000):
            s_try = sf + rng.uniform(-1, 1) * (tf + 0.5)
            d_try = df + rng.uniform(-1, 1) * (tf + 0.5) / max(1, ks[-1])
            if d_try <= 0:
                continue
            res = [s_try + k * d_try - x for k, x in zip(ks, xs)]
            if all(abs(r) <= tf + 1e-12 for r in res):
                assert sum(r * r for r in res) >= qf - 1e-9


# ---------------------------------------------------------------------------
# Structural properties
# ---------------------------------------------------------------------------


def test_serials_are_strictly_increasing_and_spacing_positive():
    rng = random.Random(42)
    for _ in range(30):
        n = rng.randint(5, 9)
        # Perturb a true grid by at most 2 units so tolerance 5 is feasible.
        d_true = rng.randint(12, 60)
        s_true = rng.randint(-100, 100)
        max_missing = [rng.randint(0, 3) for _ in range(n - 1)]
        ks = [0]
        for m in max_missing:
            ks.append(ks[-1] + rng.randint(1, m + 1))
        xs = [s_true + k * d_true + rng.randint(-2, 2) for k in ks]
        assert all(b > a for a, b in zip(xs, xs[1:]))
        r = restore(xs, max_missing, Fraction(5))
        assert r["feasible"] is True
        serials = [t["serial"] for t in r["traces"]]
        assert all(b > a for a, b in zip(serials, serials[1:]))
        assert r["spacing"] > 0
        for i, m in enumerate(r["missing"]):
            assert m == serials[i + 1] - serials[i] - 1
            assert 0 <= m <= max_missing[i]
        for t in r["traces"]:
            assert abs(t["deviation"]) <= 5 + 1e-9


def test_min_cheb_and_select_best_agree():
    xs = [3, 17, 29, 44, 58, 71]
    max_missing = [2, 1, 2, 1, 2]
    t = min_cheb(xs, max_missing)
    q, ks, s, d = select_best(xs, max_missing, t)
    assert cheb_value(ks, xs) == t
    residuals = [s + k * d - x for k, x in zip(ks, xs)]
    assert max(abs(r) for r in residuals) == t
    assert sum((r * r for r in residuals), Fraction(0)) == q
