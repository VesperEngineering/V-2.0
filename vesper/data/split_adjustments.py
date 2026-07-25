"""Fail-closed loading and application of V20 split adjustments."""

import hashlib
import json
import math
from collections.abc import Iterable
from datetime import date
from pathlib import Path

import pandas as pd


SPLIT_ADJUSTMENTS_PATH = Path("vesper/data/massive/split_adjustments.json")
SPLIT_ADJUSTMENTS_SHA256 = "f4f20d413783b0dd0d32b8bbf8e018d96b8098dba2351a2495737a8ec9dd763a"


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Invalid split adjustments: duplicate key {key!r}")
        result[key] = value
    return result


def load_split_adjustments(
    path: Path,
    *,
    expected_sha256: str,
    required_tickers: Iterable[str] = (),
) -> dict[str, dict[str, float]]:
    if not path.is_file():
        raise FileNotFoundError(f"Split adjustments not found: {path}")
    raw = path.read_bytes()
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"Split adjustment hash mismatch: expected {expected_sha256}, got {actual_sha256}"
        )
    adjustments = json.loads(raw, object_pairs_hook=_unique_object)
    if not isinstance(adjustments, dict) or not adjustments:
        raise ValueError("Invalid split adjustments: root must be a non-empty object")
    for ticker, factors in adjustments.items():
        if (
            not isinstance(ticker, str)
            or not ticker.strip()
            or ticker != ticker.strip()
            or ticker != ticker.upper()
        ):
            raise ValueError(
                "Invalid split adjustments: ticker must be a normalized uppercase string"
            )
        if not isinstance(factors, dict) or not factors:
            raise ValueError(
                f"Invalid split adjustments for {ticker}: factors must be a non-empty object"
            )
        for date_text, factor in factors.items():
            try:
                parsed_date = date.fromisoformat(date_text)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid split adjustments for {ticker}: invalid date {date_text!r}"
                ) from exc
            if parsed_date.isoformat() != date_text:
                raise ValueError(
                    f"Invalid split adjustments for {ticker}: invalid date {date_text!r}"
                )
            if (
                isinstance(factor, bool)
                or not isinstance(factor, (int, float))
                or not math.isfinite(factor)
                or factor <= 0
            ):
                raise ValueError(
                    f"Invalid split adjustments for {ticker}: invalid factor on {date_text}"
                )
    missing = sorted(set(required_tickers) - adjustments.keys())
    if missing:
        raise ValueError(
            f"Invalid split adjustments: missing required tickers: {', '.join(missing)}"
        )
    return adjustments


def apply_split_adjustments(
    bars: dict[str, pd.DataFrame],
    adjustments: dict[str, dict[str, float]],
) -> dict[str, pd.DataFrame]:
    adjusted = {}
    for ticker, frame in bars.items():
        frame = frame.copy()
        ticker_factors = adjustments.get(ticker, {})
        if ticker_factors:
            factors = pd.Series(
                {pd.Timestamp(date_text): factor for date_text, factor in ticker_factors.items()}
            ).sort_index()
            factors = factors.reindex(frame.index, method="ffill").fillna(1.0)
            for column in ("open", "high", "low", "close"):
                frame[column] = frame[column] * factors
        adjusted[ticker] = frame
    return adjusted
