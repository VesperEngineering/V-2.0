use std::io::Write;
use std::path::PathBuf;
use std::process::{Command, Stdio};

use serde_json::Value;
use vesper_ratatui_console::contract::{
    AgentCard, ConsoleSnapshot, Envelope, EvidenceRow, MemoryRow, MessageType, ModelsView,
    RiskView, SourceRow, SystemView, TimelineRow,
};

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .expect("crate is nested two levels under the repository")
        .to_path_buf()
}

fn shared_snapshot_fixture() -> Vec<u8> {
    let mut bytes = std::fs::read(
        repo_root().join("TUI testing/contracts/v1/console_snapshot_empty_command_specs.json"),
    )
    .expect("read shared snapshot fixture");
    while bytes.last().is_some_and(u8::is_ascii_whitespace) {
        bytes.pop();
    }
    bytes
}

fn event_presentation() -> Value {
    let snapshot: Value = serde_json::from_slice(&shared_snapshot_fixture()).unwrap();
    let screen_meta = |name: &str| {
        serde_json::json!({
            "freshness": snapshot[name]["freshness"].clone(),
            "as_of_utc": snapshot[name]["as_of_utc"].clone(),
            "source": snapshot[name]["source"].clone(),
            "error": snapshot[name]["error"].clone(),
        })
    };
    serde_json::json!({
        "generated_at_utc": snapshot["shell"]["generated_at_utc"].clone(),
        "header": snapshot["shell"]["header"].clone(),
        "control_version": snapshot["control_version"].clone(),
        "control_hash": snapshot["control_hash"].clone(),
        "window_omissions": snapshot["window_omissions"].clone(),
        "impact": screen_meta("impact"),
        "portfolio": screen_meta("portfolio"),
        "orders": screen_meta("orders"),
        "agents": screen_meta("agents"),
        "models": screen_meta("models"),
        "timeline": screen_meta("timeline"),
        "risk": screen_meta("risk"),
        "data": screen_meta("data"),
        "memory": screen_meta("memory"),
        "system": screen_meta("system"),
        "portfolio_rank_source": snapshot["portfolio"]["rank_source"].clone(),
        "timeline_hidden_event_count": snapshot["timeline"]["hidden_event_count"].clone(),
        "model_active_model_id": snapshot["models"]["active_model_id"].clone(),
        "model_rollback_model_id": snapshot["models"]["rollback_model_id"].clone(),
        "model_approved_family": snapshot["models"]["approved_family"].clone(),
        "model_approved_strategy": snapshot["models"]["approved_strategy"].clone(),
        "model_approved_feature_set_id": snapshot["models"]["approved_feature_set_id"].clone(),
        "model_final_regime": snapshot["models"]["final_regime"].clone(),
        "model_final_regime_confidence": snapshot["models"]["final_regime_confidence"].clone(),
        "model_regime_state": snapshot["models"]["regime_state"].clone(),
        "model_automatic_changes_blocked": snapshot["models"]["automatic_changes_blocked"].clone(),
        "model_block_reason": snapshot["models"]["block_reason"].clone(),
        "model_gates": snapshot["models"]["gates"].clone(),
        "risk_blocked_actions": snapshot["risk"]["blocked_actions"].clone(),
        "risk_circuit_breaker": snapshot["risk"]["circuit_breaker"].clone(),
        "system_qwen": snapshot["system"]["qwen"].clone(),
        "system_health": snapshot["system"]["health"].clone(),
    })
}

fn event_envelope(entity_type: &str, entity_id: &str, entity: Value, targets: &[&str]) -> Value {
    serde_json::json!({
        "schema_version": 1,
        "message_id": "server:1",
        "sequence": 1,
        "state_version": 1,
        "timestamp_utc": "2026-08-03T00:00:00Z",
        "message_type": "event",
        "payload": {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "operation": "upsert",
            "entity": entity,
            "targets": targets,
            "presentation": event_presentation(),
        }
    })
}

#[test]
fn consumes_shared_console_snapshot_fixture_byte_for_byte() {
    let fixture = shared_snapshot_fixture();
    let snapshot: ConsoleSnapshot = serde_json::from_slice(&fixture).expect("strict snapshot");

    assert!(snapshot.command_specs.is_empty());
    assert_eq!(serde_json::to_vec(&snapshot).unwrap(), fixture);
    assert!(fixture.len() < 1_048_576);
}

#[test]
fn agent_detail_and_timeline_links_are_strict_and_percentage_bounded() {
    let card = serde_json::json!({
        "work_id": "work:deep",
        "agent": "portfolio-research",
        "title": "Review exposure",
        "stage": "running",
        "priority": 90,
        "urgent": true,
        "elapsed_seconds": 12.5,
        "model": "qwen:64k",
        "affected_areas": ["portfolio", "risk"],
        "session_id": "session:deep",
        "plan_steps": ["Inspect positions", "Write evidence"],
        "activity": [{
            "activity_id": "activity:1",
            "kind": "tool",
            "summary": "Read current positions.",
            "occurred_at_utc": "2026-08-04T12:00:00Z",
            "evidence_ids": ["evidence:1"]
        }],
        "evidence_ids": ["evidence:1"],
        "context_percent": 80.0,
        "chat_agent_id": "agent:portfolio",
        "detail_next_cursor": "cursor:2"
    });
    let parsed: AgentCard = serde_json::from_value(card.clone()).expect("deep agent card");
    assert_eq!(parsed.session_id.unwrap().as_str(), "session:deep");
    assert_eq!(parsed.activity.len(), 1);
    assert_eq!(parsed.context_percent, Some(80.0));

    for invalid_percent in [-0.1, 100.1] {
        let mut invalid = card.clone();
        invalid["context_percent"] = serde_json::json!(invalid_percent);
        assert!(serde_json::from_value::<AgentCard>(invalid).is_err());
    }
    let mut unknown_activity_field = card.clone();
    unknown_activity_field["activity"][0]["private_reasoning"] = serde_json::json!("hidden");
    assert!(serde_json::from_value::<AgentCard>(unknown_activity_field).is_err());

    let timeline: TimelineRow = serde_json::from_value(serde_json::json!({
        "event_id": "event:deep",
        "occurred_at_utc": "2026-08-04T12:00:00Z",
        "impact": true,
        "severity": "active",
        "summary": "Work affected the portfolio.",
        "agent_id": "agent:portfolio",
        "symbol": "AAPL",
        "model_id": null,
        "approval_id": null,
        "order_id": null,
        "work_id": "work:deep",
        "evidence_ids": ["evidence:1"]
    }))
    .expect("timeline work link");
    assert_eq!(timeline.work_id.unwrap().as_str(), "work:deep");
}

