import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "spy_momentum_cpu_experiment.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("spy_momentum_cpu_experiment", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_adapter(tmp_path, closes=None):
    database = tmp_path / "spy.sqlite"
    database.parent.mkdir(parents=True, exist_ok=True)
    dates = pd.bdate_range("2020-01-01", periods=32, tz="UTC")
    closes = closes if closes is not None else np.arange(100.0, 132.0)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE adapter_metadata (key text primary key, value text not null)")
        connection.executemany(
            "INSERT INTO adapter_metadata VALUES (?, ?)",
            [("price_basis", "total_return_adjusted"), ("timeframe", "1day")],
        )
        connection.execute(
            "CREATE TABLE ohlcv_data (ticker text, timestamp integer, open real, high real, low real, close real, volume integer, timeframe text)"
        )
        connection.execute(
            "CREATE TABLE ohlcv_source_map (ticker text, timestamp integer, timeframe text, source_ticker text, source_as_of_date text, source_key text, source_sha256 text, alias_policy text)"
        )
        for index, date in enumerate(dates):
            timestamp = int(date.timestamp())
            close = float(closes[index])
            connection.execute(
                "INSERT INTO ohlcv_data VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("SPY", timestamp, close - 0.5, close + 1, close - 1, close, 1_000, "1day"),
            )
            connection.execute(
                "INSERT INTO ohlcv_source_map VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("SPY", timestamp, "1day", "SPY", str(date.date()), f"source/{index}", f"hash-{index}", "identity"),
            )
    return database


def _write_contract(tmp_path, database, phase="development", database_path=None, partitions=None):
    contract = {
        "phase": phase,
        "provenance": {
            "database": {
                "path": str((database_path or database).resolve()),
                "sha256": _sha256(database),
                "metadata": {"price_basis": "total_return_adjusted", "timeframe": "1day"},
            },
            "evaluator": {"path": str(SCRIPT_PATH.resolve()), "sha256": _sha256(SCRIPT_PATH)},
        },
        "freeze": {"database_sha256": _sha256(database), "evaluator_sha256": _sha256(SCRIPT_PATH)},
        "partitions": partitions or {phase: [20]},
    }
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(contract, sort_keys=True), encoding="utf-8")
    return path


