use std::io::Write;
use std::path::PathBuf;
use std::process::{Command, Stdio};

use serde_json::{Value, json};
use vesper_ratatui_console::contract::{ConsoleSnapshot, Envelope, Message};

const CONTROL_HASH: &str = "7c222fb2927d828af22f592134e8932480637c0d1a3a6c9f5d6f0f975f6e3f43";
const CATALOG: [(&str, &str); 31] = [
    ("note.add", "NoteAddPayload"),
    ("alert.dismiss", "AlertDismissPayload"),
    ("layout.reset", "LayoutResetPayload"),
    ("approval.approve", "ApprovalPayload"),
    ("approval.hold", "ApprovalPayload"),
    ("approval.reject", "ApprovalPayload"),
    ("approval.rework", "ApprovalReworkPayload"),
    ("agent.send-message", "AgentMessagePayload"),
    ("agent.enqueue", "AgentEnqueuePayload"),
    ("agent.pause", "AgentWorkPayload"),
    ("agent.stop", "AgentStopPayload"),
    ("agent.retry", "AgentWorkPayload"),
    ("agent.set-priority", "AgentPriorityPayload"),
    ("risk.propose-limit", "RiskLimitPayload"),
    ("trading.pause", "EmptyPayload"),
    ("trading.emergency-stop", "EmptyPayload"),
    ("service.pause", "ServicePayload"),
    ("service.restart", "ServicePayload"),
    ("runtime.start", "RuntimeStartPayload"),
    ("runtime.stop-safe", "EmptyPayload"),
    ("runtime.stop-force", "EmptyPayload"),
    ("runtime.prepare-shutdown", "EmptyPayload"),
    ("mode.switch", "ModeSwitchPayload"),
    ("mode.leave-live", "ModeSwitchPayload"),
    ("mode.enable-live", "EnableLivePayload"),
    ("model.request-promotion", "ModelDecisionPayload"),
    ("model.request-rollback", "ModelDecisionPayload"),
    ("memory.compress-now", "CompressMemoryPayload"),
    ("backup.create", "BackupCreatePayload"),
    ("backup.restore", "BackupRestorePayload"),
    ("source-control.push", "SourceControlPushPayload"),
];

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|path| path.parent())
        .expect("repo root")
        .to_path_buf()
}