#[test]
fn model_summary_candidates_and_gates_are_direct_strict_contract_fields() {
    let models = serde_json::json!({
        "freshness": "fresh",
        "as_of_utc": "2026-08-04T12:00:00Z",
        "source": "controller",
        "error": null,
        "active_model_id": "model:active",
        "rollback_model_id": "model:rollback",
        "approved_family": "approved-family",
        "approved_strategy": "ml_model",
        "approved_feature_set_id": "features:approved",
        "final_regime": "risk-on",
        "final_regime_confidence": 0.75,
        "regime_state": "decided",
        "automatic_changes_blocked": false,
        "block_reason": null,
        "opinions": [],
        "candidates": [{
            "candidate_id": "candidate:1",
            "family": "approved-family",
            "strategy": "ml_model",
            "status": "evaluating",
            "evidence_ids": ["evidence:1"],
            "created_at_utc": "2026-08-04T11:00:00Z",
            "feature_set_id": "features:approved",
            "data_identity": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "evaluation_contract": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "status_reason": "Evaluation is running.",
            "status_at_utc": "2026-08-04T12:00:00Z"
        }],
        "gates": [{
            "gate_id": "gate:1",
            "candidate_id": "candidate:1",
            "metric_id": "metric:sharpe",
            "candidate_value": 1.2,
            "baseline_value": 1.0,
            "comparison": "gte",
            "threshold": 1.1,
            "evaluation_window": "2025-01-01 through 2025-12-31",
            "state": "pass",
            "reason": "Candidate cleared the threshold.",
            "evidence_ids": ["evidence:1"]
        }],
        "metrics": [],
        "evidence": []
    });
    let parsed: ModelsView = serde_json::from_value(models.clone()).expect("deep model view");
    assert_eq!(parsed.final_regime.unwrap().as_str(), "risk-on");
    assert_eq!(parsed.gates.len(), 1);

    let mut invalid_confidence = models.clone();
    invalid_confidence["final_regime_confidence"] = serde_json::json!(1.01);
    assert!(serde_json::from_value::<ModelsView>(invalid_confidence).is_err());

    for missing in ["final_regime", "final_regime_confidence"] {
        let mut invalid_decided = models.clone();
        invalid_decided[missing] = Value::Null;
        assert!(serde_json::from_value::<ModelsView>(invalid_decided).is_err());
    }
    for blocked_state in ["uncertain", "unavailable"] {
        let mut invalid_block = models.clone();
        invalid_block["regime_state"] = serde_json::json!(blocked_state);
        invalid_block["automatic_changes_blocked"] = serde_json::json!(false);
        invalid_block["block_reason"] = Value::Null;
        assert!(serde_json::from_value::<ModelsView>(invalid_block).is_err());
    }
    let mut unknown_gate_field = models;
    unknown_gate_field["gates"][0]["inferred"] = serde_json::json!(true);
    assert!(serde_json::from_value::<ModelsView>(unknown_gate_field).is_err());
}

#[test]
fn risk_data_evidence_and_memory_deep_fields_are_closed_contracts() {
    let risk = serde_json::json!({
        "freshness": "fresh",
        "as_of_utc": "2026-08-04T12:00:00Z",
        "source": "controller",
        "error": null,
        "limits": [{
            "limit_id": "limit:concentration",
            "current_value": "0.10",
            "proposed_value": "0.08",
            "status": "pending",
            "proposal_reason": "Reduce concentration.",
            "review_state": "pending",
            "evidence_ids": ["evidence:1"]
        }],
        "approvals": [{
            "approval_id": "approval:1",
            "run_id": "run:1",
            "checkpoint_id": "checkpoint:1",
            "state": "pending",
            "reason": "Review required.",
            "evidence_ids": ["evidence:1"],
            "requested_at_utc": "2026-08-04T12:00:00Z",
            "affected_symbols": ["AAPL"],
            "weight_changes": [{
                "symbol": "AAPL",
                "current_weight": 0.10,
                "proposed_weight": 0.08
            }],
            "risks": ["Concentration remains elevated."],
            "expected_consequences": ["Future risk is lower."],
            "basis_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
            "stale_reason": null
        }],
        "alerts": [],
        "metrics": [],
        "blocked_actions": [{
            "action_id": "action:1",
            "action": "Submit rebalance",
            "reason": "Approval is pending.",
            "affected_symbols": ["AAPL"],
            "created_at_utc": "2026-08-04T12:00:00Z"
        }],
        "circuit_breaker": {
            "state": "armed",
            "reason": "No trip condition is active.",
            "observed_at_utc": "2026-08-04T12:00:00Z"
        }
    });
    let parsed: RiskView = serde_json::from_value(risk.clone()).expect("deep risk view");
    assert_eq!(parsed.blocked_actions.len(), 1);
    assert_eq!(parsed.approvals[0].weight_changes.len(), 1);
    let mut stale_without_reason = risk;
    stale_without_reason["approvals"][0]["state"] = serde_json::json!("stale");
    stale_without_reason["approvals"][0]["stale_reason"] = Value::Null;
    assert!(serde_json::from_value::<RiskView>(stale_without_reason).is_err());

    let source: SourceRow = serde_json::from_value(serde_json::json!({
        "source_id": "source:massive",
        "freshness": "fresh",
        "as_of_utc": "2026-08-04T12:00:00Z",
        "age_seconds": 1.0,
        "coverage": "S&P 500",
        "error": null,
        "consumers": ["ml_model"],
        "dependencies": ["Massive SQLite snapshot"]
    }))
    .expect("source dependencies");
    assert_eq!(source.dependencies.len(), 1);

    let evidence_value = serde_json::json!({
        "evidence_id": "evidence:1",
        "evidence_type": "receipt",
        "source": "controller",
        "created_at_utc": "2026-08-04T12:00:00Z",
        "sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
        "symbols": ["AAPL"],
        "agent_ids": ["agent:portfolio"],
        "model_ids": ["model:active"],
        "order_ids": ["order:1"],
        "approval_ids": ["approval:1"],
        "source_ids": ["source:massive"],
        "raw_log_id": "log:1",
        "raw_log_excerpt": ["Validated row 1."],
        "raw_log_truncated": true,
        "raw_log_next_cursor": "cursor:2"
    });
    let evidence: EvidenceRow =
        serde_json::from_value(evidence_value.clone()).expect("linked evidence");
    assert_eq!(evidence.symbols.len(), 1);
    assert!(evidence.raw_log_truncated);
    let mut too_many_excerpt_lines = serde_json::to_value(&evidence).unwrap();
    too_many_excerpt_lines["raw_log_excerpt"] = serde_json::json!(
        (0..51)
            .map(|index| format!("line {index}"))
            .collect::<Vec<_>>()
    );
    assert!(serde_json::from_value::<EvidenceRow>(too_many_excerpt_lines).is_err());
    for metadata_field in [
        "raw_log_excerpt",
        "raw_log_truncated",
        "raw_log_next_cursor",
    ] {
        let mut orphaned_metadata = evidence_value.clone();
        orphaned_metadata["raw_log_id"] = Value::Null;
        orphaned_metadata["raw_log_excerpt"] = serde_json::json!([]);
        orphaned_metadata["raw_log_truncated"] = serde_json::json!(false);
        orphaned_metadata["raw_log_next_cursor"] = Value::Null;
        if metadata_field == "raw_log_excerpt" {
            orphaned_metadata["raw_log_excerpt"] = serde_json::json!(["orphaned"]);
        } else if metadata_field == "raw_log_truncated" {
            orphaned_metadata["raw_log_truncated"] = serde_json::json!(true);
        } else {
            orphaned_metadata["raw_log_next_cursor"] = serde_json::json!("cursor:orphaned");
        }
        assert!(
            serde_json::from_value::<EvidenceRow>(orphaned_metadata).is_err(),
            "{metadata_field} requires raw_log_id"
        );
    }

    let memory: MemoryRow = serde_json::from_value(serde_json::json!({
        "memory_id": "memory:1",
        "status": "core",
        "summary": "Use controller truth.",
        "evidence_ids": ["evidence:1"],
        "updated_at_utc": "2026-08-04T12:00:00Z",
        "used_by_agents": ["agent:portfolio"],
        "change_reason": "Repeatedly useful evidence."
    }))
    .expect("memory usage and reason");
    assert_eq!(memory.used_by_agents.len(), 1);
}

