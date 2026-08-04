use std::path::PathBuf;

use serde_json::{Value, json};
use vesper_ratatui_console::contract::{ConsoleSnapshot, Envelope, EventTarget, Freshness};
use vesper_ratatui_console::reducer::{EventEnvelope, GapKind, ReduceOutcome, SnapshotReducer};

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .expect("crate is nested two levels under the repository")
        .to_path_buf()
}

fn snapshot_value() -> Value {
    serde_json::from_slice(
        &std::fs::read(
            repo_root().join("TUI testing/contracts/v1/console_snapshot_empty_command_specs.json"),
        )
        .expect("read shared snapshot fixture"),
    )
    .expect("parse shared snapshot fixture")
}

fn snapshot(mut value: Value, state_version: u64) -> ConsoleSnapshot {
    value["shell"]["state_version"] = json!(state_version);
    serde_json::from_value(value).expect("strict snapshot")
}

fn presentation(snapshot: &Value) -> Value {
    let screen_meta = |name: &str| {
        json!({
            "freshness": snapshot[name]["freshness"].clone(),
            "as_of_utc": snapshot[name]["as_of_utc"].clone(),
            "source": snapshot[name]["source"].clone(),
            "error": snapshot[name]["error"].clone(),
        })
    };
    json!({
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
    })
}

fn event(
    _snapshot: &Value,
    sequence: u64,
    state_version: u64,
    operation: &str,
    entity: Value,
    targets: &[&str],
    presentation: Value,
) -> EventEnvelope {
    let entity_id = entity
        .get("symbol")
        .or_else(|| entity.get("event_id"))
        .and_then(Value::as_str)
        .unwrap_or("AAPL")
        .to_owned();
    typed_event(
        sequence,
        state_version,
        if entity.get("symbol").is_some() {
            "portfolio-row"
        } else {
            "timeline-row"
        },
        &entity_id,
        operation,
        entity,
        targets,
        presentation,
    )
}

#[allow(clippy::too_many_arguments)]
fn typed_event(
    sequence: u64,
    state_version: u64,
    entity_type: &str,
    entity_id: &str,
    operation: &str,
    entity: Value,
    targets: &[&str],
    presentation: Value,
) -> EventEnvelope {
    let envelope: Envelope = serde_json::from_value(json!({
        "schema_version": 1,
        "message_id": format!("server:{sequence}"),
        "sequence": sequence,
        "state_version": state_version,
        "timestamp_utc": "2026-08-03T00:00:00Z",
        "message_type": "event",
        "payload": {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "operation": operation,
            "entity": if operation == "remove" { Value::Null } else { entity },
            "targets": targets,
            "presentation": presentation,
        }
    }))
    .expect("strict event envelope");
    EventEnvelope::try_from(envelope).expect("event message")
}

#[test]
fn snapshot_replaces_command_specs_atomically() {
    let mut reducer = SnapshotReducer::default();
    let mut first = snapshot_value();
    first["command_specs"] = json!([{
        "command_type": "note.add",
        "payload_model": "NoteAddPayload",
        "capability_id": "notes.write",
        "reason_rule": "optional",
        "confirmation_level": "none"
    }]);

    assert_eq!(
        reducer.apply_snapshot(snapshot(first, 1)),
        ReduceOutcome::Changed
    );
    assert_eq!(
        reducer.state().command_specs["note.add"]
            .payload_model
            .as_str(),
        "NoteAddPayload"
    );

    assert_eq!(
        reducer.apply_snapshot(snapshot(snapshot_value(), 2)),
        ReduceOutcome::Changed
    );
    assert!(reducer.state().command_specs.is_empty());
    assert!(reducer.state().snapshot.command_specs.is_empty());
}

#[test]
fn events_apply_in_order_and_duplicate_sequences_are_idempotent() {
    let base = snapshot_value();
    let mut reducer = SnapshotReducer::default();
    reducer.apply_snapshot(snapshot(base.clone(), 1));
    let mut changed = base["portfolio"]["rows"][0].clone();
    changed["current_weight"] = json!(0.2);

    assert_eq!(
        reducer
            .apply_event(event(
                &base,
                41,
                2,
                "upsert",
                changed.clone(),
                &["impact.holdings", "portfolio.rows"],
                presentation(&base),
            ))
            .unwrap(),
        ReduceOutcome::Changed
    );
    assert_eq!(
        reducer.state().snapshot.portfolio.rows[0].current_weight,
        0.2
    );
    assert_eq!(
        reducer.state().snapshot.impact.holdings[0].current_weight,
        0.2
    );
    assert_eq!(reducer.state().snapshot.portfolio.rows.len(), 1);

    changed["current_weight"] = json!(0.9);
    assert_eq!(
        reducer
            .apply_event(event(
                &base,
                41,
                3,
                "upsert",
                changed,
                &["impact.holdings", "portfolio.rows"],
                presentation(&base),
            ))
            .unwrap(),
        ReduceOutcome::Ignored
    );
    assert_eq!(
        reducer.state().snapshot.portfolio.rows[0].current_weight,
        0.2
    );
}

