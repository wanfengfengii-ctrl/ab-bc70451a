"""API-level tests for the restoration service."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_restore_feasible_exact_grid():
    r = client.post(
        "/api/restore",
        json={"xs": [0, 5, 10, 15, 20], "maxMissing": [1, 1, 1, 1], "tolerance": 0.5},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["feasible"] is True
    assert [t["serial"] for t in body["traces"]] == [1, 2, 3, 4, 5]
    assert body["spacing"] == pytest.approx(5.0)
    assert body["maxDeviation"] == pytest.approx(0.0)
    assert body["missing"] == [0, 0, 0, 0]


def test_restore_feasible_with_filled_missing_line():
    r = client.post(
        "/api/restore",
        json={
            "xs": [0, 10, 30, 40, 50],
            "maxMissing": [0, 1, 0, 0],
            "tolerance": 0.4,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["feasible"] is True
    assert [t["serial"] for t in body["traces"]] == [1, 2, 4, 5, 6]
    assert body["missing"] == [0, 1, 0, 0]


def test_restore_infeasible_returns_first_failing_trace():
    r = client.post(
        "/api/restore",
        json={
            "xs": [0, 10, 11, 20, 30],
            "maxMissing": [0, 0, 0, 0],
            "tolerance": 0.5,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["feasible"] is False
    failure = body["failure"]
    assert failure["trace"] == 3
    assert failure["x"] == 11
    assert failure["requiredTolerance"] == pytest.approx(2.25)
    assert failure["previousSerialRange"] == [2, 2]
    assert failure["candidateSerialRange"] == [3, 3]


@pytest.mark.parametrize(
    "payload",
    [
        # too few / too many traces
        {"xs": [1, 2, 3, 4], "maxMissing": [0, 0, 0], "tolerance": 0.5},
        {
            "xs": list(range(11)),
            "maxMissing": [0] * 10,
            "tolerance": 0.5,
        },
        # not strictly increasing
        {"xs": [0, 5, 5, 15, 20], "maxMissing": [0, 0, 0, 0], "tolerance": 0.5},
        {"xs": [0, 9, 5, 15, 20], "maxMissing": [0, 0, 0, 0], "tolerance": 0.5},
        # maxMissing length mismatch
        {"xs": [0, 5, 10, 15, 20], "maxMissing": [0, 0], "tolerance": 0.5},
        {"xs": [0, 5, 10, 15, 20], "maxMissing": [0] * 5, "tolerance": 0.5},
        # maxMissing out of range
        {"xs": [0, 5, 10, 15, 20], "maxMissing": [-1, 0, 0, 0], "tolerance": 0.5},
        {"xs": [0, 5, 10, 15, 20], "maxMissing": [51, 0, 0, 0], "tolerance": 0.5},
        # bad tolerance
        {"xs": [0, 5, 10, 15, 20], "maxMissing": [0, 0, 0, 0], "tolerance": 0},
        {"xs": [0, 5, 10, 15, 20], "maxMissing": [0, 0, 0, 0], "tolerance": -1},
        # non-integer coordinates
        {
            "xs": [0, 5.5, 10, 15, 20],
            "maxMissing": [0, 0, 0, 0],
            "tolerance": 0.5,
        },
    ],
)
def test_restore_validation_errors(payload):
    r = client.post("/api/restore", json=payload)
    assert r.status_code == 422
    assert r.json()["detail"]


def test_restore_accepts_six_to_ten_traces():
    for n in (5, 7, 10):
        xs = [i * 7 for i in range(n)]
        r = client.post(
            "/api/restore",
            json={
                "xs": xs,
                "maxMissing": [1] * (n - 1),
                "tolerance": 0.25,
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["feasible"] is True
        assert len(body["traces"]) == n
        assert len(body["missing"]) == n - 1