#[test]
fn system_qwen_repository_and_health_fields_are_strict_and_percentage_bounded() {
    let mut snapshot: Value = serde_json::from_slice(&shared_snapshot_fixture()).unwrap();
    snapshot["system"]["qwen"] = serde_json::json!({
        "state": "busy",
        "loaded_model": "qwen:64k",
        "current_agent": "agent:portfolio",
        "queue_length": 2,
        "context_percent": 80.0,
        "last_inference_ms": 125.0,
        "observed_at_utc": "2026-08-04T12:00:00Z",
        "error": null
    });
    snapshot["system"]["health"] = serde_json::json!([
        {
            "component": "backup",
            "state": "healthy",
            "reason": "Latest backup verified.",
            "observed_at_utc": "2026-08-04T12:00:00Z",
            "checks": [{
                "check_id": "check:backup",
                "state": "pass",
                "reason": "Manifest matched."
            }],
            "broker_actions_blocked": false
        },
        {
            "component": "recovery",
            "state": "healthy",
            "reason": "Recovery evidence is current.",
            "observed_at_utc": "2026-08-04T12:00:00Z",
            "checks": [],
            "broker_actions_blocked": false
        },
        {
            "component": "notifications",
            "state": "degraded",
            "reason": "Phone delivery is not configured.",
            "observed_at_utc": null,
            "checks": [],
            "broker_actions_blocked": false
        }
    ]);
    snapshot["system"]["repositories"][0]["checks"] = serde_json::json!([{
        "check_id": "check:tests",
        "state": "running",
        "reason": "Focused tests are running.",
        "observed_at_utc": null
    }]);
    let parsed: SystemView =
        serde_json::from_value(snapshot["system"].clone()).expect("deep system view");
    assert_eq!(parsed.qwen.context_percent, Some(80.0));
    assert_eq!(parsed.health.len(), 3);
    assert_eq!(parsed.repositories[0].checks.len(), 1);

    for invalid_percent in [-0.1, 100.1] {
        let mut invalid = snapshot["system"].clone();
        invalid["qwen"]["context_percent"] = serde_json::json!(invalid_percent);
        assert!(serde_json::from_value::<SystemView>(invalid).is_err());
    }
    let mut negative_latency = snapshot["system"].clone();
    negative_latency["qwen"]["last_inference_ms"] = serde_json::json!(-1.0);
    assert!(serde_json::from_value::<SystemView>(negative_latency).is_err());

    let mut unavailable_without_error = snapshot["system"].clone();
    unavailable_without_error["qwen"]["state"] = serde_json::json!("unavailable");
    unavailable_without_error["qwen"]["error"] = Value::Null;
    assert!(serde_json::from_value::<SystemView>(unavailable_without_error).is_err());

    let mut active_without_observation = snapshot["system"].clone();
    active_without_observation["qwen"]["state"] = serde_json::json!("ready");
    active_without_observation["qwen"]["observed_at_utc"] = Value::Null;
    assert!(serde_json::from_value::<SystemView>(active_without_observation).is_err());

    let mut missing_health_component = snapshot["system"].clone();
    missing_health_component["health"]
        .as_array_mut()
        .unwrap()
        .pop();
    assert!(serde_json::from_value::<SystemView>(missing_health_component).is_err());

    let mut duplicate_health_component = snapshot["system"].clone();
    duplicate_health_component["health"][2]["component"] = serde_json::json!("backup");
    assert!(serde_json::from_value::<SystemView>(duplicate_health_component).is_err());
}

#[test]
fn managed_memory_content_wire_is_closed_bounded_and_result_exclusive() {
    let request = serde_json::json!({
        "schema_version": 1,
        "message_id": "client:2",
        "sequence": 2,
        "state_version": 7,
        "timestamp_utc": "2026-08-04T14:30:00Z",
        "message_type": "memory-content-request",
        "payload": {
            "request_id": 9,
            "memory_id": "memory:deep-archive",
            "reviewed_updated_at_utc": "2026-08-04T14:30:00Z"
        }
    });
    let parsed: Envelope = serde_json::from_value(request.clone()).expect("strict request");
    assert_eq!(parsed.message_type(), MessageType::MemoryContentRequest);

    let content = "x".repeat(100_000);
    let success = serde_json::json!({
        "schema_version": 1,
        "message_id": "server:2",
        "sequence": 2,
        "state_version": 7,
        "timestamp_utc": "2026-08-04T14:30:00Z",
        "message_type": "memory-content-result",
        "payload": {
            "request_id": 9,
            "memory_id": "memory:deep-archive",
            "reviewed_updated_at_utc": "2026-08-04T14:30:00Z",
            "status": "success",
            "content": content,
            "error": null
        }
    });
    let parsed: Envelope = serde_json::from_value(success.clone()).expect("strict success");
    assert_eq!(parsed.message_type(), MessageType::MemoryContentResult);
    assert!(serde_json::to_vec(&parsed).unwrap().len() < 1_048_576);

    let mut error = success.clone();
    error["payload"]["status"] = serde_json::json!("error");
    error["payload"]["content"] = serde_json::Value::Null;
    error["payload"]["error"] = serde_json::json!("Memory changed. Search again.");
    assert!(serde_json::from_value::<Envelope>(error).is_ok());

    let invalid = [
        {
            let mut value = request.clone();
            value["payload"]["unknown"] = serde_json::json!(true);
            value
        },
        {
            let mut value = success.clone();
            value["payload"]["content"] = serde_json::json!("x".repeat(100_001));
            value
        },
        {
            let mut value = success.clone();
            value["payload"]["content"] = serde_json::Value::Null;
            value
        },
        {
            let mut value = success.clone();
            value["payload"]["error"] = serde_json::json!("Not allowed.");
            value
        },
        {
            let mut value = success;
            value["payload"]["status"] = serde_json::json!("error");
            value["payload"]["error"] = serde_json::json!("Failed.");
            value
        },
    ];
    for value in invalid {
        assert!(serde_json::from_value::<Envelope>(value).is_err());
    }
}

