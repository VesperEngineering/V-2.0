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
AVAILABILITY_FREEZE = "2020-12-31T00:00:00+00:00"


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
    closes = closes if closes is not None else np.arange(100.0, 160.0)
    dates = pd.bdate_range("2020-01-01", periods=len(closes), tz="UTC")
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
    tmp_path.mkdir(parents=True, exist_ok=True)
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
        "freeze": {
            "database_sha256": _sha256(database),
            "evaluator_sha256": _sha256(SCRIPT_PATH),
            "availability_freeze": AVAILABILITY_FREEZE,
        },
        "partitions": partitions or {
            "development": {"development": [20]},
            "selection": {"development": [20], "selection": [31]},
            "final": {"development": [20], "selection": [31], "final": [42]},
        }[phase],
        "partition_definition": {
            "development_through": "2020-01-29",
            "formation_cadence_sessions": 5,
            "label_horizon_sessions": 5,
            "purge_and_embargo_sessions": 5,
            "selection_from": "2020-02-13",
            "final_from": "2020-02-28",
        },
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
    rows = experiment.load_spy_rows(database, _sha256(database), AVAILABILITY_FREEZE)

    before = experiment.feature_return(rows, 20)
    rows.loc[21:, "close"] = 1_000_000

    assert experiment.feature_return(rows, 20) == before == pytest.approx(0.2)


def test_baseline_label_is_next_open_through_five_sessions_later(tmp_path):
    experiment = _load_module()
    database = _write_adapter(tmp_path)
    contract = _write_contract(tmp_path, database)
    rows = experiment.load_spy_rows(database, _sha256(database), AVAILABILITY_FREEZE)
    result = experiment.evaluate_phase_outcomes(
        "development",
        contract_path=contract,
        contract_sha256=_sha256(contract),
        database=database,
        database_sha256=_sha256(database),
        cost_bps=0,
    )[0]

    assert result["baseline"]["entry_position"] == 21
    assert result["baseline"]["exit_position"] == 25
    assert result["baseline"]["net_return"] == pytest.approx(rows.loc[25, "open"] / rows.loc[21, "open"] - 1)


def test_future_discontinuity_does_not_remove_a_known_label(tmp_path):
    experiment = _load_module()
    closes = np.arange(100.0, 132.0)
    closes[25] = 1_000.0
    database = _write_adapter(tmp_path, closes)
    rows = experiment.load_spy_rows(database, _sha256(database), AVAILABILITY_FREEZE)

    assert len(experiment.build_blocks(rows, [20])) == 1


def test_candidate_and_baseline_share_block_prices_dates_and_cost_rate(tmp_path):
    experiment = _load_module()
    database = _write_adapter(tmp_path)
    contract = _write_contract(tmp_path, database)

    result = experiment.evaluate_phase_outcomes(
        "development",
        contract_path=contract,
        contract_sha256=_sha256(contract),
        database=database,
        database_sha256=_sha256(database),
        cost_bps=10,
    )[0]

    assert result["candidate"]["entry_position"] == result["baseline"]["entry_position"] == 21
    assert result["candidate"]["exit_position"] == result["baseline"]["exit_position"] == 25
    assert result["candidate"]["entry_open"] == result["baseline"]["entry_open"]
    assert result["candidate"]["exit_open"] == result["baseline"]["exit_open"]
    assert result["candidate"]["cost_bps_per_side"] == result["baseline"]["cost_bps_per_side"] == 10
    assert result["candidate"]["net_return"] == result["baseline"]["net_return"]


def test_atomic_outcome_entrypoint_prevents_cross_database_row_substitution(tmp_path):
    experiment = _load_module()
    database = _write_adapter(tmp_path / "authorized")
    other_database = _write_adapter(tmp_path / "other", closes=np.arange(200.0, 232.0))
    contract = _write_contract(tmp_path, database)

    assert not hasattr(experiment, "require_phase_access")
    assert not hasattr(experiment, "evaluate_blocks")

    outcomes = experiment.evaluate_phase_outcomes(
        "development",
        contract_path=contract,
        contract_sha256=_sha256(contract),
        database=database,
        database_sha256=_sha256(database),
    )
    assert len(outcomes) == 1
    assert "rows" not in outcomes[0]

    with pytest.raises(ValueError, match="contract provenance mismatch"):
        experiment.evaluate_phase_outcomes(
            "development",
            contract_path=contract,
            contract_sha256=_sha256(contract),
            database=other_database,
            database_sha256=_sha256(other_database),
        )