#[test]
fn non_event_wire_sequences_can_interleave_between_events() {
    let base = snapshot_value();
    let mut reducer = SnapshotReducer::default();
    reducer.apply_snapshot(snapshot(base.clone(), 1));
    let mut first = base["portfolio"]["rows"][0].clone();
    first["current_weight"] = json!(0.2);
    reducer
        .apply_event(event(
            &base,
            41,
            2,
            "upsert",
            first,
            &["portfolio.rows"],
            presentation(&base),
        ))
        .unwrap();

    assert_eq!(
        reducer.observe_sequence(42).unwrap(),
        ReduceOutcome::Ignored
    );
    let mut second = base["portfolio"]["rows"][0].clone();
    second["current_weight"] = json!(0.3);
    assert_eq!(
        reducer
            .apply_event(event(
                &base,
                43,
                3,
                "upsert",
                second,
                &["portfolio.rows"],
                presentation(&base),
            ))
            .unwrap(),
        ReduceOutcome::Changed
    );
    assert_eq!(
        reducer.state().snapshot.portfolio.rows[0].current_weight,
        0.3
    );
}

#[test]
fn sequence_gap_preserves_state_and_requires_a_snapshot() {
    let base = snapshot_value();
    let mut reducer = SnapshotReducer::default();
    reducer.apply_snapshot(snapshot(base.clone(), 1));
    let row = base["portfolio"]["rows"][0].clone();
    reducer
        .apply_event(event(
            &base,
            7,
            2,
            "upsert",
            row.clone(),
            &["portfolio.rows"],
            presentation(&base),
        ))
        .unwrap();

    let before_gap = serde_json::to_value(&reducer.state().snapshot).unwrap();
    let error = reducer
        .apply_event(event(
            &base,
            9,
            3,
            "upsert",
            row,
            &["portfolio.rows"],
            presentation(&base),
        ))
        .expect_err("missing sequence eight must fail closed");

    assert_eq!((error.expected, error.received), (8, 9));
    assert!(error.resnapshot_required);
    assert!(reducer.needs_snapshot());
    assert_eq!(reducer.state().snapshot.shell.state_version, 2);
    assert_eq!(
        serde_json::to_value(&reducer.state().snapshot).unwrap(),
        before_gap
    );
}

#[test]
fn regressed_state_version_fails_closed_before_any_event_mutation() {
    let base = snapshot_value();
    let mut reducer = SnapshotReducer::default();
    reducer.apply_snapshot(snapshot(base.clone(), 5));
    let mut current = base["portfolio"]["rows"][0].clone();
    current["current_weight"] = json!(0.2);
    reducer
        .apply_event(event(
            &base,
            7,
            6,
            "upsert",
            current,
            &["portfolio.rows"],
            presentation(&base),
        ))
        .unwrap();
    let before = serde_json::to_value(&reducer.state().snapshot).unwrap();
    let mut regressed = base["portfolio"]["rows"][0].clone();
    regressed["current_weight"] = json!(0.9);

    let error = reducer
        .apply_event(event(
            &base,
            8,
            5,
            "upsert",
            regressed,
            &["portfolio.rows"],
            presentation(&base),
        ))
        .expect_err("state version must never move backwards");

    assert_eq!(error.kind, GapKind::StateVersion);
    assert_eq!((error.expected, error.received), (6, 5));
    assert!(reducer.needs_snapshot());
    assert_eq!(
        serde_json::to_value(&reducer.state().snapshot).unwrap(),
        before
    );
}

