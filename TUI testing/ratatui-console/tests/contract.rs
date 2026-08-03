use std::io::Write;
use std::path::PathBuf;
use std::process::{Command, Stdio};

use serde_json::Value;
use vesper_ratatui_console::contract::Envelope;

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .expect("crate is nested two levels under the repository")
        .to_path_buf()
}

struct PythonContractBundle {
    fixtures: Vec<Vec<u8>>,
    descriptor: Vec<u8>,
}

fn python_contract_bundle() -> PythonContractBundle {
    let script = r#"import base64, json
from vesper.platform.tui.contracts import CANONICAL_WIRE_FIXTURES, WIRE_CONTRACT_DESCRIPTOR
print(json.dumps({
    'fixtures': [base64.b64encode(value).decode('ascii') for value in CANONICAL_WIRE_FIXTURES],
    'descriptor': base64.b64encode(WIRE_CONTRACT_DESCRIPTOR).decode('ascii'),
}, separators=(',', ':')))
"#;
    let output = Command::new("uv")
        .current_dir(repo_root())
        .args(["run", "--locked", "python", "-c", script])
        .output()
        .expect("run Python receipt producer");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let receipt: Value = serde_json::from_slice(&output.stdout).expect("receipt JSON");
    PythonContractBundle {
        fixtures: receipt["fixtures"]
            .as_array()
            .expect("fixture list")
            .iter()
            .map(|value| decode_base64(value.as_str().expect("fixture string")))
            .collect(),
        descriptor: decode_base64(receipt["descriptor"].as_str().expect("descriptor string")),
    }
}

fn decode_base64(value: &str) -> Vec<u8> {
    fn digit(byte: u8) -> u8 {
        match byte {
            b'A'..=b'Z' => byte - b'A',
            b'a'..=b'z' => byte - b'a' + 26,
            b'0'..=b'9' => byte - b'0' + 52,
            b'+' => 62,
            b'/' => 63,
            _ => panic!("invalid base64"),
        }
    }
    let mut decoded = Vec::new();
    for chunk in value.as_bytes().chunks(4) {
        let a = digit(chunk[0]) as u32;
        let b = digit(chunk[1]) as u32;
        let c = if chunk[2] == b'=' {
            0
        } else {
            digit(chunk[2]) as u32
        };
        let d = if chunk[3] == b'=' {
            0
        } else {
            digit(chunk[3]) as u32
        };
        let bits = (a << 18) | (b << 12) | (c << 6) | d;
        decoded.push((bits >> 16) as u8);
        if chunk[2] != b'=' {
            decoded.push((bits >> 8) as u8);
        }
        if chunk[3] != b'=' {
            decoded.push(bits as u8);
        }
    }
    decoded
}

#[test]
fn consumes_all_python_fixtures_and_contract_descriptor_byte_for_byte() {
    let bundle = python_contract_bundle();
    assert_eq!(bundle.fixtures.len(), 14);
    let mut seen = Vec::new();
    for fixture in bundle.fixtures {
        let envelope: Envelope =
            serde_json::from_slice(&fixture).expect("Python fixture parses in Rust");
        seen.push(envelope.message_type());
        assert_eq!(serde_json::to_vec(&envelope).unwrap(), fixture);
    }
    seen.sort_by_key(|value| value.to_string());
    seen.dedup();
    assert_eq!(seen.len(), 14);
    assert_eq!(rust_contract_descriptor(), bundle.descriptor);
}

fn rust_contract_descriptor() -> Vec<u8> {
    let descriptor = serde_json::json!({
        "envelope_required": ["schema_version", "message_id", "sequence", "state_version", "timestamp_utc", "message_type", "payload"],
        "integer_fields": ["envelope.sequence", "envelope.state_version", "snapshot.state_version", "header.agent_queue_length"],
        "messages": {
            "auth-result": ["success", "access_state", "reason"],
            "auth-setup": ["password", "confirmation"],
            "auth-unlock": ["password"],
            "client-hello": ["client_version", "supported_schema_versions"],
            "lease-request": ["action"],
            "lease-result": ["status", "reason"],
            "lock-request": ["action"],
            "lock-result": ["locked"],
            "ping": ["nonce"],
            "pong": ["nonce"],
            "protocol-error": ["code", "safe_message"],
            "server-hello": ["server_version", "requires_setup"],
            "snapshot": ["snapshot"],
            "snapshot-request": [],
        },
        "nullable_required": [
            "auth-result.reason", "lease-result.reason", "snapshot.alerts",
            "alert.resolved_at_utc", "header.operating_mode_reason",
            "header.data_age_seconds", "header.regime_confidence", "header.portfolio_value",
            "header.next_rebalance_at_utc", "header.rebalance_blockers", "header.active_agent",
            "header.agent_queue_length", "header.qwen_context_percent"
        ],
        "optional_default": ["capability.reason"],
        "schema_version": 1,
        "shell_required": {
            "alert": ["alert_id", "severity", "summary", "created_at_utc", "resolved_at_utc"],
            "capability": ["capability_id", "state"],
            "header": [
                "operating_mode", "operating_mode_freshness", "operating_mode_reason", "data_freshness",
                "data_age_seconds", "regime_label", "regime_confidence", "portfolio_value",
                "next_rebalance_at_utc", "rebalance_blockers", "active_agent", "agent_queue_length",
                "qwen_state", "qwen_context_percent", "current_time_utc", "market_session"
            ],
            "snapshot": ["state_version", "generated_at_utc", "header", "alerts", "capabilities"]
        }
    });
    serde_json::to_vec(&descriptor).unwrap()
}