@pytest.mark.parametrize(
    "mutated_input,expected_error",
    [("contract", "contract changed during evaluation"), ("database", "database changed during evaluation")],
)
def test_atomic_outcomes_reject_contract_or_database_toctou(tmp_path, monkeypatch, mutated_input, expected_error):
    experiment = _load_module()
    database = _write_adapter(tmp_path)
    contract = _write_contract(tmp_path, database)
    original_build = experiment.build_partition_blocks

    def mutate_after_build(rows, contract_data, phase):
        blocks = original_build(rows, contract_data, phase)
        if mutated_input == "contract":
            contract.write_text(contract.read_text(encoding="utf-8") + " ", encoding="utf-8")
        else:
            with sqlite3.connect(database) as connection:
                connection.execute("UPDATE ohlcv_data SET close = close + 1 WHERE rowid = 32")
        return blocks

    monkeypatch.setattr(experiment, "build_partition_blocks", mutate_after_build)

    with pytest.raises(ValueError, match=expected_error):
        experiment.evaluate_phase_outcomes(
            "development",
            contract_path=contract,
            contract_sha256=_sha256(contract),
            database=database,
            database_sha256=_sha256(database),
        )


def test_self_sealed_tampered_final_contract_never_authorizes_outcomes(tmp_path):
    experiment = _load_module()
    database = _write_adapter(tmp_path)
    contract = _write_contract(tmp_path, database, phase="final", partitions={"final": [21]})
    manifest = _write_final_manifest(tmp_path, contract, database)

    with pytest.raises(ValueError, match="external final approval required"):
        experiment.evaluate_phase_outcomes(
            "final",
            contract_path=contract,
            contract_sha256=_sha256(contract),
            database=database,
            database_sha256=_sha256(database),
            sealed_manifest=manifest,
            expected_sha256=_sha256(manifest),
        )


def test_atomic_outcome_api_exposes_no_reusable_authority_or_row_inputs(tmp_path):
    experiment = _load_module()
    database = _write_adapter(tmp_path)
    contract = _write_contract(tmp_path, database)

    assert not hasattr(experiment, "require_phase_access")
    assert not hasattr(experiment, "evaluate_blocks")
    assert not hasattr(experiment, "_VerifiedPhase")
    assert not hasattr(experiment, "_PHASE_CAPABILITY")
    assert not hasattr(experiment, "_verify_phase_integrity")
    assert not hasattr(experiment, "_evaluate_blocks")
    assert not hasattr(experiment, "_net_return")
    assert not hasattr(experiment.Block, "label_return")
    assert experiment.evaluate_phase_outcomes.__closure__ is None

    with pytest.raises(TypeError, match="unexpected keyword argument 'rows'"):
        experiment.evaluate_phase_outcomes(
            "development",
            contract_path=contract,
            contract_sha256=_sha256(contract),
            database=database,
            database_sha256=_sha256(database),
            rows=pd.DataFrame(),
        )


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
        experiment.load_spy_rows(database, _sha256(database), AVAILABILITY_FREEZE)


def test_load_rejects_absent_or_malformed_source_mapping_and_metadata(tmp_path):
    experiment = _load_module()
    database = _write_adapter(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM ohlcv_source_map WHERE rowid = 1")

    with pytest.raises(ValueError, match="source mapping required"):
        experiment.load_spy_rows(database, _sha256(database), AVAILABILITY_FREEZE)

    database = _write_adapter(tmp_path / "malformed-source-map")
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE ohlcv_source_map SET source_ticker = NULL, source_as_of_date = NULL, source_key = NULL WHERE rowid = 1"
        )

    with pytest.raises(ValueError, match="source mapping required"):
        experiment.load_spy_rows(database, _sha256(database), AVAILABILITY_FREEZE)

    database = _write_adapter(tmp_path / "malformed-metadata")
    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM adapter_metadata WHERE key = 'price_basis'")

    with pytest.raises(ValueError, match="total-return price basis required"):
        experiment.load_spy_rows(database, _sha256(database), AVAILABILITY_FREEZE)


def test_cli_runs_interval_purge_and_embargo_checks_from_contract_blocks(tmp_path):
    experiment = _load_module()
    database = _write_adapter(tmp_path)
    contract = _write_contract(tmp_path, database, phase="selection", partitions={"development": [20], "selection": [26]})
    contract_data = json.loads(contract.read_text())
    contract_data["partition_definition"]["selection_from"] = "2020-02-06"
    contract.write_text(json.dumps(contract_data), encoding="utf-8")
    rows = experiment.load_spy_rows(database, _sha256(database), AVAILABILITY_FREEZE)

    with pytest.raises(ValueError, match="embargo boundary leakage"):
        experiment.assert_partition_purge_and_embargo(experiment.build_partition_blocks(rows, json.loads(contract.read_text()), "selection"))


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
        experiment.load_spy_rows(database, _sha256(database), AVAILABILITY_FREEZE)


