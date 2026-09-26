"""Request/response schemas and validation for the restoration API."""

from __future__ import annotations

from fractions import Fraction
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator

MIN_TRACES = 5
MAX_TRACES = 10
MAX_MISSING_PER_GAP = 50
MAX_ABS_X = 1_000_000_000


class RestoreRequest(BaseModel):
    """Input of one restoration job.

    * ``xs``: integer x-positions of the surviving traces, left to right.
    * ``maxMissing``: upper bounds of missing meridians between adjacent
      traces (``len(xs) - 1`` entries).
    * ``tolerance``: allowed positioning error applied to every trace.
    """

    xs: Annotated[list[int], Field(min_length=MIN_TRACES, max_length=MAX_TRACES)]
    maxMissing: list[int]
    tolerance: float

    @field_validator("xs")
    @classmethod
    def _xs_valid(cls, value: list[int]) -> list[int]:
        if any(abs(v) > MAX_ABS_X for v in value):
            raise ValueError(f"横坐标绝对值不得超过 {MAX_ABS_X}")
        if any(b <= a for a, b in zip(value, value[1:])):
            raise ValueError("残迹横坐标必须严格递增（按从左到右录入）")
        return value

    @field_validator("maxMissing")
    @classmethod
    def _missing_valid(cls, value: list[int]) -> list[int]:
        if any(v < 0 or v > MAX_MISSING_PER_GAP for v in value):
            raise ValueError(f"相邻缺线数上限须为 0..{MAX_MISSING_PER_GAP} 的整数")
        return value

    @field_validator("tolerance")
    @classmethod
    def _tolerance_valid(cls, value: float) -> float:
        if not (value == value):  # NaN
            raise ValueError("允许定位误差必须是有限正数")
        if value <= 0 or value == float("inf"):
            raise ValueError("允许定位误差必须是有限正数")
        return value

    @model_validator(mode="after")
    def _lengths_match(self) -> "RestoreRequest":
        if len(self.maxMissing) != len(self.xs) - 1:
            raise ValueError(
                f"缺线数上限须为 {len(self.xs) - 1} 条（残迹数减一），"
                f"实际收到 {len(self.maxMissing)} 条"
            )
        return self

    def tolerance_fraction(self) -> Fraction:
        """Exact rational form of the tolerance (no float noise)."""
        return Fraction(str(self.tolerance))