def _run_cli(database, contract, phase="development", *extra_args):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--database",
            str(database),
            "--database-sha256",
            _sha256(database),
            "--contract",
            str(contract),
            "--contract-sha256",
            _sha256(contract),
            "--phase",
            phase,
            *extra_args,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _canonical_sha256(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _write_final_manifest(tmp_path, contract, database, evaluator_sha256=None):
    freeze = json.loads(contract.read_text(encoding="utf-8"))["freeze"]
    manifest = {
        "sealed": True,
        "phase": "final",
        "bindings": {
            "contract_sha256": _sha256(contract),
            "database_sha256": _sha256(database),
            "evaluator_sha256": evaluator_sha256 or _sha256(SCRIPT_PATH),
            "freeze_sha256": _canonical_sha256(freeze),
        },
    }
    path = tmp_path / "sealed.json"
    path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return path


def test_feature_return_uses_only_rows_at_or_before_formation(tmp_path):
    experiment = _load_module()
    database = _write_adapter(tmp_path)
    rows = experiment.load_spy_rows(database, _sha256(database))

    before = experiment.feature_return(rows, 20)
    rows.loc[21:, "close"] = 1_000_000

    assert experiment.feature_return(rows, 20) == before == pytest.approx(0.2)


def test_label_is_next_open_through_five_sessions_later(tmp_path):
    experiment = _load_module()
    database = _write_adapter(tmp_path)
    rows = experiment.load_spy_rows(database, _sha256(database))

    block = experiment.build_blocks(rows, [20])[0]

    assert block.feature_position == 20
    assert block.entry_position == 21
    assert block.exit_position == 25
    assert block.label_return == pytest.approx(rows.loc[25, "open"] / rows.loc[21, "open"] - 1)


def test_future_discontinuity_does_not_remove_a_known_label(tmp_path):
    experiment = _load_module()
    closes = np.arange(100.0, 132.0)
    closes[25] = 1_000.0
    database = _write_adapter(tmp_path, closes)
    rows = experiment.load_spy_rows(database, _sha256(database))

    assert len(experiment.build_blocks(rows, [20])) == 1


def test_candidate_and_baseline_share_block_prices_dates_and_cost_rate(tmp_path):
    experiment = _load_module()
    database = _write_adapter(tmp_path)
    rows = experiment.load_spy_rows(database, _sha256(database))
    block = experiment.build_blocks(rows, [20])[0]

    result = experiment.evaluate_blocks(
        rows, [block], experiment.require_phase_access("development"), cost_bps=10
    )[0]

    assert result["candidate"]["entry_position"] == result["baseline"]["entry_position"] == 21
    assert result["candidate"]["exit_position"] == result["baseline"]["exit_position"] == 25
    assert result["candidate"]["entry_open"] == result["baseline"]["entry_open"]
    assert result["candidate"]["exit_open"] == result["baseline"]["exit_open"]
    assert result["candidate"]["cost_bps_per_side"] == result["baseline"]["cost_bps_per_side"] == 10
    assert result["candidate"]["net_return"] == result["baseline"]["net_return"]


def test_outcome_evaluation_refuses_unverified_phase_context(tmp_path):
    experiment = _load_module()
    database = _write_adapter(tmp_path)
    rows = experiment.load_spy_rows(database, _sha256(database))
    block = experiment.build_blocks(rows, [20])[0]

    with pytest.raises(ValueError, match="verified phase context"):
        experiment.evaluate_blocks(rows, [block])


def test_cli_rejects_contract_database_provenance_mismatch(tmp_path):
    database = _write_adapter(tmp_path)
    other_database = _write_adapter(tmp_path / "other")
    contract = _write_contract(tmp_path, database, database_path=other_database)

    result = _run_cli(database, contract)

    assert result.returncode != 0
    assert "contract provenance mismatch" in result.stderr


def test_final_cli_requires_manifest_bound_to_contract_database_code_and_freeze(tmp_path):
    database = _write_adapter(tmp_path)
    contract = _write_contract(tmp_path, database, phase="final")
    manifest = _write_final_manifest(tmp_path, contract, database, evaluator_sha256="wrong")

    result = _run_cli(
        database,
        contract,
        "final",
        "--sealed-manifest",
        str(manifest),
        "--sealed-manifest-sha256",
        _sha256(manifest),
    )

    assert result.returncode != 0
    assert "final manifest binding mismatch" in result.stderr


@pytest.mark.parametrize("column,value", [("open", None), ("high", float("nan")), ("low", float("inf")), ("close", 0)])
def test_load_rejects_missing_or_nonfinite_ohlc_prices(tmp_path, column, value):
    experiment = _load_module()
    database = _write_adapter(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute(f"UPDATE ohlcv_data SET {column} = ? WHERE rowid = 1", (value,))

    with pytest.raises(ValueError, match="finite positive OHLC"):
        experiment.load_spy_rows(database, _sha256(database))


def test_load_rejects_absent_source_mapping_and_malformed_metadata(tmp_path):
    experiment = _load_module()
    database = _write_adapter(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM ohlcv_source_map WHERE rowid = 1")

    with pytest.raises(ValueError, match="source hashes required"):
        experiment.load_spy_rows(database, _sha256(database))

    database = _write_adapter(tmp_path / "malformed")
    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM adapter_metadata WHERE key = 'price_basis'")

    with pytest.raises(ValueError, match="total-return price basis required"):
        experiment.load_spy_rows(database, _sha256(database))


def test_cli_runs_interval_purge_and_embargo_checks_from_contract_blocks(tmp_path):
    database = _write_adapter(tmp_path)
    contract = _write_contract(tmp_path, database, partitions={"development": [20], "selection": [26]})

    result = _run_cli(database, contract)

    assert result.returncode != 0
    assert "embargo boundary leakage" in result.stderr


def test_cli_rejects_phase_and_hash_mismatch(tmp_path):
    database = _write_adapter(tmp_path)
    contract = _write_contract(tmp_path, database, phase="selection")

    phase_mismatch = _run_cli(database, contract)
    assert phase_mismatch.returncode != 0
    assert "contract phase mismatch" in phase_mismatch.stderr

    hash_mismatch = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--database",
            str(database),
            "--database-sha256",
            "wrong",
            "--contract",
            str(contract),
            "--contract-sha256",
            _sha256(contract),
            "--phase",
            "selection",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert hash_mismatch.returncode != 0
    assert "contract provenance mismatch" in hash_mismatch.stderr


def test_cli_final_integrity_output_is_deterministically_bound(tmp_path):
    database = _write_adapter(tmp_path)
    contract = _write_contract(tmp_path, database, phase="final")
    manifest = _write_final_manifest(tmp_path, contract, database)
    arguments = ("final", "--sealed-manifest", str(manifest), "--sealed-manifest-sha256", _sha256(manifest))

    first = _run_cli(database, contract, *arguments)
    second = _run_cli(database, contract, *arguments)

    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout


def test_load_rejects_non_monotonic_timestamps(tmp_path):
    experiment = _load_module()
    database = _write_adapter(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE ohlcv_data SET timestamp = 0 WHERE rowid = 32")

    with pytest.raises(ValueError, match="unique and monotonic"):
        experiment.load_spy_rows(database, _sha256(database))


def test_partition_blocks_reject_overlapping_label_intervals(tmp_path):
    experiment = _load_module()
    database = _write_adapter(tmp_path)
    rows = experiment.load_spy_rows(database, _sha256(database))
    development, selection = experiment.build_blocks(rows, [20, 22])

    with pytest.raises(ValueError, match="overlap"):
        experiment.assert_partition_isolation({"development": [development], "selection": [selection]})

    with pytest.raises(ValueError, match="overlap"):
        experiment.assert_partition_isolation({"selection": [development, selection]})


def test_five_session_purge_and_embargo_reject_boundary_leakage():
    experiment = _load_module()

    with pytest.raises(ValueError, match="purge"):
        experiment.assert_purge(20, [25], required_sessions=5)
    with pytest.raises(ValueError, match="embargo"):
        experiment.assert_embargo(20, [25], required_sessions=5)
    experiment.assert_purge(20, [26], required_sessions=5)
    experiment.assert_embargo(20, [26], required_sessions=5)


def test_final_phase_requires_a_matching_sealed_manifest(tmp_path):
    experiment = _load_module()

    with pytest.raises(ValueError, match="sealed manifest"):
        experiment.require_phase_access("final")

    manifest = tmp_path / "sealed.json"
    manifest.write_text(json.dumps({"sealed": True, "phase": "final"}), encoding="utf-8")
    experiment.require_phase_access("final", manifest, _sha256(manifest))


def test_bootstrap_interval_is_deterministic_for_a_fixed_seed():
    experiment = _load_module()
    differences = np.array([0.01, -0.02, 0.03, 0.01, -0.01, 0.02])

    assert experiment.moving_block_interval(differences, seed=42, samples=100) == experiment.moving_block_interval(
        differences, seed=42, samples=100
    )


def test_source_database_connection_is_read_only(tmp_path, monkeypatch):
    experiment = _load_module()
    database = _write_adapter(tmp_path)
    original_connect = sqlite3.connect
    seen = []

    def recording_connect(*args, **kwargs):
        seen.append((args, kwargs))
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(experiment.sqlite3, "connect", recording_connect)
    experiment.load_spy_rows(database, _sha256(database))

    assert "mode=ro" in seen[0][0][0]
    assert seen[0][1]["uri"] is True
