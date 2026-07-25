"""In-memory research-only forecast contract."""

import math
import re
from dataclasses import dataclass
from datetime import datetime


_SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")


@dataclass(frozen=True, slots=True)
class ForecastRecord:
    symbol: str
    as_of_timestamp: datetime
    valid_until_timestamp: datetime
    horizon_sessions: int
    raw_model_score: float
    standardized_score: float
    rank: int
    model_artifact_path: str
    model_artifact_sha256: str
    dataset_identity_sha256: str
    adjustment_identity_sha256: str
    feature_identity_sha256: str
    universe_identity_sha256: str
    expert_version: str
    feature_version: str
    run_manifest_sha256: str
    schema_version: str = "1"
    expert_id: str = "xgb_ranker"
    target_definition: str = "cross_sectional_5_session_forward_return_rank"
    raw_score_units: str = "standardized_forward_return_label_score"
    score_units: str = "cross_sectional_zscore"
    direction: str = "higher_is_better"
    data_freshness_status: str = "current"
    research_only: bool = True
    execution_authority: bool = False
    authority_state: str = "shadow"

    def __post_init__(self):
        if not isinstance(self.as_of_timestamp, datetime):
            raise ValueError("as_of_timestamp must be a datetime")
        if not isinstance(self.valid_until_timestamp, datetime):
            raise ValueError("valid_until_timestamp must be a datetime")
        if self.valid_until_timestamp < self.as_of_timestamp:
            raise ValueError("valid_until_timestamp must not be earlier than as_of_timestamp")
        if not self.symbol.strip():
            raise ValueError("symbol must not be blank")
        if not self.model_artifact_path.strip():
            raise ValueError("model_artifact_path must not be blank")
        for field in ("expert_version", "feature_version"):
            if not getattr(self, field).strip():
                raise ValueError(f"{field} must not be blank")
        for field, expected in (
            ("schema_version", "1"),
            ("expert_id", "xgb_ranker"),
            ("target_definition", "cross_sectional_5_session_forward_return_rank"),
            ("raw_score_units", "standardized_forward_return_label_score"),
            ("score_units", "cross_sectional_zscore"),
            ("direction", "higher_is_better"),
            ("data_freshness_status", "current"),
        ):
            if getattr(self, field) != expected:
                raise ValueError(f"{field} must be {expected}")
        if (
            isinstance(self.horizon_sessions, bool)
            or not isinstance(self.horizon_sessions, int)
            or self.horizon_sessions != 5
        ):
            raise ValueError("horizon_sessions must be 5")
        for field in ("raw_model_score", "standardized_score"):
            value = getattr(self, field)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(f"{field} must be finite")
        if (
            isinstance(self.rank, bool)
            or not isinstance(self.rank, int)
            or self.rank < 1
        ):
            raise ValueError("rank must be a positive integer")
        for field in (
            "model_artifact_sha256",
            "dataset_identity_sha256",
            "adjustment_identity_sha256",
            "feature_identity_sha256",
            "universe_identity_sha256",
            "run_manifest_sha256",
        ):
            if not _SHA256.fullmatch(getattr(self, field)):
                raise ValueError(f"{field} must be a 64-character hexadecimal SHA-256")
        if self.research_only is not True:
            raise ValueError("research_only must be True")
        if self.execution_authority is not False:
            raise ValueError("execution_authority must be False")
        if self.authority_state != "shadow":
            raise ValueError("authority_state must be shadow")