fn python_acceptance(corpus: &[Value]) -> Vec<bool> {
    let script = r#"import json, sys
from pydantic import ValidationError
from vesper.platform.tui.contracts import WireEnvelope, decode_payload
result = []
for value in json.load(sys.stdin):
    try:
        envelope = WireEnvelope.model_validate_json(json.dumps(value, separators=(',', ':')))
        decode_payload(envelope)
        result.append(True)
    except (ValidationError, TypeError, ValueError):
        result.append(False)
json.dump(result, sys.stdout, separators=(',', ':'))
"#;
    let mut child = Command::new("uv")
        .current_dir(repo_root())
        .args(["run", "--locked", "python", "-c", script])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .expect("run Python differential validator");
    child
        .stdin
        .take()
        .unwrap()
        .write_all(&serde_json::to_vec(corpus).unwrap())
        .unwrap();
    let output = child.wait_with_output().unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    serde_json::from_slice(&output.stdout).unwrap()
}

#[test]
fn differential_corpus_matches_python_for_required_unknown_and_ranges() {
    let bundle = python_contract_bundle();
    let mut corpus: Vec<Value> = bundle
        .fixtures
        .iter()
        .map(|fixture| serde_json::from_slice(fixture).unwrap())
        .collect();
    let valid = corpus.clone();
    for source in &valid {
        for field in [
            "schema_version",
            "message_id",
            "sequence",
            "state_version",
            "timestamp_utc",
            "message_type",
            "payload",
        ] {
            let mut value = source.clone();
            value.as_object_mut().unwrap().remove(field);
            corpus.push(value);
        }
        let mut unknown = source.clone();
        unknown
            .as_object_mut()
            .unwrap()
            .insert("unknown".into(), Value::Bool(true));
        corpus.push(unknown);
        let mut payload_unknown = source.clone();
        payload_unknown["payload"]
            .as_object_mut()
            .unwrap()
            .insert("unknown".into(), Value::Bool(true));
        corpus.push(payload_unknown);
        for field in source["payload"].as_object().unwrap().keys() {
            let mut value = source.clone();
            value["payload"].as_object_mut().unwrap().remove(field);
            corpus.push(value);
        }
    }
    for (index, source) in valid.iter().enumerate() {
        let mut mismatched = source.clone();
        mismatched["payload"] = valid[(index + 1) % valid.len()]["payload"].clone();
        corpus.push(mismatched);
    }
    let snapshot = valid
        .iter()
        .find(|value| value["message_type"] == "snapshot")
        .unwrap();
    for (path, fields) in [
        (
            &["payload", "snapshot"][..],
            &[
                "state_version",
                "generated_at_utc",
                "header",
                "alerts",
                "capabilities",
            ][..],
        ),
        (
            &["payload", "snapshot", "header"][..],
            &[
                "operating_mode",
                "operating_mode_freshness",
                "operating_mode_reason",
                "data_freshness",
                "data_age_seconds",
                "regime_label",
                "regime_confidence",
                "portfolio_value",
                "next_rebalance_at_utc",
                "rebalance_blockers",
                "active_agent",
                "agent_queue_length",
                "qwen_state",
                "qwen_context_percent",
                "current_time_utc",
                "market_session",
            ][..],
        ),
    ] {
        for field in fields {
            let mut value = snapshot.clone();
            let mut target = &mut value;
            for part in path {
                target = &mut target[*part];
            }
            target.as_object_mut().unwrap().remove(*field);
            corpus.push(value);
        }
    }
    for (path, fields) in [
        (
            &["payload", "snapshot", "alerts", "0"][..],
            &[
                "alert_id",
                "severity",
                "summary",
                "created_at_utc",
                "resolved_at_utc",
            ][..],
        ),
        (
            &["payload", "snapshot", "capabilities", "0"][..],
            &["capability_id", "state", "reason"][..],
        ),
    ] {
        for field in fields {
            let mut value = snapshot.clone();
            let mut target = &mut value;
            for part in path {
                target = if let Ok(index) = part.parse::<usize>() {
                    &mut target[index]
                } else {
                    &mut target[*part]
                };
            }
            target.as_object_mut().unwrap().remove(*field);
            corpus.push(value);
        }
    }
    for field in ["sequence", "state_version"] {
        for number in [
            serde_json::json!(-1),
            serde_json::json!(u64::MAX),
            serde_json::json!("18446744073709551616"),
        ] {
            let mut value = valid[0].clone();
            value[field] = if number.is_string() {
                serde_json::from_str(number.as_str().unwrap()).unwrap()
            } else {
                number
            };
            corpus.push(value);
        }
    }
    for (path, number) in [
        (
            &["payload", "snapshot", "state_version"][..],
            serde_json::json!(-1),
        ),
        (
            &["payload", "snapshot", "state_version"][..],
            serde_json::json!(u64::MAX),
        ),
        (
            &["payload", "snapshot", "state_version"][..],
            serde_json::from_str("18446744073709551616").unwrap(),
        ),
        (
            &["payload", "snapshot", "header", "agent_queue_length"][..],
            serde_json::json!(-1),
        ),
        (
            &["payload", "snapshot", "header", "agent_queue_length"][..],
            serde_json::json!(u64::MAX),
        ),
        (
            &["payload", "snapshot", "header", "agent_queue_length"][..],
            serde_json::from_str("18446744073709551616").unwrap(),
        ),
    ] {
        let mut value = snapshot.clone();
        let (last, parents) = path.split_last().unwrap();
        let mut target = &mut value;
        for part in parents {
            target = &mut target[*part];
        }
        target[*last] = number;
        corpus.push(value);
    }
    let python = python_acceptance(&corpus);
    let rust: Vec<bool> = corpus
        .iter()
        .map(|value| serde_json::from_value::<Envelope>(value.clone()).is_ok())
        .collect();
    let mismatches: Vec<_> = rust
        .iter()
        .zip(&python)
        .enumerate()
        .filter(|(_, (rust, python))| rust != python)
        .map(|(index, (rust, python))| (index, *rust, *python, &corpus[index]))
        .collect();
    assert!(mismatches.is_empty(), "{mismatches:#?}");
}