#[test]
fn event_control_pair_cannot_regress_or_diverge_before_mutation() {
    let mut base = snapshot_value();
    base["control_version"] = json!(5);
    base["control_hash"] =
        json!("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");

    for (incoming_version, incoming_hash, expected_kind) in [
        (
            4,
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            GapKind::ControlVersion,
        ),
        (
            5,
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            GapKind::ControlHash,
        ),
    ] {
        let mut reducer = SnapshotReducer::default();
        reducer.apply_snapshot(snapshot(base.clone(), 1));
        let before = serde_json::to_value(&reducer.state().snapshot).unwrap();
        let mut changed = base["portfolio"]["rows"][0].clone();
        changed["current_weight"] = json!(0.9);
        let mut event_presentation = presentation(&base);
        event_presentation["control_version"] = json!(incoming_version);
        event_presentation["control_hash"] = json!(incoming_hash);

        let error = reducer
            .apply_event(event(
                &base,
                1,
                2,
                "upsert",
                changed,
                &["portfolio.rows"],
                event_presentation,
            ))
            .expect_err("invalid control pair must fail closed");

        assert_eq!(error.kind, expected_kind);
        if expected_kind == GapKind::ControlHash {
            assert_eq!(
                error.to_string(),
                "control hash changed without a control-version advance at version 5"
            );
        }
        assert!(reducer.needs_snapshot());
        assert_eq!(
            serde_json::to_value(&reducer.state().snapshot).unwrap(),
            before
        );
    }
}

#[test]
fn newer_snapshot_control_pair_cannot_regress_or_diverge() {
    let mut base = snapshot_value();
    base["control_version"] = json!(5);
    base["control_hash"] =
        json!("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");

    for (incoming_version, incoming_hash) in [
        (
            4,
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        ),
        (
            5,
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        ),
    ] {
        let mut reducer = SnapshotReducer::default();
        reducer.apply_snapshot(snapshot(base.clone(), 1));
        let before = serde_json::to_value(&reducer.state().snapshot).unwrap();
        let mut invalid = base.clone();
        invalid["control_version"] = json!(incoming_version);
        invalid["control_hash"] = json!(incoming_hash);

        assert_eq!(
            reducer.apply_snapshot(snapshot(invalid, 2)),
            ReduceOutcome::ResnapshotRequired
        );
        assert!(reducer.needs_snapshot());
        assert_eq!(
            serde_json::to_value(&reducer.state().snapshot).unwrap(),
            before
        );
    }
}