def test_partition_blocks_reject_overlapping_label_intervals(tmp_path):
    experiment = _load_module()
    database = _write_adapter(tmp_path)
    rows = experiment.load_spy_rows(database, _sha256(database), AVAILABILITY_FREEZE)
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


def test_final_phase_requires_complete_matching_sealed_manifest_bindings(tmp_path):
    experiment = _load_module()
    database = _write_adapter(tmp_path)
    contract = _write_contract(tmp_path, database, phase="final")
    manifest = _write_final_manifest(tmp_path, contract, database)

    with pytest.raises(ValueError, match="complete sealed-manifest bindings"):
        experiment.evaluate_phase_outcomes(
            "final",
            contract_path=contract,
            contract_sha256=_sha256(contract),
            database=database,
            database_sha256=_sha256(database),
            sealed_manifest=manifest,
        )

    with pytest.raises(ValueError, match="external final approval required"):
        experiment.evaluate_phase_outcomes(
            "final",
            contract_path=contract,
            contract_sha256=_sha256(contract),
            database=database,
            database_sha256=_sha256(database),
            sealed_manifest=manifest,
            expected_sha256=_sha256(manifest),
        )


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
    experiment.load_spy_rows(database, _sha256(database), AVAILABILITY_FREEZE)

    assert "mode=ro" in seen[0][0][0]
    assert seen[0][1]["uri"] is True


def test_cli_denies_self_authored_selection_contract_before_data_access(tmp_path):
    database = _write_adapter(tmp_path)
    contract = _write_contract(tmp_path, database, phase="selection")

    result = _run_cli(database, contract, "selection")

    assert result.returncode != 0
    assert "selection approval anchor required" in result.stderr


def test_cli_rejects_vacuous_partition_declaration(tmp_path):
    database = _write_adapter(tmp_path)
    contract = _write_contract(tmp_path, database, partitions={"development": [20]})
    contract_data = json.loads(contract.read_text(encoding="utf-8"))
    del contract_data["partition_definition"]
    contract.write_text(json.dumps(contract_data), encoding="utf-8")

    result = _run_cli(database, contract)

    assert result.returncode != 0
    assert "complete chronological partition declaration required" in result.stderr