#[test]
fn memory_agent_usage_reason_is_required_and_rejects_unknown_counts() {
    const REASON: &str = "No trusted memory-use source is configured.";
    let mut value: Value = serde_json::from_slice(&shared_snapshot_fixture()).unwrap();
    value["memory"]["agent_usage_error"] = serde_json::json!(REASON);

    let snapshot: ConsoleSnapshot =
        serde_json::from_value(value.clone()).expect("trusted-use reason is valid");
    assert_eq!(snapshot.memory.agent_usage_error.as_str(), REASON);

    let mut missing = value.clone();
    missing["memory"]
        .as_object_mut()
        .unwrap()
        .remove("agent_usage_error");
    assert!(serde_json::from_value::<ConsoleSnapshot>(missing).is_err());

    value["memory"]["agent_usage_count"] = serde_json::json!(9);
    assert!(serde_json::from_value::<ConsoleSnapshot>(value).is_err());
}

#[test]
fn live_readiness_account_and_transition_are_strict_and_fail_closed() {
    let base: Value = serde_json::from_slice(&shared_snapshot_fixture()).unwrap();
    let readiness = &base["system"]["live_readiness"];
    for name in [
        "broker",
        "account",
        "data",
        "model",
        "strategy",
        "risk",
        "reconciliation",
        "incident",
        "authority",
    ] {
        assert_eq!(readiness[name]["state"], "unavailable");
    }
    assert_eq!(readiness["enabled"], false);
    assert!(base["system"]["live_account"].is_null());
    assert!(base["system"]["live_transition_plan"].is_null());

    let mut ready = base.clone();
    for gate in ready["system"]["live_readiness"]
        .as_object_mut()
        .unwrap()
        .values_mut()
        .filter(|value| value.is_object())
    {
        gate["state"] = serde_json::json!("ready");
        gate["reason"] = serde_json::json!("Reviewed test evidence.");
    }
    ready["system"]["live_readiness"]["enabled"] = serde_json::json!(true);
    ready["system"]["live_account"] = serde_json::json!({
        "name": "Primary brokerage",
        "number": "123456789",
        "balance": "1000.25",
        "capital": "900"
    });
    ready["system"]["live_transition_plan"] = serde_json::json!({
        "broker_positions_as_of_utc": "2026-08-04T12:00:00Z",
        "desired_portfolio_id": "portfolio:candidate",
        "orders": [{
            "symbol": "NVDA",
            "side": "buy",
            "quantity": "2.5",
            "approval_required": true
        }]
    });
    assert!(serde_json::from_value::<ConsoleSnapshot>(ready.clone()).is_ok());

    let invalid = [
        {
            let mut value = base.clone();
            value["system"]["live_readiness"]["enabled"] = serde_json::json!(true);
            value
        },
        {
            let mut value = ready.clone();
            value["system"]["live_readiness"]
                .as_object_mut()
                .unwrap()
                .remove("authority");
            value
        },
        {
            let mut value = base.clone();
            value["system"]
                .as_object_mut()
                .unwrap()
                .remove("live_account");
            value
        },
        {
            let mut value = base.clone();
            value["system"]
                .as_object_mut()
                .unwrap()
                .remove("live_transition_plan");
            value
        },
        {
            let mut value = ready.clone();
            value["system"]["live_account"]["credential"] = serde_json::json!("forbidden");
            value
        },
        {
            let mut value = ready.clone();
            value["system"]["live_transition_plan"]["orders"][0]["approval_required"] =
                serde_json::json!(false);
            value
        },
        {
            let mut value = ready.clone();
            value["system"]["live_transition_plan"]["orders"][0]["quantity"] =
                serde_json::json!("0");
            value
        },
    ];
    for value in invalid {
        assert!(serde_json::from_value::<ConsoleSnapshot>(value).is_err());
    }
}

#[test]
fn event_payload_is_keyed_closed_and_checks_operation_type_and_id() {
    let valid = serde_json::json!({
        "schema_version": 1,
        "message_id": "server:1",
        "sequence": 1,
        "state_version": 1,
        "timestamp_utc": "2026-08-03T00:00:00Z",
        "message_type": "event",
        "payload": {
            "entity_type": "alert-row",
            "entity_id": "alert:1",
            "operation": "upsert",
            "entity": {
                "alert_id": "alert:1",
                "severity": "urgent",
                "summary": "Needs attention",
                "created_at_utc": "2026-08-03T00:00:00Z",
                "resolved_at_utc": null
            },
            "targets": ["shell.alerts"],
            "presentation": event_presentation()
        }
    });
    let envelope: Envelope = serde_json::from_value(valid.clone()).expect("valid event");
    assert_eq!(envelope.message_type(), MessageType::Event);

    for invalid in [
        {
            let mut value = valid.clone();
            value["payload"]["entity_id"] = serde_json::json!("alert:2");
            value
        },
        {
            let mut value = valid.clone();
            value["payload"]["entity_type"] = serde_json::json!("metric-row");
            value
        },
        {
            let mut value = valid.clone();
            value["payload"]["operation"] = serde_json::json!("remove");
            value
        },
        {
            let mut value = valid.clone();
            value["payload"]["entity"] = serde_json::Value::Null;
            value
        },
        {
            let mut value = valid.clone();
            value["payload"]["entity"]["secret"] = serde_json::json!("x");
            value
        },
    ] {
        assert!(serde_json::from_value::<Envelope>(invalid).is_err());
    }
    let mut remove = valid;
    remove["payload"]["operation"] = serde_json::json!("remove");
    remove["payload"]["entity"] = serde_json::Value::Null;
    assert!(serde_json::from_value::<Envelope>(remove).is_ok());
}