#[test]
fn equal_or_higher_valid_control_pairs_are_accepted() {
    let mut base = snapshot_value();
    base["control_version"] = json!(5);
    base["control_hash"] =
        json!("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
    let mut reducer = SnapshotReducer::default();
    reducer.apply_snapshot(snapshot(base.clone(), 1));

    reducer
        .apply_event(event(
            &base,
            1,
            2,
            "upsert",
            base["portfolio"]["rows"][0].clone(),
            &["portfolio.rows"],
            presentation(&base),
        ))
        .unwrap();
    let mut higher = presentation(&base);
    higher["control_version"] = json!(6);
    higher["control_hash"] =
        json!("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");

    assert_eq!(
        reducer
            .apply_event(event(
                &base,
                2,
                3,
                "upsert",
                base["portfolio"]["rows"][0].clone(),
                &["portfolio.rows"],
                higher,
            ))
            .unwrap(),
        ReduceOutcome::Changed
    );
    assert_eq!(reducer.state().snapshot.control_version, 6);
}

#[test]
fn equal_state_version_is_valid_for_an_ordered_multi_event_batch() {
    let base = snapshot_value();
    let mut reducer = SnapshotReducer::default();
    reducer.apply_snapshot(snapshot(base.clone(), 1));
    let mut first = base["portfolio"]["rows"][0].clone();
    first["current_weight"] = json!(0.2);
    reducer
        .apply_event(event(
            &base,
            1,
            2,
            "upsert",
            first,
            &["portfolio.rows"],
            presentation(&base),
        ))
        .unwrap();
    let mut second = base["portfolio"]["rows"][0].clone();
    second["current_weight"] = json!(0.3);

    assert_eq!(
        reducer
            .apply_event(event(
                &base,
                2,
                2,
                "upsert",
                second,
                &["portfolio.rows"],
                presentation(&base),
            ))
            .unwrap(),
        ReduceOutcome::Changed
    );
    assert_eq!(reducer.state().snapshot.shell.state_version, 2);
    assert_eq!(
        reducer.state().snapshot.portfolio.rows[0].current_weight,
        0.3
    );
}

#[test]
fn full_snapshot_recovers_from_a_gap_and_rebases_the_event_sequence() {
    let base = snapshot_value();
    let mut reducer = SnapshotReducer::default();
    reducer.apply_snapshot(snapshot(base.clone(), 1));
    let row = base["portfolio"]["rows"][0].clone();
    reducer
        .apply_event(event(
            &base,
            7,
            2,
            "upsert",
            row.clone(),
            &["portfolio.rows"],
            presentation(&base),
        ))
        .unwrap();
    assert!(
        reducer
            .apply_event(event(
                &base,
                9,
                3,
                "upsert",
                row.clone(),
                &["portfolio.rows"],
                presentation(&base),
            ))
            .is_err()
    );

    assert_eq!(
        reducer.apply_snapshot(snapshot(base.clone(), 3)),
        ReduceOutcome::Changed
    );
    assert!(!reducer.needs_snapshot());
    assert_eq!(
        reducer
            .apply_event(event(
                &base,
                100,
                4,
                "upsert",
                row,
                &["portfolio.rows"],
                presentation(&base),
            ))
            .unwrap(),
        ReduceOutcome::Changed
    );
}

#[test]
fn equal_version_snapshot_recovers_a_partial_same_version_event_batch() {
    let base = snapshot_value();
    let mut reducer = SnapshotReducer::default();
    reducer.apply_snapshot(snapshot(base.clone(), 1));

    let mut first_change = base["portfolio"]["rows"][0].clone();
    first_change["current_weight"] = json!(0.2);
    reducer
        .apply_event(event(
            &base,
            10,
            2,
            "upsert",
            first_change,
            &["portfolio.rows"],
            presentation(&base),
        ))
        .unwrap();

    let mut later_change = base["portfolio"]["rows"][0].clone();
    later_change["current_weight"] = json!(0.3);
    assert!(
        reducer
            .apply_event(event(
                &base,
                12,
                2,
                "upsert",
                later_change.clone(),
                &["portfolio.rows"],
                presentation(&base),
            ))
            .is_err()
    );
    assert!(reducer.needs_snapshot());
    assert_eq!(
        reducer.state().snapshot.portfolio.rows[0].current_weight,
        0.2
    );

    let mut authoritative = base.clone();
    authoritative["portfolio"]["rows"][0] = later_change;
    assert_eq!(
        reducer.apply_snapshot(snapshot(authoritative, 2)),
        ReduceOutcome::Changed
    );
    assert!(!reducer.needs_snapshot());
    assert_eq!(
        reducer.state().snapshot.portfolio.rows[0].current_weight,
        0.3
    );
}

#[test]
fn duplicate_entity_ids_in_a_snapshot_fail_closed_without_replacing_state() {
    let base = snapshot_value();
    let mut reducer = SnapshotReducer::default();
    reducer.apply_snapshot(snapshot(base.clone(), 1));
    let before = serde_json::to_value(&reducer.state().snapshot).unwrap();
    let mut duplicate = base;
    let duplicate_row = duplicate["portfolio"]["rows"][0].clone();
    duplicate["portfolio"]["rows"]
        .as_array_mut()
        .unwrap()
        .push(duplicate_row);

    assert_eq!(
        reducer.apply_snapshot(snapshot(duplicate, 2)),
        ReduceOutcome::ResnapshotRequired
    );
    assert!(reducer.needs_snapshot());
    assert_eq!(
        serde_json::to_value(&reducer.state().snapshot).unwrap(),
        before
    );
}

#[test]
fn event_presentation_keeps_stale_reason_visible() {
    let base = snapshot_value();
    let mut stale = presentation(&base);
    stale["portfolio"]["freshness"] = json!("stale");
    stale["portfolio"]["error"] = json!("Position read-back is delayed.");
    let mut reducer = SnapshotReducer::default();
    reducer.apply_snapshot(snapshot(base.clone(), 1));

    reducer
        .apply_event(event(
            &base,
            1,
            2,
            "upsert",
            base["portfolio"]["rows"][0].clone(),
            &["portfolio.rows"],
            stale,
        ))
        .unwrap();

    assert_eq!(
        reducer.state().snapshot.portfolio.freshness,
        Freshness::Stale
    );
    assert_eq!(
        reducer.state().snapshot.portfolio.error.as_deref(),
        Some("Position read-back is delayed.")
    );
}

#[test]
fn selection_stays_on_entity_id_when_snapshot_order_changes() {
    let mut first = snapshot_value();
    let mut msft = first["portfolio"]["rows"][0].clone();
    msft["symbol"] = json!("MSFT");
    msft["description"] = json!("Microsoft");
    msft["confirmed_rank"] = json!(2);
    first["portfolio"]["rows"]
        .as_array_mut()
        .unwrap()
        .push(msft.clone());
    let mut second = first.clone();
    second["portfolio"]["rows"] = json!([msft, first["portfolio"]["rows"][0].clone()]);

    let mut reducer = SnapshotReducer::default();
    reducer.apply_snapshot(snapshot(first, 1));
    assert!(reducer.select(EventTarget::PortfolioRows, "AAPL"));
    reducer.apply_snapshot(snapshot(second, 2));

    assert_eq!(
        reducer.selected_id(EventTarget::PortfolioRows),
        Some("AAPL")
    );
    assert_eq!(
        reducer.state().snapshot.portfolio.rows[0].symbol.as_str(),
        "MSFT"
    );
}

#[test]
fn removing_the_selected_entity_clears_only_that_target_selection() {
    let base = snapshot_value();
    let mut reducer = SnapshotReducer::default();
    reducer.apply_snapshot(snapshot(base.clone(), 1));
    assert!(reducer.select(EventTarget::PortfolioRows, "AAPL"));
    assert!(reducer.select(EventTarget::ImpactHoldings, "AAPL"));

    reducer
        .apply_event(event(
            &base,
            1,
            2,
            "remove",
            base["portfolio"]["rows"][0].clone(),
            &["portfolio.rows"],
            presentation(&base),
        ))
        .unwrap();

    assert_eq!(reducer.selected_id(EventTarget::PortfolioRows), None);
    assert_eq!(
        reducer.selected_id(EventTarget::ImpactHoldings),
        Some("AAPL")
    );
}

#[test]
fn removing_an_unavailable_shell_alert_keeps_alerts_unavailable() {
    let mut base = snapshot_value();
    base["shell"]["alerts"] = Value::Null;
    let mut reducer = SnapshotReducer::default();
    reducer.apply_snapshot(snapshot(base.clone(), 1));

    reducer
        .apply_event(typed_event(
            1,
            2,
            "alert-row",
            "alert:1",
            "remove",
            base["risk"]["alerts"][0].clone(),
            &["shell.alerts"],
            presentation(&base),
        ))
        .unwrap();

    assert!(reducer.state().snapshot.shell.alerts.is_none());
}

#[test]
fn every_wire_entity_updates_and_removes_every_compatible_target() {
    struct Case {
        entity_type: &'static str,
        id_field: &'static str,
        id: &'static str,
        entity: Value,
        targets: &'static [(&'static str, &'static str)],
    }

    let base = snapshot_value();
    let changed = |path: &str, field: &str, id: &str| {
        let mut row = base.pointer(path).expect("fixture row").clone();
        row[field] = json!(id);
        row
    };
    let cases = vec![
        Case {
            entity_type: "portfolio-row",
            id_field: "symbol",
            id: "MSFT",
            entity: changed("/portfolio/rows/0", "symbol", "MSFT"),
            targets: &[
                ("impact.holdings", "/impact/holdings"),
                ("portfolio.rows", "/portfolio/rows"),
            ],
        },
        Case {
            entity_type: "agent-card",
            id_field: "work_id",
            id: "work:added",
            entity: changed("/agents/rows/0", "work_id", "work:added"),
            targets: &[
                ("impact.agents", "/impact/agents"),
                (
                    "orders.reconciliation-agents",
                    "/orders/reconciliation_agents",
                ),
                ("agents.rows", "/agents/rows"),
            ],
        },
        Case {
            entity_type: "timeline-row",
            id_field: "event_id",
            id: "event:added",
            entity: changed("/timeline/rows/0", "event_id", "event:added"),
            targets: &[
                ("impact.events", "/impact/events"),
                ("portfolio.history", "/portfolio/history"),
                ("orders.history", "/orders/history"),
                ("agents.history", "/agents/history"),
                ("timeline.rows", "/timeline/rows"),
                ("memory.history", "/memory/history"),
            ],
        },
        Case {
            entity_type: "order-row",
            id_field: "order_id",
            id: "order:added",
            entity: changed("/orders/rows/0", "order_id", "order:added"),
            targets: &[("orders.rows", "/orders/rows")],
        },
        Case {
            entity_type: "model-opinion-row",
            id_field: "model_id",
            id: "model:added",
            entity: changed("/models/opinions/0", "model_id", "model:added"),
            targets: &[("models.opinions", "/models/opinions")],
        },
        Case {
            entity_type: "candidate-row",
            id_field: "candidate_id",
            id: "candidate:added",
            entity: changed("/models/candidates/0", "candidate_id", "candidate:added"),
            targets: &[("models.candidates", "/models/candidates")],
        },
        Case {
            entity_type: "risk-limit-row",
            id_field: "limit_id",
            id: "limit:added",
            entity: changed("/risk/limits/0", "limit_id", "limit:added"),
            targets: &[("risk.limits", "/risk/limits")],
        },
        Case {
            entity_type: "approval-row",
            id_field: "approval_id",
            id: "approval:added",
            entity: changed("/risk/approvals/0", "approval_id", "approval:added"),
            targets: &[("risk.approvals", "/risk/approvals")],
        },
        Case {
            entity_type: "source-row",
            id_field: "source_id",
            id: "source:added",
            entity: changed("/data/sources/0", "source_id", "source:added"),
            targets: &[("data.sources", "/data/sources")],
        },
        Case {
            entity_type: "evidence-row",
            id_field: "evidence_id",
            id: "evidence:added",
            entity: changed("/data/evidence/0", "evidence_id", "evidence:added"),
            targets: &[
                ("models.evidence", "/models/evidence"),
                ("data.evidence", "/data/evidence"),
            ],
        },
        Case {
            entity_type: "memory-row",
            id_field: "memory_id",
            id: "memory:added",
            entity: changed("/memory/rows/0", "memory_id", "memory:added"),
            targets: &[("memory.rows", "/memory/rows")],
        },
        Case {
            entity_type: "service-row",
            id_field: "service_id",
            id: "service:added",
            entity: changed("/system/services/0", "service_id", "service:added"),
            targets: &[("system.services", "/system/services")],
        },
        Case {
            entity_type: "repository-row",
            id_field: "repository_id",
            id: "repository:added",
            entity: changed(
                "/system/repositories/0",
                "repository_id",
                "repository:added",
            ),
            targets: &[("system.repositories", "/system/repositories")],
        },
        Case {
            entity_type: "metric-row",
            id_field: "metric_id",
            id: "metric:added",
            entity: changed("/system/metrics/0", "metric_id", "metric:added"),
            targets: &[
                ("portfolio.metrics", "/portfolio/metrics"),
                ("models.metrics", "/models/metrics"),
                ("risk.metrics", "/risk/metrics"),
                ("system.metrics", "/system/metrics"),
            ],
        },
        Case {
            entity_type: "return-component-row",
            id_field: "component",
            id: "price",
            entity: base["portfolio"]["returns_today"][0].clone(),
            targets: &[
                ("portfolio.returns-today", "/portfolio/returns_today"),
                (
                    "portfolio.returns-since-rebalance",
                    "/portfolio/returns_since_rebalance",
                ),
                (
                    "portfolio.returns-since-start",
                    "/portfolio/returns_since_start",
                ),
            ],
        },
        Case {
            entity_type: "alert-row",
            id_field: "alert_id",
            id: "alert:added",
            entity: changed("/risk/alerts/0", "alert_id", "alert:added"),
            targets: &[
                ("shell.alerts", "/shell/alerts"),
                ("risk.alerts", "/risk/alerts"),
            ],
        },
    ];

    let mut reducer = SnapshotReducer::default();
    reducer.apply_snapshot(snapshot(base.clone(), 1));
    let mut sequence = 1;
    for case in cases {
        let targets = case
            .targets
            .iter()
            .map(|(target, _)| *target)
            .collect::<Vec<_>>();
        reducer
            .apply_event(typed_event(
                sequence,
                sequence + 1,
                case.entity_type,
                case.id,
                "upsert",
                case.entity.clone(),
                &targets,
                presentation(&base),
            ))
            .unwrap();
        sequence += 1;
        let value = serde_json::to_value(&reducer.state().snapshot).unwrap();
        for (_, path) in case.targets {
            assert!(
                value
                    .pointer(path)
                    .and_then(Value::as_array)
                    .unwrap()
                    .iter()
                    .any(|row| row[case.id_field] == case.id),
                "{} did not update {path}",
                case.entity_type
            );
        }

        reducer
            .apply_event(typed_event(
                sequence,
                sequence + 1,
                case.entity_type,
                case.id,
                "remove",
                case.entity,
                &targets,
                presentation(&base),
            ))
            .unwrap();
        sequence += 1;
        let value = serde_json::to_value(&reducer.state().snapshot).unwrap();
        for (_, path) in case.targets {
            assert!(
                value
                    .pointer(path)
                    .and_then(Value::as_array)
                    .unwrap()
                    .iter()
                    .all(|row| row[case.id_field] != case.id),
                "{} did not remove from {path}",
                case.entity_type
            );
        }
    }
}