fn valid_payload(command: &str) -> Value {
    match command {
        "note.add" => {
            json!({"target_type":"stock","target_id":"AAPL","body":"Review concentration.","visibility":"private"})
        }
        "alert.dismiss" => {
            json!({"alert_id":"alert:1","created_at_utc":"2026-08-03T00:00:00Z"})
        }
        "layout.reset" => json!({"screen":"impact"}),
        "approval.approve" | "approval.hold" | "approval.reject" => {
            json!({"run_id":"run:1","checkpoint_id":"checkpoint:1"})
        }
        "approval.rework" => {
            json!({"run_id":"run:1","checkpoint_id":"checkpoint:1","evidence_ids":["evidence:1"]})
        }
        "agent.send-message" => {
            json!({"agent_id":"agent:risk","text":"Review this.","selected_entity_type":"stock","selected_entity_id":"AAPL"})
        }
        "agent.enqueue" => {
            json!({"agent_id":"agent:risk","title":"Review risk","objective":"Review evidence.","priority":75})
        }
        "agent.pause" | "agent.retry" => json!({"work_id":"work:1"}),
        "agent.stop" => json!({"work_id":"work:1","workflow_run_id":"workflow:1"}),
        "agent.set-priority" => json!({"work_id":"work:1","priority":90}),
        "risk.propose-limit" => {
            json!({"limit_id":"limit:1","proposed_value":"0.05","evidence_ids":["evidence:1"]})
        }
        "trading.pause"
        | "trading.emergency-stop"
        | "runtime.stop-safe"
        | "runtime.stop-force"
        | "runtime.prepare-shutdown" => json!({}),
        "service.pause" | "service.restart" => json!({"service_id":"service:qwen"}),
        "runtime.start" => json!({"mode":"paper","activation_receipt_id":"receipt:1"}),
        "mode.switch" => json!({"target_mode":"shadow"}),
        "mode.leave-live" => json!({"target_mode":"paper"}),
        "mode.enable-live" => json!({"desired_portfolio_id":"portfolio:1"}),
        "model.request-promotion" | "model.request-rollback" => {
            json!({"candidate_id":"candidate:1","evidence_ids":["evidence:1"]})
        }
        "memory.compress-now" => json!({"agent_id":"agent:risk"}),
        "backup.create" => json!({"destination":"C:\\backups\\v20.zip"}),
        "backup.restore" => {
            json!({"archive":"C:\\backups\\v20.zip","preview_hash":CONTROL_HASH,"safety_backup_receipt_id":"receipt:backup"})
        }
        "source-control.push" => {
            json!({"expected_revision":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"})
        }
        _ => panic!("unknown test command"),
    }
}

fn command_envelope(command: &str, payload: Value) -> Value {
    let reason = match command {
        "note.add"
        | "alert.dismiss"
        | "layout.reset"
        | "agent.send-message"
        | "memory.compress-now" => Value::Null,
        "approval.approve" | "backup.create" => Value::Null,
        _ => json!("Required rationale"),
    };
    json!({
        "schema_version":1,
        "message_id":"client:1",
        "sequence":1,
        "state_version":0,
        "timestamp_utc":"2026-08-03T00:00:00Z",
        "message_type":"command",
        "payload":{"request":{
            "command_id":format!("client-1:{command}"),
            "command_type":command,
            "reviewed_control_version":19,
            "reviewed_control_hash":CONTROL_HASH,
            "reason":reason,
            "confirmation":null,
            "payload":payload
        }}
    })
}

#[test]
fn controls_snapshot_has_exact_order_and_models() {
    let fixture =
        std::fs::read(repo_root().join("TUI testing/contracts/v1/controls_snapshot.json"))
            .expect("controls snapshot fixture");
    let snapshot: ConsoleSnapshot = serde_json::from_slice(&fixture).expect("strict snapshot");
    let actual: Vec<_> = snapshot
        .command_specs
        .iter()
        .map(|spec| (spec.command_type.as_str(), spec.payload_model.as_str()))
        .collect();
    assert_eq!(actual, CATALOG);
    for spec in &snapshot.command_specs {
        assert_eq!(spec.command_type.as_str(), spec.capability_id.as_str());
    }
}

#[test]
fn every_command_binds_to_its_exact_typed_payload() {
    for (command, model) in CATALOG {
        let envelope: Envelope =
            serde_json::from_value(command_envelope(command, valid_payload(command)))
                .unwrap_or_else(|error| panic!("{command}: {error}"));
        let Message::Command(payload) = envelope.message else {
            panic!("command message");
        };
        assert_eq!(payload.request.command_type.as_str(), command);
        assert_eq!(payload.request.payload.model_name(), model);
    }
}

#[test]
fn wrong_payload_pair_operator_and_secret_fields_are_rejected() {
    let wrong = command_envelope("note.add", valid_payload("alert.dismiss"));
    assert!(serde_json::from_value::<Envelope>(wrong).is_err());

    for (location, key) in [
        ("request", "operator_id"),
        ("payload", "password"),
        ("payload", "token"),
        ("payload", "api_key"),
        ("payload", "credential"),
        ("payload", "secret"),
        ("payload", "account_id"),
    ] {
        let mut value = command_envelope("note.add", valid_payload("note.add"));
        let request = value["payload"]["request"].as_object_mut().unwrap();
        if location == "request" {
            request.insert(key.to_owned(), json!("forbidden"));
        } else {
            request["payload"]
                .as_object_mut()
                .unwrap()
                .insert(key.to_owned(), json!("forbidden"));
        }
        assert!(serde_json::from_value::<Envelope>(value).is_err(), "{key}");
    }
}

#[test]
fn payload_over_64_kib_is_rejected() {
    let mut payload = valid_payload("note.add");
    payload["unknown"] = json!("x".repeat(65_536));
    assert!(serde_json::from_value::<Envelope>(command_envelope("note.add", payload)).is_err());
}

#[test]
fn command_receipt_is_strict_and_round_trips() {
    let value = json!({
        "schema_version":1,"message_id":"server:1","sequence":1,"state_version":0,
        "timestamp_utc":"2026-08-03T00:00:01Z","message_type":"command-receipt",
        "payload":{"receipt":{"command_id":"client:command:1","status":"completed",
        "code":"completed","safe_message":"Note stored.","accepted_at_utc":"2026-08-03T00:00:00Z",
        "finished_at_utc":"2026-08-03T00:00:01Z","result":null}}
    });
    let envelope: Envelope = serde_json::from_value(value.clone()).expect("strict receipt");
    assert_eq!(serde_json::to_value(envelope).unwrap(), value);
    let mut invalid = value;
    invalid["payload"]["receipt"]["operator_id"] = json!("spoofed");
    assert!(serde_json::from_value::<Envelope>(invalid).is_err());
}

#[test]
fn python_and_rust_accept_the_same_command_corpus() {
    let mut corpus: Vec<Value> = CATALOG
        .iter()
        .map(|(command, _)| command_envelope(command, valid_payload(command)))
        .collect();
    corpus.push(command_envelope("note.add", valid_payload("alert.dismiss")));
    let mut operator = command_envelope("note.add", valid_payload("note.add"));
    operator["payload"]["request"]["operator_id"] = json!("spoofed");
    corpus.push(operator);
    let mut oversized = valid_payload("note.add");
    oversized["unknown"] = json!("x".repeat(65_536));
    corpus.push(command_envelope("note.add", oversized));

    let rust: Vec<bool> = corpus
        .iter()
        .map(|value| serde_json::from_value::<Envelope>(value.clone()).is_ok())
        .collect();
    assert_eq!(rust, python_acceptance(&corpus));
    assert!(rust[..31].iter().all(|accepted| *accepted));
    assert!(rust[31..].iter().all(|accepted| !accepted));
}

#[test]
fn python_and_rust_match_all_command_boundary_values() {
    let mut corpus = Vec::new();

    let mut body_max = valid_payload("note.add");
    body_max["body"] = json!("x".repeat(8_000));
    corpus.push(command_envelope("note.add", body_max.clone()));
    body_max["body"] = json!("x".repeat(8_001));
    corpus.push(command_envelope("note.add", body_max));

    let mut entity_max = valid_payload("agent.send-message");
    entity_max["selected_entity_type"] = json!("x".repeat(512));
    corpus.push(command_envelope("agent.send-message", entity_max.clone()));
    entity_max["selected_entity_type"] = json!("x".repeat(513));
    corpus.push(command_envelope("agent.send-message", entity_max));

    let mut reason_max = command_envelope("approval.reject", valid_payload("approval.reject"));
    reason_max["payload"]["request"]["reason"] = json!("x".repeat(2_000));
    corpus.push(reason_max.clone());
    reason_max["payload"]["request"]["reason"] = json!("x".repeat(2_001));
    corpus.push(reason_max);

    let mut typed_max = command_envelope("mode.enable-live", valid_payload("mode.enable-live"));
    typed_max["payload"]["request"]["confirmation"] = json!({"typed_text":"x".repeat(512)});
    corpus.push(typed_max.clone());
    typed_max["payload"]["request"]["confirmation"] = json!({"typed_text":"x".repeat(513)});
    corpus.push(typed_max);

    let mut evidence_max = valid_payload("approval.rework");
    evidence_max["evidence_ids"] = json!(
        (0..32)
            .map(|index| format!("e:{index}"))
            .collect::<Vec<_>>()
    );
    corpus.push(command_envelope("approval.rework", evidence_max.clone()));
    evidence_max["evidence_ids"] = json!(
        (0..33)
            .map(|index| format!("e:{index}"))
            .collect::<Vec<_>>()
    );
    corpus.push(command_envelope("approval.rework", evidence_max));

    let mut path_max = valid_payload("backup.create");
    path_max["destination"] = json!("x".repeat(32_767));
    corpus.push(command_envelope("backup.create", path_max.clone()));
    path_max["destination"] = json!("x".repeat(32_768));
    corpus.push(command_envelope("backup.create", path_max));

    let mut priority = valid_payload("agent.enqueue");
    priority["priority"] = json!(100);
    corpus.push(command_envelope("agent.enqueue", priority.clone()));
    priority["priority"] = json!(101);
    corpus.push(command_envelope("agent.enqueue", priority.clone()));
    priority["priority"] = json!(-1);
    corpus.push(command_envelope("agent.enqueue", priority));

    let mut decimal = valid_payload("risk.propose-limit");
    decimal["proposed_value"] = json!("1".repeat(128));
    corpus.push(command_envelope("risk.propose-limit", decimal.clone()));
    decimal["proposed_value"] = json!("1".repeat(129));
    corpus.push(command_envelope("risk.propose-limit", decimal));

    let mut identifier = valid_payload("alert.dismiss");
    identifier["alert_id"] = json!(format!("a{}", "x".repeat(127)));
    corpus.push(command_envelope("alert.dismiss", identifier.clone()));
    identifier["alert_id"] = json!(format!("a{}", "x".repeat(128)));
    corpus.push(command_envelope("alert.dismiss", identifier));

    let mut revision = valid_payload("source-control.push");
    revision["expected_revision"] = json!("a".repeat(64));
    corpus.push(command_envelope("source-control.push", revision.clone()));
    revision["expected_revision"] = json!("a".repeat(39));
    corpus.push(command_envelope("source-control.push", revision.clone()));
    revision["expected_revision"] = json!("A".repeat(40));
    corpus.push(command_envelope("source-control.push", revision));

    let mut version = command_envelope("note.add", valid_payload("note.add"));
    version["payload"]["request"]["reviewed_control_version"] = json!(u64::MAX);
    corpus.push(version.clone());
    version["payload"]["request"]["reviewed_control_version"] = json!(-1);
    corpus.push(version);

    let mut forbidden_reason = command_envelope("note.add", valid_payload("note.add"));
    forbidden_reason["payload"]["request"]["reason"] = json!("not allowed");
    corpus.push(forbidden_reason);

    let rust: Vec<bool> = corpus
        .iter()
        .map(|value| serde_json::from_value::<Envelope>(value.clone()).is_ok())
        .collect();
    assert_eq!(rust, python_acceptance(&corpus));
    assert_eq!(
        rust,
        vec![
            true, false, true, false, true, false, true, false, true, false, true, false, true,
            false, false, true, false, true, false, true, false, false, true, false, false,
        ]
    );
}

fn python_acceptance(corpus: &[Value]) -> Vec<bool> {
    let script = r#"import json, sys
from pydantic import ValidationError
from vesper.platform.tui.contracts import WireEnvelope, decode_payload
out = []
for value in json.load(sys.stdin):
    try:
        envelope = WireEnvelope.model_validate_json(json.dumps(value, separators=(',', ':')))
        decode_payload(envelope)
        out.append(True)
    except (ValidationError, TypeError, ValueError):
        out.append(False)
json.dump(out, sys.stdout, separators=(',', ':'))
"#;
    let mut child = Command::new("uv")
        .current_dir(repo_root())
        .args(["run", "--locked", "python", "-c", script])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .expect("start Python parity process");
    child
        .stdin
        .take()
        .expect("Python stdin")
        .write_all(&serde_json::to_vec(corpus).unwrap())
        .expect("write corpus");
    let output = child.wait_with_output().expect("Python parity output");
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    serde_json::from_slice(&output.stdout).expect("Python acceptance vector")
}