#[test]
fn all_sixteen_event_entities_use_only_canonical_compatible_targets() {
    let snapshot: Value = serde_json::from_slice(&shared_snapshot_fixture()).unwrap();
    let cases = [
        (
            "portfolio-row",
            "AAPL",
            snapshot["portfolio"]["rows"][0].clone(),
            vec!["impact.holdings", "portfolio.rows"],
        ),
        (
            "agent-card",
            "work:1",
            snapshot["agents"]["rows"][0].clone(),
            vec![
                "impact.agents",
                "orders.reconciliation-agents",
                "agents.rows",
            ],
        ),
        (
            "timeline-row",
            "event:1",
            snapshot["timeline"]["rows"][0].clone(),
            vec![
                "impact.events",
                "portfolio.history",
                "orders.history",
                "agents.history",
                "timeline.rows",
                "memory.history",
            ],
        ),
        (
            "order-row",
            "order:1",
            snapshot["orders"]["rows"][0].clone(),
            vec!["orders.rows"],
        ),
        (
            "model-opinion-row",
            "model:active",
            snapshot["models"]["opinions"][0].clone(),
            vec!["models.opinions"],
        ),
        (
            "candidate-row",
            "candidate:1",
            snapshot["models"]["candidates"][0].clone(),
            vec!["models.candidates"],
        ),
        (
            "risk-limit-row",
            "limit:concentration",
            snapshot["risk"]["limits"][0].clone(),
            vec!["risk.limits"],
        ),
        (
            "approval-row",
            "approval:1",
            snapshot["risk"]["approvals"][0].clone(),
            vec!["risk.approvals"],
        ),
        (
            "source-row",
            "source:massive",
            snapshot["data"]["sources"][0].clone(),
            vec!["data.sources"],
        ),
        (
            "evidence-row",
            "evidence:1",
            snapshot["data"]["evidence"][0].clone(),
            vec!["models.evidence", "data.evidence"],
        ),
        (
            "memory-row",
            "memory:1",
            snapshot["memory"]["rows"][0].clone(),
            vec!["memory.rows"],
        ),
        (
            "service-row",
            "service:qwen",
            snapshot["system"]["services"][0].clone(),
            vec!["system.services"],
        ),
        (
            "repository-row",
            "repository:v20",
            snapshot["system"]["repositories"][0].clone(),
            vec!["system.repositories"],
        ),
        (
            "metric-row",
            "metric:cpu",
            snapshot["system"]["metrics"][0].clone(),
            vec![
                "portfolio.metrics",
                "models.metrics",
                "risk.metrics",
                "system.metrics",
            ],
        ),
        (
            "return-component-row",
            "price",
            snapshot["portfolio"]["returns_today"][0].clone(),
            vec![
                "portfolio.returns-today",
                "portfolio.returns-since-rebalance",
                "portfolio.returns-since-start",
            ],
        ),
        (
            "alert-row",
            "alert:1",
            snapshot["risk"]["alerts"][0].clone(),
            vec!["shell.alerts", "risk.alerts"],
        ),
    ];

    for (entity_type, entity_id, entity, targets) in cases {
        let valid = event_envelope(entity_type, entity_id, entity, &targets);
        assert!(
            serde_json::from_value::<Envelope>(valid.clone()).is_ok(),
            "failed {entity_type}"
        );
        let mut incompatible = valid;
        incompatible["payload"]["targets"] = if entity_type == "alert-row" {
            serde_json::json!(["orders.rows"])
        } else {
            serde_json::json!(["shell.alerts"])
        };
        assert!(serde_json::from_value::<Envelope>(incompatible).is_err());
    }

    let nested_fill = snapshot["orders"]["rows"][0]["fills"][0].clone();
    assert!(
        serde_json::from_value::<Envelope>(event_envelope(
            "fill-row",
            "fill:1",
            nested_fill,
            &["orders.rows"],
        ))
        .is_err()
    );
}

#[test]
fn event_targets_presentation_metrics_and_omissions_are_strict() {
    let snapshot: Value = serde_json::from_slice(&shared_snapshot_fixture()).unwrap();
    let base = event_envelope(
        "portfolio-row",
        "AAPL",
        snapshot["portfolio"]["rows"][0].clone(),
        &["impact.holdings", "portfolio.rows"],
    );
    for targets in [
        serde_json::json!([]),
        serde_json::json!(["portfolio.rows", "impact.holdings"]),
        serde_json::json!(["portfolio.rows", "portfolio.rows"]),
        serde_json::json!(["unknown.target"]),
        serde_json::json!(vec!["portfolio.rows"; 9]),
    ] {
        let mut invalid = base.clone();
        invalid["payload"]["targets"] = targets;
        assert!(serde_json::from_value::<Envelope>(invalid).is_err());
    }
    let mut missing_targets = base.clone();
    missing_targets["payload"]
        .as_object_mut()
        .unwrap()
        .remove("targets");
    assert!(serde_json::from_value::<Envelope>(missing_targets).is_err());
    let mut unknown_presentation = base;
    unknown_presentation["payload"]["presentation"]["secret"] = serde_json::json!("x");
    assert!(serde_json::from_value::<Envelope>(unknown_presentation).is_err());

    for omissions in [
        serde_json::json!([{"target": "timeline.rows", "omitted_count": 0}]),
        serde_json::json!([
            {"target": "timeline.rows", "omitted_count": 1},
            {"target": "timeline.rows", "omitted_count": 2}
        ]),
        serde_json::json!([
            {"target": "timeline.rows", "omitted_count": 1},
            {"target": "models.evidence", "omitted_count": 2}
        ]),
    ] {
        let mut invalid = snapshot.clone();
        invalid["window_omissions"] = omissions;
        assert!(serde_json::from_value::<ConsoleSnapshot>(invalid).is_err());
    }

    for changes in [
        serde_json::json!({"value": null}),
        serde_json::json!({"freshness": "stale", "error": null}),
        serde_json::json!({"freshness": "unavailable", "error": "Unavailable."}),
        serde_json::json!({"freshness": "loading"}),
    ] {
        let mut invalid = snapshot.clone();
        let metric = invalid["system"]["metrics"][0].as_object_mut().unwrap();
        for (name, value) in changes.as_object().unwrap() {
            metric.insert(name.clone(), value.clone());
        }
        assert!(serde_json::from_value::<ConsoleSnapshot>(invalid).is_err());
    }
}

#[test]
fn event_presentation_model_regime_rules_match_snapshot_rules() {
    let snapshot: Value = serde_json::from_slice(&shared_snapshot_fixture()).unwrap();
    let base = event_envelope(
        "portfolio-row",
        "AAPL",
        snapshot["portfolio"]["rows"][0].clone(),
        &["portfolio.rows"],
    );

    for required_field in ["model_final_regime", "model_final_regime_confidence"] {
        let mut invalid = base.clone();
        invalid["payload"]["presentation"][required_field] = Value::Null;
        assert!(
            serde_json::from_value::<Envelope>(invalid).is_err(),
            "decided event presentation accepted null {required_field}"
        );
    }

    for regime_state in ["uncertain", "unavailable"] {
        let prepare = || {
            let mut candidate = base.clone();
            let presentation = &mut candidate["payload"]["presentation"];
            presentation["model_regime_state"] = serde_json::json!(regime_state);
            presentation["model_final_regime"] = Value::Null;
            presentation["model_final_regime_confidence"] = Value::Null;
            candidate
        };

        let mut automatic_changes_allowed = prepare();
        automatic_changes_allowed["payload"]["presentation"]["model_automatic_changes_blocked"] =
            serde_json::json!(false);
        automatic_changes_allowed["payload"]["presentation"]["model_block_reason"] =
            serde_json::json!("Regime is not decided.");
        assert!(
            serde_json::from_value::<Envelope>(automatic_changes_allowed).is_err(),
            "{regime_state} event presentation allowed automatic changes"
        );

        let mut missing_reason = prepare();
        missing_reason["payload"]["presentation"]["model_automatic_changes_blocked"] =
            serde_json::json!(true);
        missing_reason["payload"]["presentation"]["model_block_reason"] = Value::Null;
        assert!(
            serde_json::from_value::<Envelope>(missing_reason).is_err(),
            "{regime_state} event presentation accepted no block reason"
        );

        let mut valid = prepare();
        valid["payload"]["presentation"]["model_automatic_changes_blocked"] =
            serde_json::json!(true);
        valid["payload"]["presentation"]["model_block_reason"] =
            serde_json::json!("Regime is not decided.");
        assert!(
            serde_json::from_value::<Envelope>(valid).is_ok(),
            "valid {regime_state} event presentation was rejected"
        );
    }
}

