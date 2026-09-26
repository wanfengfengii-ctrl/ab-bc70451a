"""FastAPI application exposing the meridian grid restoration service."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import solver
from .schemas import RestoreRequest

app = FastAPI(
    title="航海图经线网复原 API",
    version="1.0.0",
    description=(
        "将受潮航海图上按从左到右录入的经线残迹复原为同一套经线网："
        "联合确定严格递增的整数序号、正的共同网距与起始位置，"
        "依次使最大偏差最小、偏差平方和最小、相邻缺线数序列字典序最小。"
    ),
)

# The production deployment serves the frontend through the same origin
# (nginx proxies /api), but CORS stays open for local development where the
# Vite dev server runs on a different port.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/restore")
def restore(request: RestoreRequest) -> dict:
    try:
        return solver.restore(
            request.xs, request.maxMissing, request.tolerance_fraction()
        )
    except solver.SearchLimitExceeded as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"复原搜索超出安全预算：{exc}")
