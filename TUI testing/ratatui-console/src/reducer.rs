use std::collections::HashMap;
use std::error::Error;
use std::fmt;

use crate::contract::{
    AgentCard, AlertRow, CandidateRow, CommandSpecView, ConsoleSnapshot, Envelope, EventEntity,
    EventOperation, EventPayload, EventPresentation, EventTarget, EvidenceRow, MemoryRow, Message,
    MetricRow, ModelOpinionRow, OrderRow, PortfolioRow, RepositoryRow, ReturnComponent,
    ReturnComponentRow, RiskLimitRow, ServiceRow, SourceRow, TimelineRow,
};

#[derive(Clone, Debug, PartialEq)]
pub struct EventEnvelope {
    pub sequence: u64,
    pub state_version: u64,
    pub payload: EventPayload,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct EventEnvelopeError;

impl fmt::Display for EventEnvelopeError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("wire envelope is not an event")
    }
}

impl Error for EventEnvelopeError {}

impl TryFrom<Envelope> for EventEnvelope {
    type Error = EventEnvelopeError;

    fn try_from(envelope: Envelope) -> Result<Self, Self::Error> {
        let Message::Event(payload) = envelope.message else {
            return Err(EventEnvelopeError);
        };
        Ok(Self {
            sequence: envelope.sequence,
            state_version: envelope.state_version,
            payload: *payload,
        })
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ReduceOutcome {
    Changed,
    Ignored,
    ResnapshotRequired,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum GapKind {
    EventSequence,
    StateVersion,
    ControlVersion,
    ControlHash,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SequenceGap {
    pub kind: GapKind,
    pub expected: u64,
    pub received: u64,
    pub resnapshot_required: bool,
}

impl fmt::Display for SequenceGap {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.kind == GapKind::ControlHash {
            return write!(
                formatter,
                "control hash changed without a control-version advance at version {}",
                self.expected
            );
        }
        let field = match self.kind {
            GapKind::EventSequence => "event sequence",
            GapKind::StateVersion => "state version",
            GapKind::ControlVersion => "control version",
            GapKind::ControlHash => unreachable!("handled above"),
        };
        write!(
            formatter,
            "{field} gap: expected {}, received {}",
            self.expected, self.received
        )
    }
}

impl Error for SequenceGap {}

#[derive(Debug)]
pub struct ReducedState {
    pub snapshot: ConsoleSnapshot,
    pub command_specs: HashMap<String, CommandSpecView>,
    indexes: HashMap<EventTarget, HashMap<String, usize>>,
}

impl ReducedState {
    fn new(snapshot: ConsoleSnapshot) -> Option<Self> {
        let command_specs = unique_command_specs(&snapshot.command_specs)?;
        let indexes = build_indexes(&snapshot)?;
        Some(Self {
            snapshot,
            command_specs,
            indexes,
        })
    }

    fn contains(&self, target: EventTarget, entity_id: &str) -> bool {
        self.indexes
            .get(&target)
            .is_some_and(|index| index.contains_key(entity_id))
    }

    fn apply_event(&mut self, state_version: u64, payload: EventPayload) {
        let EventPayload {
            entity_id,
            operation,
            entity,
            targets,
            presentation,
            ..
        } = payload;
        self.apply_presentation(state_version, presentation);
        for target in targets {
            self.apply_target(target, operation, entity_id.as_str(), entity.as_ref());
        }
    }

    fn apply_presentation(&mut self, state_version: u64, presentation: EventPresentation) {
        let EventPresentation {
            generated_at_utc,
            header,
            control_version,
            control_hash,
            window_omissions,
            impact,
            portfolio,
            orders,
            agents,
            models,
            timeline,
            risk,
            data,
            memory,
            system,
            portfolio_rank_source,
            timeline_hidden_event_count,
            model_active_model_id,
            model_rollback_model_id,
            model_approved_family,
            model_approved_strategy,
            model_approved_feature_set_id,
            model_final_regime,
            model_final_regime_confidence,
            model_regime_state,
            model_automatic_changes_blocked,
            model_block_reason,
            model_gates,
            risk_blocked_actions,
            risk_circuit_breaker,
            system_qwen,
            system_health,
        } = presentation;
        self.snapshot.shell.state_version = state_version;
        self.snapshot.shell.generated_at_utc = generated_at_utc;
        self.snapshot.shell.header = header;
        self.snapshot.control_version = control_version;
        self.snapshot.control_hash = control_hash;
        self.snapshot.window_omissions = window_omissions;

        macro_rules! replace_meta {
            ($view:expr, $meta:expr) => {{
                $view.freshness = $meta.freshness;
                $view.as_of_utc = $meta.as_of_utc;
                $view.source = $meta.source;
                $view.error = $meta.error;
            }};
        }
        replace_meta!(self.snapshot.impact, impact);
        replace_meta!(self.snapshot.portfolio, portfolio);
        replace_meta!(self.snapshot.orders, orders);
        replace_meta!(self.snapshot.agents, agents);
        replace_meta!(self.snapshot.models, models);
        replace_meta!(self.snapshot.timeline, timeline);
        replace_meta!(self.snapshot.risk, risk);
        replace_meta!(self.snapshot.data, data);
        replace_meta!(self.snapshot.memory, memory);
        replace_meta!(self.snapshot.system, system);
        self.snapshot.portfolio.rank_source = portfolio_rank_source;
        self.snapshot.timeline.hidden_event_count = timeline_hidden_event_count;
        self.snapshot.models.active_model_id = model_active_model_id;
        self.snapshot.models.rollback_model_id = model_rollback_model_id;
        self.snapshot.models.approved_family = model_approved_family;
        self.snapshot.models.approved_strategy = model_approved_strategy;
        self.snapshot.models.approved_feature_set_id = model_approved_feature_set_id;
        self.snapshot.models.final_regime = model_final_regime;
        self.snapshot.models.final_regime_confidence = model_final_regime_confidence;
        self.snapshot.models.regime_state = model_regime_state;
        self.snapshot.models.automatic_changes_blocked = model_automatic_changes_blocked;
        self.snapshot.models.block_reason = model_block_reason;
        self.snapshot.models.gates = model_gates;
        self.snapshot.risk.blocked_actions = risk_blocked_actions;
        self.snapshot.risk.circuit_breaker = risk_circuit_breaker;
        self.snapshot.system.qwen = system_qwen;
        self.snapshot.system.health = system_health;
    }

    fn apply_target(
        &mut self,
        target: EventTarget,
        operation: EventOperation,
        entity_id: &str,
        entity: Option<&EventEntity>,
    ) {
        let index = self.indexes.entry(target).or_default();
        match target {
            EventTarget::ShellAlerts
                if self.snapshot.shell.alerts.is_none() && operation == EventOperation::Remove => {}
            EventTarget::ShellAlerts => update_rows(
                self.snapshot.shell.alerts.get_or_insert_with(Vec::new),
                index,
                operation,
                entity_id,
                alert(entity),
                |row| row.alert_id.as_str(),
            ),
            EventTarget::ImpactHoldings => update_rows(
                &mut self.snapshot.impact.holdings,
                index,
                operation,
                entity_id,
                portfolio_row(entity),
                |row| row.symbol.as_str(),
            ),
            EventTarget::ImpactEvents => update_rows(
                &mut self.snapshot.impact.events,
                index,
                operation,
                entity_id,
                timeline_row(entity),
                |row| row.event_id.as_str(),
            ),
            EventTarget::ImpactAgents => update_rows(
                &mut self.snapshot.impact.agents,
                index,
                operation,
                entity_id,
                agent_card(entity),
                |row| row.work_id.as_str(),
            ),
            EventTarget::PortfolioRows => update_rows(
                &mut self.snapshot.portfolio.rows,
                index,
                operation,
                entity_id,
                portfolio_row(entity),
                |row| row.symbol.as_str(),
            ),
            EventTarget::PortfolioReturnsToday => update_rows(
                &mut self.snapshot.portfolio.returns_today,
                index,
                operation,
                entity_id,
                return_component_row(entity),
                return_component_id,
            ),
            EventTarget::PortfolioReturnsSinceRebalance => update_rows(
                &mut self.snapshot.portfolio.returns_since_rebalance,
                index,
                operation,
                entity_id,
                return_component_row(entity),
                return_component_id,
            ),
            EventTarget::PortfolioReturnsSinceStart => update_rows(
                &mut self.snapshot.portfolio.returns_since_start,
                index,
                operation,
                entity_id,
                return_component_row(entity),
                return_component_id,
            ),
            EventTarget::PortfolioMetrics => update_rows(
                &mut self.snapshot.portfolio.metrics,
                index,
                operation,
                entity_id,
                metric_row(entity),
                |row| row.metric_id.as_str(),
            ),
            EventTarget::PortfolioHistory => update_rows(
                &mut self.snapshot.portfolio.history,
                index,
                operation,
                entity_id,
                timeline_row(entity),
                |row| row.event_id.as_str(),
            ),
            EventTarget::OrdersRows => update_rows(
                &mut self.snapshot.orders.rows,
                index,
                operation,
                entity_id,
                order_row(entity),
                |row| row.order_id.as_str(),
            ),
            EventTarget::OrdersReconciliationAgents => update_rows(
                &mut self.snapshot.orders.reconciliation_agents,
                index,
                operation,
                entity_id,
                agent_card(entity),
                |row| row.work_id.as_str(),
            ),
            EventTarget::OrdersHistory => update_rows(
                &mut self.snapshot.orders.history,
                index,
                operation,
                entity_id,
                timeline_row(entity),
                |row| row.event_id.as_str(),
            ),
            EventTarget::AgentsRows => update_rows(
                &mut self.snapshot.agents.rows,
                index,
                operation,
                entity_id,
                agent_card(entity),
                |row| row.work_id.as_str(),
            ),
            EventTarget::AgentsHistory => update_rows(
                &mut self.snapshot.agents.history,
                index,
                operation,
                entity_id,
                timeline_row(entity),
                |row| row.event_id.as_str(),
            ),
            EventTarget::ModelsOpinions => update_rows(
                &mut self.snapshot.models.opinions,
                index,
                operation,
                entity_id,
                model_opinion_row(entity),
                |row| row.model_id.as_str(),
            ),
            EventTarget::ModelsCandidates => update_rows(
                &mut self.snapshot.models.candidates,
                index,
                operation,
                entity_id,
                candidate_row(entity),
                |row| row.candidate_id.as_str(),
            ),
            EventTarget::ModelsMetrics => update_rows(
                &mut self.snapshot.models.metrics,
                index,
                operation,
                entity_id,
                metric_row(entity),
                |row| row.metric_id.as_str(),
            ),
            EventTarget::ModelsEvidence => update_rows(
                &mut self.snapshot.models.evidence,
                index,
                operation,
                entity_id,
                evidence_row(entity),
                |row| row.evidence_id.as_str(),
            ),
            EventTarget::TimelineRows => update_rows(
                &mut self.snapshot.timeline.rows,
                index,
                operation,
                entity_id,
                timeline_row(entity),
                |row| row.event_id.as_str(),
            ),
            EventTarget::RiskLimits => update_rows(
                &mut self.snapshot.risk.limits,
                index,
                operation,
                entity_id,
                risk_limit_row(entity),
                |row| row.limit_id.as_str(),
            ),
            EventTarget::RiskApprovals => update_rows(
                &mut self.snapshot.risk.approvals,
                index,
                operation,
                entity_id,
                approval_row(entity),
                |row| row.approval_id.as_str(),
            ),
            EventTarget::RiskAlerts => update_rows(
                &mut self.snapshot.risk.alerts,
                index,
                operation,
                entity_id,
                alert(entity),
                |row| row.alert_id.as_str(),
            ),
            EventTarget::RiskMetrics => update_rows(
                &mut self.snapshot.risk.metrics,
                index,
                operation,
                entity_id,
                metric_row(entity),
                |row| row.metric_id.as_str(),
            ),
            EventTarget::DataSources => update_rows(
                &mut self.snapshot.data.sources,
                index,
                operation,
                entity_id,
                source_row(entity),
                |row| row.source_id.as_str(),
            ),
            EventTarget::DataEvidence => update_rows(
                &mut self.snapshot.data.evidence,
                index,
                operation,
                entity_id,
                evidence_row(entity),
                |row| row.evidence_id.as_str(),
            ),
            EventTarget::MemoryRows => update_rows(
                &mut self.snapshot.memory.rows,
                index,
                operation,
                entity_id,
                memory_row(entity),
                |row| row.memory_id.as_str(),
            ),
            EventTarget::MemoryHistory => update_rows(
                &mut self.snapshot.memory.history,
                index,
                operation,
                entity_id,
                timeline_row(entity),
                |row| row.event_id.as_str(),
            ),
            EventTarget::SystemServices => update_rows(
                &mut self.snapshot.system.services,
                index,
                operation,
                entity_id,
                service_row(entity),
                |row| row.service_id.as_str(),
            ),
            EventTarget::SystemMetrics => update_rows(
                &mut self.snapshot.system.metrics,
                index,
                operation,
                entity_id,
                metric_row(entity),
                |row| row.metric_id.as_str(),
            ),
            EventTarget::SystemRepositories => update_rows(
                &mut self.snapshot.system.repositories,
                index,
                operation,
                entity_id,
                repository_row(entity),
                |row| row.repository_id.as_str(),
            ),
        }
    }
}

#[derive(Debug, Default)]
pub struct SnapshotReducer {
    state: Option<ReducedState>,
    last_wire_sequence: Option<u64>,
    needs_snapshot: bool,
    selections: HashMap<EventTarget, String>,
}

impl SnapshotReducer {
    pub fn apply_snapshot(&mut self, snapshot: ConsoleSnapshot) -> ReduceOutcome {
        if let Some(current) = &self.state {
            let current_version = current.snapshot.shell.state_version;
            let incoming_version = snapshot.shell.state_version;
            if incoming_version < current_version {
                return ReduceOutcome::Ignored;
            }
            if incoming_version == current_version {
                if current.snapshot == snapshot {
                    self.needs_snapshot = false;
                    self.last_wire_sequence = None;
                    return ReduceOutcome::Ignored;
                }
                if !self.needs_snapshot {
                    self.needs_snapshot = true;
                    return ReduceOutcome::ResnapshotRequired;
                }
            }
            if invalid_control_pair(
                current.snapshot.control_version,
                &current.snapshot.control_hash,
                snapshot.control_version,
                &snapshot.control_hash,
            )
            .is_some()
            {
                self.needs_snapshot = true;
                return ReduceOutcome::ResnapshotRequired;
            }
        }
        let Some(state) = ReducedState::new(snapshot) else {
            self.needs_snapshot = true;
            return ReduceOutcome::ResnapshotRequired;
        };
        self.selections
            .retain(|target, entity_id| state.contains(*target, entity_id));
        self.state = Some(state);
        self.last_wire_sequence = None;
        self.needs_snapshot = false;
        ReduceOutcome::Changed
    }

    pub fn apply_event(&mut self, event: EventEnvelope) -> Result<ReduceOutcome, SequenceGap> {
        if !self.check_sequence(event.sequence)? {
            return Ok(ReduceOutcome::Ignored);
        }

        let current_state_version = self
            .state
            .as_ref()
            .expect("state checked above")
            .snapshot
            .shell
            .state_version;
        if event.state_version < current_state_version {
            self.needs_snapshot = true;
            return Err(SequenceGap {
                kind: GapKind::StateVersion,
                expected: current_state_version,
                received: event.state_version,
                resnapshot_required: true,
            });
        }
        let current = self.state.as_ref().expect("state checked above");
        if let Some(kind) = invalid_control_pair(
            current.snapshot.control_version,
            &current.snapshot.control_hash,
            event.payload.presentation.control_version,
            &event.payload.presentation.control_hash,
        ) {
            self.needs_snapshot = true;
            return Err(SequenceGap {
                kind,
                expected: current.snapshot.control_version,
                received: event.payload.presentation.control_version,
                resnapshot_required: true,
            });
        }

        let targets = event.payload.targets.clone();
        self.state
            .as_mut()
            .expect("state checked above")
            .apply_event(event.state_version, event.payload);
        self.last_wire_sequence = Some(event.sequence);
        for target in targets {
            if self.selections.get(&target).is_some_and(|entity_id| {
                !self
                    .state
                    .as_ref()
                    .expect("state checked above")
                    .contains(target, entity_id)
            }) {
                self.selections.remove(&target);
            }
        }
        Ok(ReduceOutcome::Changed)
    }

    /// Record an ordered non-event server envelope between presentation events.
    pub fn observe_sequence(&mut self, sequence: u64) -> Result<ReduceOutcome, SequenceGap> {
        if self.check_sequence(sequence)? {
            self.last_wire_sequence = Some(sequence);
        }
        Ok(ReduceOutcome::Ignored)
    }

    pub fn state(&self) -> &ReducedState {
        self.state
            .as_ref()
            .expect("snapshot reducer has not received a snapshot")
    }

    pub fn state_opt(&self) -> Option<&ReducedState> {
        self.state.as_ref()
    }

    pub fn needs_snapshot(&self) -> bool {
        self.needs_snapshot
    }

    pub fn select(&mut self, target: EventTarget, entity_id: &str) -> bool {
        if self
            .state
            .as_ref()
            .is_some_and(|state| state.contains(target, entity_id))
        {
            self.selections.insert(target, entity_id.to_owned());
            true
        } else {
            false
        }
    }

    pub fn selected_id(&self, target: EventTarget) -> Option<&str> {
        self.selections.get(&target).map(String::as_str)
    }

    fn check_sequence(&mut self, sequence: u64) -> Result<bool, SequenceGap> {
        let expected = self
            .last_wire_sequence
            .and_then(|last| last.checked_add(1))
            .unwrap_or(1);
        if self.state.is_none() || self.needs_snapshot || sequence == 0 {
            self.needs_snapshot = true;
            return Err(sequence_gap(expected, sequence));
        }
        let Some(last) = self.last_wire_sequence else {
            return Ok(true);
        };
        if sequence <= last {
            return Ok(false);
        }
        if sequence != expected {
            self.needs_snapshot = true;
            return Err(sequence_gap(expected, sequence));
        }
        Ok(true)
    }
}

fn sequence_gap(expected: u64, received: u64) -> SequenceGap {
    SequenceGap {
        kind: GapKind::EventSequence,
        expected,
        received,
        resnapshot_required: true,
    }
}

fn invalid_control_pair<T: PartialEq>(
    current_version: u64,
    current_hash: &T,
    incoming_version: u64,
    incoming_hash: &T,
) -> Option<GapKind> {
    if incoming_version < current_version {
        Some(GapKind::ControlVersion)
    } else if incoming_version == current_version && incoming_hash != current_hash {
        Some(GapKind::ControlHash)
    } else {
        None
    }
}

fn unique_command_specs(specs: &[CommandSpecView]) -> Option<HashMap<String, CommandSpecView>> {
    let mut result = HashMap::with_capacity(specs.len());
    for spec in specs {
        if result
            .insert(spec.command_type.as_str().to_owned(), spec.clone())
            .is_some()
        {
            return None;
        }
    }
    Some(result)
}

fn build_indexes(
    snapshot: &ConsoleSnapshot,
) -> Option<HashMap<EventTarget, HashMap<String, usize>>> {
    let mut result = HashMap::new();
    macro_rules! add {
        ($target:expr, $rows:expr, $key:expr) => {{
            result.insert($target, unique_index($rows, $key)?);
        }};
    }
    add!(
        EventTarget::ShellAlerts,
        snapshot.shell.alerts.as_deref().unwrap_or_default(),
        |row: &AlertRow| row.alert_id.as_str()
    );
    add!(
        EventTarget::ImpactHoldings,
        &snapshot.impact.holdings,
        |row: &PortfolioRow| row.symbol.as_str()
    );
    add!(
        EventTarget::ImpactEvents,
        &snapshot.impact.events,
        |row: &TimelineRow| row.event_id.as_str()
    );
    add!(
        EventTarget::ImpactAgents,
        &snapshot.impact.agents,
        |row: &AgentCard| row.work_id.as_str()
    );
    add!(
        EventTarget::PortfolioRows,
        &snapshot.portfolio.rows,
        |row: &PortfolioRow| row.symbol.as_str()
    );
    add!(
        EventTarget::PortfolioReturnsToday,
        &snapshot.portfolio.returns_today,
        return_component_id
    );
    add!(
        EventTarget::PortfolioReturnsSinceRebalance,
        &snapshot.portfolio.returns_since_rebalance,
        return_component_id
    );
    add!(
        EventTarget::PortfolioReturnsSinceStart,
        &snapshot.portfolio.returns_since_start,
        return_component_id
    );
    add!(
        EventTarget::PortfolioMetrics,
        &snapshot.portfolio.metrics,
        |row: &MetricRow| row.metric_id.as_str()
    );
    add!(
        EventTarget::PortfolioHistory,
        &snapshot.portfolio.history,
        |row: &TimelineRow| row.event_id.as_str()
    );
    add!(
        EventTarget::OrdersRows,
        &snapshot.orders.rows,
        |row: &OrderRow| row.order_id.as_str()
    );
    add!(
        EventTarget::OrdersReconciliationAgents,
        &snapshot.orders.reconciliation_agents,
        |row: &AgentCard| row.work_id.as_str()
    );
    add!(
        EventTarget::OrdersHistory,
        &snapshot.orders.history,
        |row: &TimelineRow| row.event_id.as_str()
    );
    add!(
        EventTarget::AgentsRows,
        &snapshot.agents.rows,
        |row: &AgentCard| row.work_id.as_str()
    );
    add!(
        EventTarget::AgentsHistory,
        &snapshot.agents.history,
        |row: &TimelineRow| row.event_id.as_str()
    );
    add!(
        EventTarget::ModelsOpinions,
        &snapshot.models.opinions,
        |row: &ModelOpinionRow| row.model_id.as_str()
    );
    add!(
        EventTarget::ModelsCandidates,
        &snapshot.models.candidates,
        |row: &CandidateRow| row.candidate_id.as_str()
    );
    add!(
        EventTarget::ModelsMetrics,
        &snapshot.models.metrics,
        |row: &MetricRow| row.metric_id.as_str()
    );
    add!(
        EventTarget::ModelsEvidence,
        &snapshot.models.evidence,
        |row: &EvidenceRow| row.evidence_id.as_str()
    );
    add!(
        EventTarget::TimelineRows,
        &snapshot.timeline.rows,
        |row: &TimelineRow| row.event_id.as_str()
    );
    add!(
        EventTarget::RiskLimits,
        &snapshot.risk.limits,
        |row: &RiskLimitRow| row.limit_id.as_str()
    );
    add!(
        EventTarget::RiskApprovals,
        &snapshot.risk.approvals,
        |row| row.approval_id.as_str()
    );
    add!(
        EventTarget::RiskAlerts,
        &snapshot.risk.alerts,
        |row: &AlertRow| row.alert_id.as_str()
    );
    add!(
        EventTarget::RiskMetrics,
        &snapshot.risk.metrics,
        |row: &MetricRow| row.metric_id.as_str()
    );
    add!(
        EventTarget::DataSources,
        &snapshot.data.sources,
        |row: &SourceRow| row.source_id.as_str()
    );
    add!(
        EventTarget::DataEvidence,
        &snapshot.data.evidence,
        |row: &EvidenceRow| row.evidence_id.as_str()
    );
    add!(
        EventTarget::MemoryRows,
        &snapshot.memory.rows,
        |row: &MemoryRow| row.memory_id.as_str()
    );
    add!(
        EventTarget::MemoryHistory,
        &snapshot.memory.history,
        |row: &TimelineRow| row.event_id.as_str()
    );
    add!(
        EventTarget::SystemServices,
        &snapshot.system.services,
        |row: &ServiceRow| row.service_id.as_str()
    );
    add!(
        EventTarget::SystemMetrics,
        &snapshot.system.metrics,
        |row: &MetricRow| row.metric_id.as_str()
    );
    add!(
        EventTarget::SystemRepositories,
        &snapshot.system.repositories,
        |row: &RepositoryRow| row.repository_id.as_str()
    );
    Some(result)
}

fn unique_index<T>(rows: &[T], key: impl Fn(&T) -> &str) -> Option<HashMap<String, usize>> {
    let mut index = HashMap::with_capacity(rows.len());
    for (position, row) in rows.iter().enumerate() {
        if index.insert(key(row).to_owned(), position).is_some() {
            return None;
        }
    }
    Some(index)
}

fn update_rows<T: Clone>(
    rows: &mut Vec<T>,
    index: &mut HashMap<String, usize>,
    operation: EventOperation,
    entity_id: &str,
    entity: Option<&T>,
    key: impl Fn(&T) -> &str + Copy,
) {
    match operation {
        EventOperation::Upsert => {
            let Some(entity) = entity else {
                return;
            };
            if let Some(position) = index.get(entity_id).copied() {
                rows[position] = entity.clone();
            } else {
                index.insert(entity_id.to_owned(), rows.len());
                rows.push(entity.clone());
            }
        }
        EventOperation::Remove => {
            let Some(position) = index.get(entity_id).copied() else {
                return;
            };
            rows.remove(position);
            *index = unique_index(rows, key).expect("event updates preserve unique entity IDs");
        }
    }
}

fn return_component_id(row: &ReturnComponentRow) -> &str {
    match row.component {
        ReturnComponent::Price => "price",
        ReturnComponent::Dividends => "dividends",
        ReturnComponent::CashInterest => "cash-interest",
        ReturnComponent::Fees => "fees",
        ReturnComponent::Sp500TotalReturn => "sp500-total-return",
    }
}

macro_rules! entity_accessor {
    ($name:ident, $variant:ident, $kind:ty) => {
        fn $name(entity: Option<&EventEntity>) -> Option<&$kind> {
            match entity {
                Some(EventEntity::$variant(row)) => Some(row),
                _ => None,
            }
        }
    };
}

entity_accessor!(portfolio_row, PortfolioRow, PortfolioRow);
entity_accessor!(agent_card, AgentCard, AgentCard);
entity_accessor!(timeline_row, TimelineRow, TimelineRow);
entity_accessor!(order_row, OrderRow, OrderRow);
entity_accessor!(model_opinion_row, ModelOpinionRow, ModelOpinionRow);
entity_accessor!(candidate_row, CandidateRow, CandidateRow);
entity_accessor!(risk_limit_row, RiskLimitRow, RiskLimitRow);
entity_accessor!(approval_row, ApprovalRow, crate::contract::ApprovalRow);
entity_accessor!(source_row, SourceRow, SourceRow);
entity_accessor!(evidence_row, EvidenceRow, EvidenceRow);
entity_accessor!(memory_row, MemoryRow, MemoryRow);
entity_accessor!(service_row, ServiceRow, ServiceRow);
entity_accessor!(repository_row, RepositoryRow, RepositoryRow);
entity_accessor!(metric_row, MetricRow, MetricRow);
entity_accessor!(return_component_row, ReturnComponentRow, ReturnComponentRow);
entity_accessor!(alert, AlertRow, AlertRow);