#[test]
fn decimal_and_nullable_fields_match_python_strictness() {
    let base = serde_json::json!({
        "schema_version": 1,
        "message_id": "server:1",
        "sequence": 1,
        "state_version": 1,
        "timestamp_utc": "2026-08-03T00:00:00Z",
        "message_type": "event",
        "payload": {
            "entity_type": "order-row",
            "entity_id": "order:1",
            "operation": "upsert",
            "entity": {
                "order_id": "order:1",
                "symbol": "AAPL",
                "side": "buy",
                "quantity": "10",
                "status": "proposed",
                "submitted_at_utc": null,
                "broker_order_id": null,
                "fills": [],
                "expected_price": null,
                "actual_price": null,
                "reconciliation": "unavailable"
            },
            "targets": ["orders.rows"],
            "presentation": event_presentation()
        }
    });
    assert!(serde_json::from_value::<Envelope>(base.clone()).is_ok());
    for invalid_decimal in ["", "+1", "01", ".5", "1.", "1e2", "NaN"] {
        let mut invalid = base.clone();
        invalid["payload"]["entity"]["quantity"] = serde_json::json!(invalid_decimal);
        assert!(serde_json::from_value::<Envelope>(invalid).is_err());
    }
    let mut missing_nullable = base;
    missing_nullable["payload"]["entity"]
        .as_object_mut()
        .unwrap()
        .remove("broker_order_id");
    assert!(serde_json::from_value::<Envelope>(missing_nullable).is_err());
}

#[test]
fn utc_timestamp_matches_the_shared_zero_offset_corpus() {
    let fixture = python_contract_bundle().fixtures[0].clone();
    let base: Value = serde_json::from_slice(&fixture).unwrap();
    for value in [
        "2026-08-03T00:00:00Z",
        "2026-08-03T00:00:00+00:00",
        "2026-08-03T00:00:00.1Z",
        "2026-08-03T00:00:00.123456+00:00",
    ] {
        let mut candidate = base.clone();
        candidate["timestamp_utc"] = Value::String(value.to_owned());
        assert!(
            serde_json::from_value::<Envelope>(candidate).is_ok(),
            "{value}"
        );
    }
    for value in [
        "2026-08-03T00:00:00-04:00",
        "2026-08-03 00:00:00Z",
        "2026-02-30T00:00:00Z",
        "2026-08-03T00:00:00.Z",
        "2026-08-03T00:00:00.1234567Z",
    ] {
        let mut candidate = base.clone();
        candidate["timestamp_utc"] = Value::String(value.to_owned());
        assert!(
            serde_json::from_value::<Envelope>(candidate).is_err(),
            "{value}"
        );
    }
}

#[test]
fn utc_timestamp_serialization_matches_python_zero_or_six_digit_form() {
    let fixture = python_contract_bundle().fixtures[0].clone();
    let base: Value = serde_json::from_slice(&fixture).unwrap();
    for (input, expected) in [
        ("2026-08-03T00:00:00Z", "2026-08-03T00:00:00Z"),
        ("2026-08-03T00:00:00+00:00", "2026-08-03T00:00:00Z"),
        ("2026-08-03T00:00:00.1Z", "2026-08-03T00:00:00.100000Z"),
        (
            "2026-08-03T00:00:00.123+00:00",
            "2026-08-03T00:00:00.123000Z",
        ),
        ("2026-08-03T00:00:00.000000Z", "2026-08-03T00:00:00Z"),
    ] {
        let mut candidate = base.clone();
        candidate["timestamp_utc"] = Value::String(input.to_owned());
        let envelope: Envelope = serde_json::from_value(candidate).unwrap();
        let serialized = serde_json::to_value(envelope).unwrap();
        assert_eq!(serialized["timestamp_utc"], expected);
    }
}

#[test]
fn repository_event_is_typed_keyed_and_freshness_checked() {
    let event = serde_json::json!({
        "schema_version": 1,
        "message_id": "server:1",
        "sequence": 1,
        "state_version": 1,
        "timestamp_utc": "2026-08-03T00:00:00Z",
        "message_type": "event",
        "payload": {
            "entity_type": "repository-row",
            "entity_id": "repository:v20",
            "operation": "upsert",
            "entity": {
                "repository_id": "repository:v20",
                "freshness": "fresh",
                "as_of_utc": "2026-08-03T00:00:00Z",
                "source": "git",
                "error": null,
                "branch": "codex/vesper/ratatui-console",
                "revision": "0123456789abcdef",
                "clean": true,
                "worktrees": ["C:/Users/bgonn/Desktop/v20"],
                "unpushed_commit_count": 0,
                "checks": [{
                    "check_id": "check:tests",
                    "state": "pass",
                    "reason": null,
                    "observed_at_utc": "2026-08-03T00:00:00Z"
                }]
            },
            "targets": ["system.repositories"],
            "presentation": event_presentation()
        }
    });
    assert!(serde_json::from_value::<Envelope>(event.clone()).is_ok());

    let mut mismatched = event.clone();
    mismatched["payload"]["entity_id"] = serde_json::json!("repository:other");
    assert!(serde_json::from_value::<Envelope>(mismatched).is_err());

    let mut stale_without_reason = event;
    stale_without_reason["payload"]["entity"]["freshness"] = serde_json::json!("stale");
    assert!(serde_json::from_value::<Envelope>(stale_without_reason).is_err());
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
    assert_eq!(bundle.fixtures.len(), 24);
    let mut seen = Vec::new();
    for fixture in bundle.fixtures {
        let envelope: Envelope =
            serde_json::from_slice(&fixture).expect("Python fixture parses in Rust");
        seen.push(envelope.message_type());
        assert_eq!(serde_json::to_vec(&envelope).unwrap(), fixture);
    }
    seen.sort_by_key(|value| value.to_string());
    seen.dedup();
    assert_eq!(seen.len(), 24);
    assert_eq!(rust_contract_descriptor(), bundle.descriptor);
}