#[test]
fn rejects_unknown_contract_field() {
    let json = r#"{"schema_version":1,"unknown":true}"#;
    assert!(serde_json::from_str::<Envelope>(json).is_err());
}

#[test]
fn rejects_wrong_schema_negative_versions_and_invalid_ids() {
    let fixture = python_contract_bundle().fixtures[1].clone();
    let text = String::from_utf8(fixture).unwrap();
    for bad in [
        text.replace("\"schema_version\":1", "\"schema_version\":2"),
        text.replace("\"sequence\":1", "\"sequence\":-1"),
        text.replace("\"state_version\":0", "\"state_version\":-1"),
        text.replace("\"server:1\"", "\"..\""),
        text.replace(
            "\"requires_setup\":true",
            "\"requires_setup\":true,\"unknown\":1",
        ),
    ] {
        assert!(
            serde_json::from_str::<Envelope>(&bad).is_err(),
            "accepted {bad}"
        );
    }
}

#[test]
fn parses_all_fourteen_strict_payloads() {
    let samples = [
        (
            "client-hello",
            r#"{"client_version":"0.1.0","supported_schema_versions":[1]}"#,
        ),
        (
            "server-hello",
            r#"{"server_version":"0.1.0","requires_setup":false}"#,
        ),
        ("auth-setup", r#"{"password":"p","confirmation":"p"}"#),
        ("auth-unlock", r#"{"password":"p"}"#),
        (
            "auth-result",
            r#"{"success":true,"access_state":"viewer","reason":null}"#,
        ),
        ("lease-request", r#"{"action":"take-control"}"#),
        ("lease-result", r#"{"status":"controller","reason":null}"#),
        ("lock-request", r#"{"action":"lock"}"#),
        ("lock-result", r#"{"locked":true}"#),
        ("snapshot-request", r#"{}"#),
        (
            "snapshot",
            r#"{"snapshot":{"state_version":0,"generated_at_utc":"2026-08-03T00:00:00Z","header":{"operating_mode":"unknown","operating_mode_freshness":"unavailable","operating_mode_reason":null,"data_freshness":"unavailable","data_age_seconds":null,"regime_label":"Unavailable","regime_confidence":null,"portfolio_value":null,"next_rebalance_at_utc":null,"rebalance_blockers":null,"active_agent":null,"agent_queue_length":null,"qwen_state":"Unavailable","qwen_context_percent":null,"current_time_utc":"2026-08-03T00:00:00Z","market_session":"Unavailable"},"alerts":null,"capabilities":[]}}"#,
        ),
        (
            "protocol-error",
            r#"{"code":"locked","safe_message":"Locked."}"#,
        ),
        ("ping", r#"{"nonce":"n:1"}"#),
        ("pong", r#"{"nonce":"n:1"}"#),
    ];
    for (message_type, payload) in samples {
        let wire = format!(
            r#"{{"schema_version":1,"message_id":"id:1","sequence":0,"state_version":0,"timestamp_utc":"2026-08-03T00:00:00Z","message_type":"{message_type}","payload":{payload}}}"#
        );
        assert!(
            serde_json::from_str::<Envelope>(&wire).is_ok(),
            "failed {message_type}"
        );
    }
}

#[test]
fn rejects_non_utc_timestamp_and_non_finite_or_coerced_numbers() {
    let fixture = python_contract_bundle().fixtures[1].clone();
    let text = String::from_utf8(fixture).unwrap();
    assert!(serde_json::from_str::<Envelope>(&text.replace("Z\"", "-04:00\"")).is_err());
    assert!(
        serde_json::from_str::<Envelope>(&text.replace("\"sequence\":1", "\"sequence\":1.0"))
            .is_err()
    );
    assert!(serde_json::from_str::<Envelope>(&text.replace("true", "NaN")).is_err());
}

#[test]
fn matches_python_literal_and_string_constraints() {
    let base = r#"{"schema_version":1,"message_id":"id:1","sequence":0,"state_version":0,"timestamp_utc":"2026-08-03T00:00:00Z","message_type":"MESSAGE","payload":PAYLOAD}"#;
    for (message_type, payload) in [
        (
            "client-hello",
            r#"{"client_version":"","supported_schema_versions":[1]}"#,
        ),
        (
            "client-hello",
            r#"{"client_version":"ok","supported_schema_versions":[2]}"#,
        ),
        (
            "server-hello",
            r#"{"server_version":"   ","requires_setup":true}"#,
        ),
        ("auth-unlock", r#"{"password":""}"#),
        ("lock-result", r#"{"locked":false}"#),
        ("protocol-error", r#"{"code":"ok","safe_message":""}"#),
    ] {
        let wire = base
            .replace("MESSAGE", message_type)
            .replace("PAYLOAD", payload);
        assert!(
            serde_json::from_str::<Envelope>(&wire).is_err(),
            "accepted {message_type}: {payload}"
        );
    }
}

#[test]
fn normalizes_zero_offset_timestamp_to_python_z_form() {
    let fixture = python_contract_bundle().fixtures[1].clone();
    let wire = String::from_utf8(fixture)
        .unwrap()
        .replace("00:00:00Z", "00:00:00+00:00");
    let envelope: Envelope = serde_json::from_str(&wire).unwrap();
    assert!(
        String::from_utf8(serde_json::to_vec(&envelope).unwrap())
            .unwrap()
            .contains("00:00:00Z")
    );
}

#[test]
fn rejects_dates_python_would_reject_and_redacts_password_debug() {
    let fixture = python_contract_bundle().fixtures[1].clone();
    let text = String::from_utf8(fixture).unwrap();
    for invalid in [
        "2026-13-03T00:00:00Z",
        "2026-02-30T00:00:00Z",
        "2026-08-03T24:00:00Z",
    ] {
        assert!(
            serde_json::from_str::<Envelope>(&text.replace("2026-08-03T00:00:00Z", invalid))
                .is_err()
        );
    }
    let auth: Envelope = serde_json::from_str(
        r#"{"schema_version":1,"message_id":"auth:1","sequence":1,"state_version":0,"timestamp_utc":"2026-08-03T00:00:00Z","message_type":"auth-unlock","payload":{"password":"do-not-print"}}"#,
    )
    .unwrap();
    let debug = format!("{auth:?}");
    assert!(!debug.contains("do-not-print"));
    assert!(debug.contains("redacted"));
}
