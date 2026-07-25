import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from vesper.data.split_adjustments import apply_split_adjustments, load_split_adjustments


ROOT = Path(__file__).resolve().parents[1]
RECEIPT_PATH = ROOT / "reports" / "gate_a_split_adjustment_admission_v1.json"


def _write_adjustments(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_admission_receipt_binds_canonical_feature_code():
    receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    assert receipt["feature_code_hash_basis"] == (
        "SHA-256 of file bytes with CRLF normalized to LF; equivalent to staged Git blob content"
    )

    for relative_path, expected_hash in receipt["feature_code_identity"].items():
        canonical_bytes = (ROOT / relative_path).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(canonical_bytes).hexdigest() == expected_hash


def test_load_split_adjustments_rejects_missing_file(tmp_path):
    missing = tmp_path / "split_adjustments.json"

    with pytest.raises(FileNotFoundError, match="Split adjustments not found"):
        load_split_adjustments(missing, expected_sha256="0" * 64)


def test_load_split_adjustments_rejects_hash_mismatch(tmp_path):
    path = tmp_path / "split_adjustments.json"
    path.write_text('{"AAA": {"2024-01-01": 1.0}}', encoding="utf-8")
    actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match=f"expected {'0' * 64}, got {actual_hash}"):
        load_split_adjustments(path, expected_sha256="0" * 64)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"": {"2024-01-01": 1.0}},
        {" AAA ": {"2024-01-01": 1.0}},
        {"aaa": {"2024-01-01": 1.0}},
        {"AAA": []},
        {"AAA": {}},
        {"AAA": {"not-a-date": 1.0}},
        {"AAA": {"2024-01-01": True}},
        {"AAA": {"2024-01-01": 0.0}},
        {"AAA": {"2024-01-01": -1.0}},
        {"AAA": {"2024-01-01": float("nan")}},
        {"AAA": {"2024-01-01": float("inf")}},
        {"AAA": {"2024-01-01": "1.0"}},
    ],
)
def test_load_split_adjustments_rejects_invalid_schema(tmp_path, payload):
    path = tmp_path / "split_adjustments.json"
    expected_hash = _write_adjustments(path, payload)

    with pytest.raises(ValueError, match="Invalid split adjustments"):
        load_split_adjustments(path, expected_sha256=expected_hash)


def test_load_split_adjustments_requires_universe_coverage(tmp_path):
    path = tmp_path / "split_adjustments.json"
    expected_hash = _write_adjustments(path, {"AAA": {"2024-01-01": 1.0}})

    with pytest.raises(ValueError, match="missing required tickers: BBB"):
        load_split_adjustments(
            path,
            expected_sha256=expected_hash,
            required_tickers=["AAA", "BBB"],
        )


def test_load_split_adjustments_rejects_duplicate_json_keys(tmp_path):
    path = tmp_path / "split_adjustments.json"
    path.write_text(
        '{"AAA": {"2024-01-01": 1.0}, "AAA": {"2024-01-02": 1.0}}',
        encoding="utf-8",
    )
    expected_hash = hashlib.sha256(path.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="duplicate key 'AAA'"):
        load_split_adjustments(path, expected_sha256=expected_hash)


def test_load_split_adjustments_rejects_duplicate_date_keys(tmp_path):
    path = tmp_path / "split_adjustments.json"
    path.write_text(
        '{"AAA": {"2024-01-01": 1.0, "2024-01-01": 0.5}}',
        encoding="utf-8",
    )
    expected_hash = hashlib.sha256(path.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="duplicate key '2024-01-01'"):
        load_split_adjustments(path, expected_sha256=expected_hash)


def test_apply_split_adjustments_changes_prices_only():
    index = pd.to_datetime(
        ["2023-12-29", "2024-01-02", "2024-01-03", "2024-01-04"]
    )
    frame = pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0, 100.0],
            "high": [110.0, 110.0, 110.0, 110.0],
            "low": [90.0, 90.0, 90.0, 90.0],
            "close": [105.0, 105.0, 105.0, 105.0],
            "volume": [1000, 2000, 3000, 4000],
        },
        index=index,
    )
    bars = {"AAA": frame, "BBB": frame.copy()}

    adjusted = apply_split_adjustments(
        bars,
        {"AAA": {"2024-01-02": 0.5, "2024-01-03": 1.0}},
    )

    assert adjusted["AAA"]["close"].tolist() == [105.0, 52.5, 105.0, 105.0]
    assert adjusted["AAA"]["open"].tolist() == [100.0, 50.0, 100.0, 100.0]
    assert adjusted["AAA"]["high"].tolist() == [110.0, 55.0, 110.0, 110.0]
    assert adjusted["AAA"]["low"].tolist() == [90.0, 45.0, 90.0, 90.0]
    assert adjusted["AAA"]["volume"].tolist() == [1000, 2000, 3000, 4000]
    assert adjusted["BBB"].equals(frame)
    assert bars["AAA"]["close"].tolist() == [105.0, 105.0, 105.0, 105.0]
