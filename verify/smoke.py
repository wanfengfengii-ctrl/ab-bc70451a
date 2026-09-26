"""Smoke tests against the live restoration API.

Targets the nginx-proxied deployment (API_BASE_URL, default http://web) so the
whole request path used by the frontend is exercised, and additionally checks
the api service health endpoint directly (API_DIRECT_URL).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("API_BASE_URL", "http://web").rstrip("/")
DIRECT = os.environ.get("API_DIRECT_URL", "http://api:8000").rstrip("/")

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "ok" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def request(method: str, url: str, payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, {"_raw": raw}
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode())
        except Exception:
            return exc.code, {}


def main() -> int:
    print(f"smoke: proxied base = {BASE}, direct api = {DIRECT}")

    status, body = request("GET", f"{DIRECT}/health")
    check("api /health responds ok", status == 200 and body.get("status") == "ok",
          f"status={status} body={body}")

    status, body = request("GET", f"{BASE}/healthz")
    check("web /healthz responds ok", status == 200, f"status={status}")

    # 1. Exact grid through the nginx proxy: serials 1..5, spacing 5.
    status, body = request(
        "POST",
        f"{BASE}/api/restore",
        {"xs": [0, 5, 10, 15, 20], "maxMissing": [1, 1, 1, 1], "tolerance": 0.5},
    )
    ok = (
        status == 200
        and body.get("feasible") is True
        and [t["serial"] for t in body["traces"]] == [1, 2, 3, 4, 5]
        and abs(body["spacing"] - 5.0) < 1e-9
        and abs(body["maxDeviation"]) < 1e-9
        and body["missing"] == [0, 0, 0, 0]
    )
    check("restore exact grid via proxy", ok, f"status={status} body={body}")

    # 2. A missing meridian must be filled between traces 2 and 3.
    status, body = request(
        "POST",
        f"{BASE}/api/restore",
        {"xs": [0, 10, 30, 40, 50], "maxMissing": [0, 1, 0, 0], "tolerance": 0.4},
    )
    ok = (
        status == 200
        and body.get("feasible") is True
        and [t["serial"] for t in body["traces"]] == [1, 2, 4, 5, 6]
        and body["missing"] == [0, 1, 0, 0]
    )
    check("restore fills missing meridian", ok, f"status={status} body={body}")

    # 3. Infeasible input: the first unsatisfiable trace and the adjacent
    #    determined serial interval must be reported.
    status, body = request(
        "POST",
        f"{BASE}/api/restore",
        {"xs": [0, 10, 11, 20, 30], "maxMissing": [0, 0, 0, 0], "tolerance": 0.5},
    )
    failure = body.get("failure", {})
    ok = (
        status == 200
        and body.get("feasible") is False
        and failure.get("trace") == 3
        and failure.get("x") == 11
        and abs(failure.get("requiredTolerance", 0) - 2.25) < 1e-9
        and failure.get("previousSerialRange") == [2, 2]
        and failure.get("candidateSerialRange") == [3, 3]
    )
    check("infeasible case reports first failing trace", ok,
          f"status={status} body={body}")

    # 4. Invalid input is rejected with 422.
    status, _ = request(
        "POST",
        f"{BASE}/api/restore",
        {"xs": [0, 5, 5, 15, 20], "maxMissing": [0, 0, 0, 0], "tolerance": 0.5},
    )
    check("non-increasing coordinates rejected with 422", status == 422,
          f"status={status}")

    if failures:
        print(f"smoke: {len(failures)} check(s) failed: {failures}")
        return 1
    print("smoke: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
