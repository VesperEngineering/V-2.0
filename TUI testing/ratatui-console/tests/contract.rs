use std::path::PathBuf;
use std::process::Command;

use serde_json::Value;
use vesper_ratatui_console::contract::{Envelope, Message, MessageType};

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .expect("crate is nested two levels under the repository")
        .to_path_buf()
}

fn python_receipts() -> (Vec<u8>, Vec<u8>) {
    let script = r#"import base64, json
from vesper.platform.tui.contracts import CANONICAL_WIRE_FIXTURE, WIRE_SCHEMA_RECEIPT
print(json.dumps({
    'fixture': base64.b64encode(CANONICAL_WIRE_FIXTURE).decode('ascii'),
    'schema': base64.b64encode(WIRE_SCHEMA_RECEIPT).decode('ascii'),
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
    (
        decode_base64(receipt["fixture"].as_str().expect("fixture string")),
        decode_base64(receipt["schema"].as_str().expect("schema string")),
    )
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
fn consumes_python_fixture_and_schema_receipt_byte_for_byte() {
    let (fixture, schema_receipt) = python_receipts();
    let envelope: Envelope =
        serde_json::from_slice(&fixture).expect("Python fixture parses in Rust");
    assert_eq!(envelope.message_type(), MessageType::ServerHello);
    assert!(matches!(envelope.message, Message::ServerHello(_)));
    assert_eq!(serde_json::to_vec(&envelope).unwrap(), fixture);

    let schema: Value =
        serde_json::from_slice(&schema_receipt).expect("Python schema receipt parses");
    assert_eq!(serde_json::to_vec(&schema).unwrap(), schema_receipt);
    let properties = schema["properties"]
        .as_object()
        .expect("envelope properties");
    for name in [
        "schema_version",
        "message_id",
        "sequence",
        "state_version",
        "timestamp_utc",
        "message_type",
        "payload",
    ] {
        assert!(properties.contains_key(name), "missing schema field {name}");
    }
}

#[test]
fn rejects_unknown_contract_field() {
    let json = r#"{"schema_version":1,"unknown":true}"#;
    assert!(serde_json::from_str::<Envelope>(json).is_err());
}

#[test]
fn rejects_wrong_schema_negative_versions_and_invalid_ids() {
    let (fixture, _) = python_receipts();
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
    let (fixture, _) = python_receipts();
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
    let (fixture, _) = python_receipts();
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
    let (fixture, _) = python_receipts();
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
