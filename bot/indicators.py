from __future__ import annotations
from typing import List

def calculate_sma(prices: List[float], period: int) -> float:
    if len(prices) < period:
        raise ValueError(f"Not enough data for SMA calculation: required {period}, got {len(prices)}")
    subset = prices[-period:]
    return sum(subset) / period