fn rust_contract_descriptor() -> Vec<u8> {
    let descriptor = serde_json::json!({
        "envelope_required": ["schema_version", "message_id", "sequence", "state_version", "timestamp_utc", "message_type", "payload"],
        "field_catalog_scope": [
            "envelope", "payloads", "shell", "snapshot-observability-metadata",
            "event-presentation-metadata", "repository-status", "governed-command-contracts",
            "live-readiness", "agent-chat", "managed-memory-content"
        ],
        "integer_fields": [
            "envelope.sequence",
            "envelope.state_version",
            "command.request.reviewed_control_version",
            "snapshot.shell.state_version",
            "snapshot.control_version",
            "snapshot.shell.header.agent_queue_length",
            "snapshot.timeline.hidden_event_count",
            "snapshot.window_omissions[].omitted_count",
            "event.presentation.control_version",
            "event.presentation.header.agent_queue_length",
            "event.presentation.timeline_hidden_event_count",
            "event.presentation.window_omissions[].omitted_count",
            "repository.unpushed_commit_count",
            "chat-history-request.limit",
            "chat-event.chunk_sequence",
            "chat-event.token_count"
        ],
        "messages": {
            "auth-result": ["success", "access_state", "reason"],
            "auth-setup": ["password", "confirmation"],
            "auth-unlock": ["password"],
            "chat-event": [
                "event_id", "agent_id", "message_id", "role", "operation",
                "chunk_sequence", "text", "token_count", "message_created_at_utc",
                "occurred_at_utc", "validation_receipt_id", "raw_text_sha256"
            ],
            "chat-history-request": ["agent_id", "limit", "cursor"],
            "chat-history-result": ["agent_id", "next_cursor"],
            "client-hello": ["client_version", "supported_schema_versions"],
            "command": ["request"],
            "command-receipt": ["receipt"],
            "event": ["entity_type", "entity_id", "operation", "entity", "targets", "presentation"],
            "lease-request": ["action"],
            "lease-result": ["status", "reason"],
            "lock-request": ["action"],
            "lock-result": ["locked"],
            "memory-content-request": ["request_id", "memory_id", "reviewed_updated_at_utc"],
            "memory-content-result": ["request_id", "memory_id", "reviewed_updated_at_utc", "status", "content", "error"],
            "ping": ["nonce"],
            "pong": ["nonce"],
            "protocol-error": ["code", "safe_message"],
            "server-hello": ["server_version", "requires_setup"],
            "search-request": ["request_id", "query", "filters", "limit"],
            "search-results": ["request_id", "indexed_state_version", "results", "error"],
            "snapshot": ["snapshot"],
            "snapshot-request": [],
        },
        "nullable_required": [
            "auth-result.reason", "lease-result.reason", "search-results.error",
            "search-results.results[].occurred_at_utc",
            "search-results.results[].context_only",
            "memory-content-result.content",
            "memory-content-result.error",
            "chat-history-request.cursor",
            "chat-history-result.next_cursor",
            "chat-event.chunk_sequence",
            "chat-event.text",
            "chat-event.token_count",
            "chat-event.occurred_at_utc",
            "chat-event.validation_receipt_id",
            "chat-event.raw_text_sha256",
            "command.request.reason",
            "command-receipt.receipt.accepted_at_utc",
            "command-receipt.receipt.finished_at_utc",
            "command-receipt.receipt.result", "event.entity", "snapshot.shell.alerts",
            "alert.resolved_at_utc", "snapshot.shell.header.operating_mode_reason",
            "snapshot.shell.header.data_age_seconds",
            "snapshot.shell.header.regime_confidence",
            "snapshot.shell.header.portfolio_value",
            "snapshot.shell.header.next_rebalance_at_utc",
            "snapshot.shell.header.rebalance_blockers",
            "snapshot.shell.header.active_agent",
            "snapshot.shell.header.agent_queue_length",
            "snapshot.shell.header.qwen_context_percent",
            "snapshot.window_omissions[].omitted_count",
            "snapshot.impact.as_of_utc", "snapshot.impact.error",
            "snapshot.portfolio.as_of_utc", "snapshot.portfolio.error",
            "snapshot.portfolio.rank_source",
            "snapshot.orders.as_of_utc", "snapshot.orders.error",
            "snapshot.agents.as_of_utc", "snapshot.agents.error",
            "snapshot.models.as_of_utc", "snapshot.models.error",
            "snapshot.timeline.as_of_utc", "snapshot.timeline.error",
            "snapshot.risk.as_of_utc", "snapshot.risk.error",
            "snapshot.data.as_of_utc", "snapshot.data.error",
            "snapshot.memory.as_of_utc", "snapshot.memory.error",
            "snapshot.system.as_of_utc", "snapshot.system.error",
            "snapshot.system.live_account", "snapshot.system.live_transition_plan",
            "event.presentation.header.operating_mode_reason",
            "event.presentation.header.data_age_seconds",
            "event.presentation.header.regime_confidence",
            "event.presentation.header.portfolio_value",
            "event.presentation.header.next_rebalance_at_utc",
            "event.presentation.header.rebalance_blockers",
            "event.presentation.header.active_agent",
            "event.presentation.header.agent_queue_length",
            "event.presentation.header.qwen_context_percent",
            "event.presentation.window_omissions[].omitted_count",
            "event.presentation.impact.as_of_utc", "event.presentation.impact.error",
            "event.presentation.portfolio.as_of_utc", "event.presentation.portfolio.error",
            "event.presentation.orders.as_of_utc", "event.presentation.orders.error",
            "event.presentation.agents.as_of_utc", "event.presentation.agents.error",
            "event.presentation.models.as_of_utc", "event.presentation.models.error",
            "event.presentation.timeline.as_of_utc", "event.presentation.timeline.error",
            "event.presentation.risk.as_of_utc", "event.presentation.risk.error",
            "event.presentation.data.as_of_utc", "event.presentation.data.error",
            "event.presentation.memory.as_of_utc", "event.presentation.memory.error",
            "event.presentation.system.as_of_utc", "event.presentation.system.error",
            "event.presentation.portfolio_rank_source"
        ],
        "optional_default": [
            "capability.reason",
            "command.request.confirmation",
            "command.request.confirmation.first_confirmed",
            "command.request.confirmation.second_confirmed",
            "command.request.confirmation.typed_text",
            "command.request.confirmation.bound_preview_hash"
        ],
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

fn collect_object_pointers(value: &Value, pointer: &str, output: &mut Vec<String>) {
    match value {
        Value::Object(values) => {
            output.push(pointer.to_owned());
            for (key, child) in values {
                let key = key.replace('~', "~0").replace('/', "~1");
                collect_object_pointers(child, &format!("{pointer}/{key}"), output);
            }
        }
        Value::Array(values) => {
            for (index, child) in values.iter().enumerate() {
                collect_object_pointers(child, &format!("{pointer}/{index}"), output);
            }
        }
        _ => {}
    }
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
    for source in valid
        .iter()
        .filter(|value| matches!(value["message_type"].as_str(), Some("snapshot" | "event")))
    {
        let mut pointers = Vec::new();
        collect_object_pointers(&source["payload"], "/payload", &mut pointers);
        for pointer in pointers {
            let fields = source
                .pointer(&pointer)
                .and_then(Value::as_object)
                .unwrap()
                .keys()
                .cloned()
                .collect::<Vec<_>>();
            let mut unknown = source.clone();
            unknown
                .pointer_mut(&pointer)
                .and_then(Value::as_object_mut)
                .unwrap()
                .insert("unknown".to_owned(), Value::Bool(true));
            corpus.push(unknown);
            for field in fields {
                let mut missing = source.clone();
                missing
                    .pointer_mut(&pointer)
                    .and_then(Value::as_object_mut)
                    .unwrap()
                    .remove(&field);
                corpus.push(missing);
            }
        }
    }
    let snapshot = valid
        .iter()
        .find(|value| value["message_type"] == "snapshot")
        .unwrap();
    let event = valid
        .iter()
        .find(|value| value["message_type"] == "event")
        .unwrap();
    let header_reason_start = corpus.len();
    for reason in [
        Value::String(String::new()),
        Value::String("   ".to_owned()),
        Value::String("x".repeat(513)),
    ] {
        let mut snapshot_reason = snapshot.clone();
        snapshot_reason["payload"]["snapshot"]["shell"]["header"]["operating_mode_reason"] =
            reason.clone();
        corpus.push(snapshot_reason);
        let mut event_reason = event.clone();
        event_reason["payload"]["presentation"]["header"]["operating_mode_reason"] = reason;
        corpus.push(event_reason);
    }
    let header_reason_end = corpus.len();
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
            &["payload", "snapshot", "shell", "state_version"][..],
            serde_json::json!(-1),
        ),
        (
            &["payload", "snapshot", "shell", "state_version"][..],
            serde_json::json!(u64::MAX),
        ),
        (
            &["payload", "snapshot", "shell", "state_version"][..],
            serde_json::from_str("18446744073709551616").unwrap(),
        ),
        (
            &[
                "payload",
                "snapshot",
                "shell",
                "header",
                "agent_queue_length",
            ][..],
            serde_json::json!(-1),
        ),
        (
            &[
                "payload",
                "snapshot",
                "shell",
                "header",
                "agent_queue_length",
            ][..],
            serde_json::json!(u64::MAX),
        ),
        (
            &[
                "payload",
                "snapshot",
                "shell",
                "header",
                "agent_queue_length",
            ][..],
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
    assert!(
        python[header_reason_start..header_reason_end]
            .iter()
            .all(|accepted| !accepted)
    );
    assert!(
        rust[header_reason_start..header_reason_end]
            .iter()
            .all(|accepted| !accepted)
    );
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
fn parses_all_twenty_four_strict_payloads() {
    let snapshot = String::from_utf8(shared_snapshot_fixture()).unwrap();
    let event = serde_json::to_string(&serde_json::json!({
        "entity_type": "alert-row",
        "entity_id": "alert:1",
        "operation": "remove",
        "entity": null,
        "targets": ["shell.alerts"],
        "presentation": event_presentation(),
    }))
    .unwrap();
    let samples = vec![
        (
            "client-hello",
            r#"{"client_version":"0.1.0","supported_schema_versions":[1]}"#.to_owned(),
        ),
        (
            "server-hello",
            r#"{"server_version":"0.1.0","requires_setup":false}"#.to_owned(),
        ),
        (
            "auth-setup",
            r#"{"password":"p","confirmation":"p"}"#.to_owned(),
        ),
        ("auth-unlock", r#"{"password":"p"}"#.to_owned()),
        (
            "auth-result",
            r#"{"success":true,"access_state":"viewer","reason":null}"#.to_owned(),
        ),
        ("lease-request", r#"{"action":"take-control"}"#.to_owned()),
        (
            "lease-result",
            r#"{"status":"controller","reason":null}"#.to_owned(),
        ),
        ("lock-request", r#"{"action":"lock"}"#.to_owned()),
        ("lock-result", r#"{"locked":true}"#.to_owned()),
        ("snapshot-request", r#"{}"#.to_owned()),
        ("snapshot", format!(r#"{{"snapshot":{snapshot}}}"#)),
        (
            "search-request",
            r#"{"request_id":1,"query":"AAPL","filters":{"kinds":["stock","note"],"screens":["portfolio"],"source":null},"limit":100}"#.to_owned(),
        ),
        (
            "search-results",
            r#"{"request_id":1,"indexed_state_version":0,"results":[{"kind":"note","record_type":"note","record_id":"note:1","label":"AAPL note","summary":"Review concentration risk.","occurred_at_utc":"2026-08-03T00:00:00Z","source":"operator","screen":"portfolio","context_only":true}],"error":null}"#.to_owned(),
        ),
        (
            "memory-content-request",
            r#"{"request_id":1,"memory_id":"memory:1","reviewed_updated_at_utc":"2026-08-03T00:00:00Z"}"#.to_owned(),
        ),
        (
            "memory-content-result",
            r#"{"request_id":1,"memory_id":"memory:1","reviewed_updated_at_utc":"2026-08-03T00:00:00Z","status":"success","content":"Full current content.","error":null}"#.to_owned(),
        ),
        (
            "chat-history-request",
            r#"{"agent_id":"v20-product","limit":20,"cursor":null}"#.to_owned(),
        ),
        (
            "chat-event",
            r#"{"event_id":"chat:event:1","agent_id":"v20-product","message_id":"chat:message:1","role":"agent","operation":"chunk","chunk_sequence":1,"text":"Working","token_count":null,"message_created_at_utc":"2026-08-03T00:00:00Z","occurred_at_utc":null,"validation_receipt_id":null,"raw_text_sha256":null}"#.to_owned(),
        ),
        (
            "chat-history-result",
            r#"{"agent_id":"v20-product","next_cursor":null}"#.to_owned(),
        ),
        (
            "command",
            r#"{"request":{"command_id":"client:command:1","command_type":"note.add","reviewed_control_version":19,"reviewed_control_hash":"7c222fb2927d828af22f592134e8932480637c0d1a3a6c9f5d6f0f975f6e3f43","reason":null,"confirmation":null,"payload":{"target_type":"stock","target_id":"AAPL","body":"Review concentration.","visibility":"private"}}}"#.to_owned(),
        ),
        (
            "command-receipt",
            r#"{"receipt":{"command_id":"client:command:1","status":"completed","code":"completed","safe_message":"Note stored.","accepted_at_utc":"2026-08-03T00:00:00Z","finished_at_utc":"2026-08-03T00:00:01Z","result":null}}"#.to_owned(),
        ),
        ("event", event),
        (
            "protocol-error",
            r#"{"code":"locked","safe_message":"Locked."}"#.to_owned(),
        ),
        ("ping", r#"{"nonce":"n:1"}"#.to_owned()),
        ("pong", r#"{"nonce":"n:1"}"#.to_owned()),
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
        (
            "search-request",
            r#"{"request_id":0,"query":"AAPL","filters":{"kinds":[],"screens":[],"source":null},"limit":100}"#,
        ),
        (
            "search-request",
            r#"{"request_id":1,"query":"   ","filters":{"kinds":[],"screens":[],"source":null},"limit":100}"#,
        ),
        (
            "search-request",
            r#"{"request_id":1,"query":"AAPL","filters":{"kinds":[],"screens":[],"source":null},"limit":0}"#,
        ),
        (
            "search-results",
            r#"{"request_id":1,"indexed_state_version":0,"results":[{"kind":"note","record_type":"note","record_id":"note:1","label":"AAPL note","summary":"context","occurred_at_utc":null,"source":"operator","screen":"portfolio","context_only":false}],"error":null}"#,
        ),
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
