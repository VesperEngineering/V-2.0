#!/usr/bin/env python3
"""Research-only SPY evaluator with explicit information and execution clocks."""

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import NamedTuple

import numpy as np
import pandas as pd


LOOKBACK_SESSIONS = 20
HOLDING_SESSIONS = 5


class Block(NamedTuple):
    feature_position: int
    entry_position: int
    exit_position: int
    feature_return: float


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1_048_576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verified_json(path: Path, expected_sha256: str) -> dict:
    if _sha256(path) != expected_sha256:
        raise ValueError("hash mismatch")
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_contract_provenance(contract: dict, database: Path, database_sha256: str):
    expected = {
        "database": {
            "path": str(database.resolve()),
            "sha256": database_sha256,
            "metadata": {"price_basis": "total_return_adjusted", "timeframe": "1day"},
        },
        "evaluator": {"path": str(Path(__file__).resolve()), "sha256": _sha256(Path(__file__))},
    }
    provenance = contract.get("provenance")
    freeze = contract.get("freeze")
    if provenance != expected or freeze != {
        "database_sha256": database_sha256,
        "evaluator_sha256": expected["evaluator"]["sha256"],
    }:
        raise ValueError("contract provenance mismatch")


def _canonical_sha256(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _verify_final_manifest(
    manifest: Path, manifest_sha256: str, contract_sha256: str, database_sha256: str, freeze: dict
):
    sealed = _verified_json(manifest, manifest_sha256)
    expected = {
        "contract_sha256": contract_sha256,
        "database_sha256": database_sha256,
        "evaluator_sha256": _sha256(Path(__file__)),
        "freeze_sha256": _canonical_sha256(freeze),
    }
    if sealed.get("sealed") is not True or sealed.get("phase") != "final" or sealed.get("bindings") != expected:
        raise ValueError("final manifest binding mismatch")


def load_spy_rows(database: Path, expected_sha256: str) -> pd.DataFrame:
    """Load SPY rows from the declared total-return adapter without write access."""
    if _sha256(database) != expected_sha256:
        raise ValueError("database hash mismatch")
    uri = f"{database.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        metadata = dict(connection.execute("SELECT key, value FROM adapter_metadata"))
        if metadata.get("price_basis") != "total_return_adjusted":
            raise ValueError("total-return price basis required")
        if metadata.get("timeframe") != "1day":
            raise ValueError("one-day timeframe required")
        rows = pd.read_sql_query(
            "SELECT data.timestamp, data.open, data.high, data.low, data.close, "
            "source.source_ticker, source.source_as_of_date, source.source_key, source.source_sha256 "
            "FROM ohlcv_data AS data "
            "LEFT JOIN ohlcv_source_map AS source "
            "ON source.ticker = data.ticker "
            "AND source.timestamp = data.timestamp "
            "AND source.timeframe = data.timeframe "
            "WHERE data.ticker = 'SPY' AND data.timeframe = '1day' "
            "ORDER BY data.rowid",
            connection,
        )
    if rows.empty:
        raise ValueError("SPY rows required")
    if rows["timestamp"].duplicated().any() or not rows["timestamp"].is_monotonic_increasing:
        raise ValueError("SPY timestamps must be unique and monotonic")
    prices = rows[["open", "high", "low", "close"]].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(prices.to_numpy(dtype=float)).all() or (prices <= 0).any().any():
        raise ValueError("finite positive OHLC prices required")
    rows[["open", "high", "low", "close"]] = prices
    source_fields = ["source_ticker", "source_as_of_date", "source_key", "source_sha256"]
    if rows[source_fields].isna().any().any() or not all(
        rows[field].map(lambda value: isinstance(value, str) and bool(value.strip())).all()
        for field in source_fields
    ):
        raise ValueError("source mapping required")
    return rows


def feature_return(rows: pd.DataFrame, feature_position: int) -> float:
    if feature_position < LOOKBACK_SESSIONS:
        raise ValueError("insufficient feature history")
    start = float(rows.loc[feature_position - LOOKBACK_SESSIONS, "close"])
    end = float(rows.loc[feature_position, "close"])
    if start <= 0:
        raise ValueError("positive feature prices required")
    return end / start - 1


def build_blocks(rows: pd.DataFrame, formation_positions) -> list[Block]:
    """Build fixed labels without outcome-conditioned filtering."""
    blocks = []
    for feature_position in formation_positions:
        entry_position = feature_position + 1
        exit_position = feature_position + HOLDING_SESSIONS
        if entry_position >= len(rows) or exit_position >= len(rows):
            raise ValueError("label extends beyond available rows")
        entry_open = float(rows.loc[entry_position, "open"])
        exit_open = float(rows.loc[exit_position, "open"])
        if entry_open <= 0 or exit_open <= 0:
            raise ValueError("positive execution prices required")
        blocks.append(
            Block(
                feature_position,
                entry_position,
                exit_position,
                feature_return(rows, feature_position),
            )
        )
    return blocks


def evaluate_phase_outcomes(
    phase: str,
    *,
    contract_path: Path,
    contract_sha256: str,
    database: Path,
    database_sha256: str,
    sealed_manifest: Path | None = None,
    expected_sha256: str | None = None,
    cost_bps: int = 10,
) -> list[dict]:
    """Atomically evaluate only the contract-declared blocks for one admitted phase."""
    if phase not in {"development", "selection", "final"}:
        raise ValueError("unknown phase")
    contract = _verified_json(contract_path, contract_sha256)
    if contract.get("phase") != phase:
        raise ValueError("contract phase mismatch")
    _verify_contract_provenance(contract, database, database_sha256)
    if phase == "final":
        if sealed_manifest is None or expected_sha256 is None:
            raise ValueError("final phase requires complete sealed-manifest bindings")
        _verify_final_manifest(
            sealed_manifest,
            expected_sha256,
            contract_sha256,
            database_sha256,
            contract["freeze"],
        )
        raise ValueError("external final approval required for outcome evaluation")
    rows = load_spy_rows(database, database_sha256)
    blocks_by_partition = build_partition_blocks(rows, contract.get("partitions"))
    assert_partition_purge_and_embargo(blocks_by_partition)
    if phase not in blocks_by_partition:
        raise ValueError("contract phase blocks required")

    def net_return(block: Block, invested: bool) -> dict:
        entry_open = float(rows.loc[block.entry_position, "open"])
        exit_open = float(rows.loc[block.exit_position, "open"])
        gross_return = exit_open / entry_open - 1 if invested else 0.0
        cost = 2 * cost_bps / 10_000 if invested else 0.0
        return {
            "entry_position": block.entry_position,
            "exit_position": block.exit_position,
            "entry_open": entry_open,
            "exit_open": exit_open,
            "cost_bps_per_side": cost_bps,
            "net_return": gross_return - cost,
        }

    outcomes = [
        {
            "candidate": net_return(block, block.feature_return > 0),
            "baseline": net_return(block, True),
        }
        for block in blocks_by_partition[phase]
    ]
    if _sha256(contract_path) != contract_sha256:
        raise ValueError("contract changed during evaluation")
    if _sha256(database) != database_sha256:
        raise ValueError("database changed during evaluation")
    return outcomes


def assert_partition_isolation(blocks_by_partition: dict[str, list[Block]]):
    intervals = []
    for partition, blocks in blocks_by_partition.items():
        intervals.extend((block.feature_position, block.exit_position, partition) for block in blocks)
    for index, (start, end, partition) in enumerate(intervals):
        for other_start, other_end, other_partition in intervals[index + 1:]:
            if start <= other_end and other_start <= end:
                raise ValueError("partition label intervals overlap")


def _assert_boundary(boundary_position: int, formation_positions, required_sessions: int, name: str):
    if any(position <= boundary_position + required_sessions for position in formation_positions):
        raise ValueError(f"{name} boundary leakage")


def assert_purge(boundary_position: int, formation_positions, required_sessions: int = HOLDING_SESSIONS):
    _assert_boundary(boundary_position, formation_positions, required_sessions, "purge")


def assert_embargo(boundary_position: int, formation_positions, required_sessions: int = HOLDING_SESSIONS):
    _assert_boundary(boundary_position, formation_positions, required_sessions, "embargo")


def build_partition_blocks(rows: pd.DataFrame, partitions: dict) -> dict[str, list[Block]]:
    if not isinstance(partitions, dict) or not partitions:
        raise ValueError("contract partitions required")
    if any(not isinstance(name, str) or not isinstance(positions, list) or not positions for name, positions in partitions.items()):
        raise ValueError("contract partitions required")
    return {name: build_blocks(rows, positions) for name, positions in partitions.items()}


def assert_partition_purge_and_embargo(blocks_by_partition: dict[str, list[Block]]):
    assert_partition_isolation(blocks_by_partition)
    ordered = sorted(blocks_by_partition.items(), key=lambda item: min(block.feature_position for block in item[1]))
    for (_, earlier), (_, later) in zip(ordered, ordered[1:]):
        boundary = max(block.exit_position for block in earlier)
        formations = [block.feature_position for block in later]
        assert_embargo(boundary, formations)
        assert_purge(boundary, formations)


def moving_block_interval(differences, seed: int = 42, samples: int = 10_000, block_length: int = 4):
    values = np.asarray(differences, dtype=float)
    if len(values) == 0:
        raise ValueError("differences required")
    generator = np.random.default_rng(seed)
    means = []
    for _ in range(samples):
        sample = []
        while len(sample) < len(values):
            start = int(generator.integers(0, len(values)))
            sample.extend(values[(start + offset) % len(values)] for offset in range(block_length))
        means.append(float(np.mean(sample[:len(values)])))
    return tuple(float(value) for value in np.quantile(means, [0.025, 0.975]))


def main():
    parser = argparse.ArgumentParser(description="Verify an admitted SPY experiment input without computing outcomes")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--database-sha256", required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--phase", choices=("development", "selection", "final"), required=True)
    parser.add_argument("--sealed-manifest", type=Path)
    parser.add_argument("--sealed-manifest-sha256")
    args = parser.parse_args()

    contract = _verified_json(args.contract, args.contract_sha256)
    if contract.get("phase") != args.phase:
        raise ValueError("contract phase mismatch")
    _verify_contract_provenance(contract, args.database, args.database_sha256)
    if args.phase == "final":
        if args.sealed_manifest is None or args.sealed_manifest_sha256 is None:
            raise ValueError("final phase requires complete sealed-manifest bindings")
        _verify_final_manifest(
            args.sealed_manifest,
            args.sealed_manifest_sha256,
            args.contract_sha256,
            args.database_sha256,
            contract["freeze"],
        )
    rows = load_spy_rows(args.database, args.database_sha256)
    assert_partition_purge_and_embargo(build_partition_blocks(rows, contract.get("partitions")))
    spy_rows = len(rows)
    print(json.dumps({"phase": args.phase, "spy_rows": spy_rows, "integrity_only": True}, indent=2))


if __name__ == "__main__":
    main()