@pytest.mark.parametrize("source_as_of_date", ["not-a-date", "2019-12-31", "2027-01-01"])
def test_load_rejects_malformed_or_temporally_invalid_source_availability(tmp_path, source_as_of_date):
    experiment = _load_module()
    database = _write_adapter(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE ohlcv_source_map SET source_as_of_date = ?", (source_as_of_date,))

    with pytest.raises(ValueError, match="source availability"):
        experiment.load_spy_rows(database, _sha256(database), AVAILABILITY_FREEZE)


def test_cli_receipt_changes_when_bound_database_changes(tmp_path):
    first_database = _write_adapter(tmp_path / "first")
    second_database = _write_adapter(tmp_path / "second", closes=np.arange(200.0, 232.0))
    first_contract = _write_contract(tmp_path / "first-contract", first_database)
    second_contract = _write_contract(tmp_path / "second-contract", second_database)

    first = _run_cli(first_database, first_contract)
    second = _run_cli(second_database, second_contract)

    assert first.returncode == second.returncode == 0
    assert json.loads(first.stdout)["bindings"]["database_sha256"] != json.loads(second.stdout)["bindings"]["database_sha256"]
    assert json.loads(first.stdout)["output_sha256"] != json.loads(second.stdout)["output_sha256"]


def test_final_cli_rejects_missing_selection_predecessor_and_unordered_boundaries(tmp_path):
    database = _write_adapter(tmp_path, closes=np.arange(100.0, 160.0))
    contract = _write_contract(tmp_path, database, phase="final", partitions={"development": [20], "final": [42]})
    manifest = _write_final_manifest(tmp_path, contract, database)

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
    assert "complete chronological partition declaration required" in result.stderr


def test_five_session_cadence_is_accepted_in_cli_and_outcome_paths(tmp_path):
    experiment = _load_module()
    database = _write_adapter(tmp_path)
    contract = _write_contract(tmp_path, database, partitions={"development": [20, 25]})
    contract_data = json.loads(contract.read_text(encoding="utf-8"))
    contract_data["partition_definition"]["formation_cadence_sessions"] = 5
    contract_data["partition_definition"]["development_through"] = "2020-02-05"
    contract.write_text(json.dumps(contract_data), encoding="utf-8")

    outcomes = experiment.evaluate_phase_outcomes(
        "development",
        contract_path=contract,
        contract_sha256=_sha256(contract),
        database=database,
        database_sha256=_sha256(database),
    )
    result = _run_cli(database, contract)

    assert [outcome["baseline"]["entry_position"] for outcome in outcomes] == [21, 26]
    assert result.returncode == 0


@pytest.mark.parametrize("path", ["cli", "outcome"])
def test_development_label_crossing_selection_boundary_is_rejected(tmp_path, path):
    experiment = _load_module()
    database = _write_adapter(tmp_path)
    contract = _write_contract(tmp_path, database)
    contract_data = json.loads(contract.read_text(encoding="utf-8"))
    contract_data["partition_definition"]["selection_from"] = "2020-01-30"
    contract_data["partition_definition"]["final_from"] = "2020-02-14"
    contract.write_text(json.dumps(contract_data), encoding="utf-8")

    if path == "cli":
        result = _run_cli(database, contract)
        assert result.returncode != 0
        assert "development partition date mismatch" in result.stderr
    else:
        with pytest.raises(ValueError, match="development partition date mismatch"):
            experiment.evaluate_phase_outcomes(
                "development",
                contract_path=contract,
                contract_sha256=_sha256(contract),
                database=database,
                database_sha256=_sha256(database),
            )


def test_final_cli_rejects_selection_label_crossing_final_boundary(tmp_path):
    database = _write_adapter(tmp_path)
    contract = _write_contract(
        tmp_path,
        database,
        phase="final",
        partitions={"development": [20], "selection": [31], "final": [42]},
    )
    contract_data = json.loads(contract.read_text(encoding="utf-8"))
    contract_data["partition_definition"]["selection_from"] = "2020-02-06"
    contract_data["partition_definition"]["final_from"] = "2020-02-14"
    contract.write_text(json.dumps(contract_data), encoding="utf-8")
    manifest = _write_final_manifest(tmp_path, contract, database)

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
    assert "selection partition date mismatch" in result.stderr


@pytest.mark.parametrize("path", ["cli", "outcome"])
def test_missing_contract_availability_freeze_is_rejected(tmp_path, path):
    experiment = _load_module()
    database = _write_adapter(tmp_path)
    contract = _write_contract(tmp_path, database)
    contract_data = json.loads(contract.read_text(encoding="utf-8"))
    del contract_data["freeze"]["availability_freeze"]
    contract.write_text(json.dumps(contract_data), encoding="utf-8")

    if path == "cli":
        result = _run_cli(database, contract)
        assert result.returncode != 0
        assert "contract availability freeze required" in result.stderr
    else:
        with pytest.raises(ValueError, match="contract availability freeze required"):
            experiment.evaluate_phase_outcomes(
                "development",
                contract_path=contract,
                contract_sha256=_sha256(contract),
                database=database,
                database_sha256=_sha256(database),
            )


def test_receipt_integrity_rechecks_admitted_input_bytes_before_emission(tmp_path):
    experiment = _load_module()
    database = _write_adapter(tmp_path)
    contract = _write_contract(tmp_path, database)
    contract_sha256 = _sha256(contract)
    contract.write_text(contract.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(ValueError, match="contract changed before receipt"):
        experiment._verify_receipt_input_hashes(
            contract,
            contract_sha256,
            database,
            _sha256(database),
            None,
            None,
        )


@pytest.mark.parametrize(
    "partitions,definition_change,expected_error",
    [
        ({"development": [20], "selection": [31], "final": [42]}, ("final_from", "2020-02-13"), "complete chronological partition declaration required"),
        ({"development": [20], "selection": [31], "final": [41]}, None, "final partition date mismatch"),
    ],
)
def test_final_cli_rejects_overlapping_boundaries_and_out_of_boundary_formations(tmp_path, partitions, definition_change, expected_error):
    database = _write_adapter(tmp_path)
    contract = _write_contract(tmp_path, database, phase="final", partitions=partitions)
    if definition_change is not None:
        contract_data = json.loads(contract.read_text())
        contract_data["partition_definition"][definition_change[0]] = definition_change[1]
        contract.write_text(json.dumps(contract_data), encoding="utf-8")
    manifest = _write_final_manifest(tmp_path, contract, database)

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
    assert expected_error in result.stderr


@pytest.mark.parametrize("path", ["cli", "outcome"])
def test_source_availability_after_contract_freeze_is_rejected_in_executable_paths(tmp_path, path):
    experiment = _load_module()
    database = _write_adapter(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE ohlcv_source_map SET source_as_of_date = '2021-01-01'")
    contract = _write_contract(tmp_path, database)

    if path == "cli":
        result = _run_cli(database, contract)
        assert result.returncode != 0
        assert "source availability required" in result.stderr
    else:
        with pytest.raises(ValueError, match="source availability required"):
            experiment.evaluate_phase_outcomes(
                "development",
                contract_path=contract,
                contract_sha256=_sha256(contract),
                database=database,
                database_sha256=_sha256(database),
            )
