use ratatui::Frame;
use ratatui::layout::Rect;
use ratatui::style::Style;
use ratatui::text::Line;
use ratatui::widgets::{Block, Borders, Paragraph, Wrap};
use unicode_width::UnicodeWidthChar;

use crate::contract::{
    AgentActivityKind, AgentCard, AgentStage, AlertSeverity, AlertView, ApprovalRow, ApprovalState,
    CandidateRow, CandidateStatus, ConsoleSnapshot, DataView, EvidenceRow, FillRow, Freshness,
    MemoryRow, MemoryStatus, MemoryView, MetricRow, ModelOpinionRow, ModelsView,
    OrderReconciliation, OrderRow, OrderSide, OrderStatus, OrdersView, RepositoryCheckState,
    RepositoryRow, RiskLimitRow, RiskLimitStatus, RiskReviewState, RiskView, ServiceRow,
    ServiceState, Sha256Hex, SourceRow, StrategyName, SystemView, TimelineRow, UtcTimestamp,
};
use crate::screens::{DetailKind, ScreenState};
use crate::state::Screen;
use crate::ui::format_eastern_time;

const MAX_FIELD_CHARS: usize = 256;
const MAX_LIST_ITEMS: usize = 8;
const MAX_LIST_ITEM_CHARS: usize = 48;
const MAX_FILL_ROWS: usize = 8;

struct DetailBody {
    title: &'static str,
    lines: Vec<String>,
}

impl DetailBody {
    fn new(title: &'static str, lines: Vec<String>) -> Self {
        Self { title, lines }
    }
}

pub fn render_direct_detail(
    frame: &mut Frame<'_>,
    area: Rect,
    snapshot: &ConsoleSnapshot,
    screen: Screen,
    state: &ScreenState,
) {
    let (title, lines) = direct_detail_content(snapshot, screen, state);

    let palette = state.theme.palette();
    let style = Style::default()
        .fg(palette.foreground)
        .bg(palette.background);
    frame.render_widget(
        Paragraph::new(lines.into_iter().map(Line::from).collect::<Vec<_>>())
            .style(style)
            .wrap(Wrap { trim: false })
            .scroll((u16::try_from(state.scroll_offset).unwrap_or(u16::MAX), 0))
            .block(
                Block::default()
                    .borders(Borders::ALL)
                    .title(title)
                    .style(style),
            ),
        area,
    );
}

#[allow(dead_code)]
pub(crate) fn direct_detail_line_count(
    snapshot: &ConsoleSnapshot,
    screen: Screen,
    state: &ScreenState,
    width: u16,
) -> usize {
    let (_, lines) = direct_detail_content(snapshot, screen, state);
    Paragraph::new(lines.into_iter().map(Line::from).collect::<Vec<_>>())
        .wrap(Wrap { trim: false })
        .line_count(width)
}

fn direct_detail_content(
    snapshot: &ConsoleSnapshot,
    screen: Screen,
    state: &ScreenState,
) -> (String, Vec<String>) {
    let selected_id = state.selected_id.as_deref();
    let selected_kind = state.selected_kind;
    match screen {
        Screen::Orders => compose_detail(
            "ORDERS",
            snapshot.orders.freshness,
            snapshot.orders.as_of_utc.as_ref(),
            snapshot.orders.source.as_str(),
            snapshot.orders.error.as_deref(),
            selected_id,
            orders_body(&snapshot.orders, selected_id, selected_kind),
        ),
        Screen::ModelsRegime => compose_detail(
            "MODELS",
            snapshot.models.freshness,
            snapshot.models.as_of_utc.as_ref(),
            snapshot.models.source.as_str(),
            snapshot.models.error.as_deref(),
            selected_id,
            models_body(&snapshot.models, selected_id, selected_kind),
        ),
        Screen::RiskApprovals => compose_detail(
            "RISK",
            snapshot.risk.freshness,
            snapshot.risk.as_of_utc.as_ref(),
            snapshot.risk.source.as_str(),
            snapshot.risk.error.as_deref(),
            selected_id,
            risk_body(&snapshot.risk, selected_id, selected_kind),
        ),
        Screen::DataEvidence => compose_detail(
            "DATA",
            snapshot.data.freshness,
            snapshot.data.as_of_utc.as_ref(),
            snapshot.data.source.as_str(),
            snapshot.data.error.as_deref(),
            selected_id,
            data_body(&snapshot.data, selected_id, selected_kind),
        ),
        Screen::Memory => compose_detail(
            "MEMORY",
            snapshot.memory.freshness,
            snapshot.memory.as_of_utc.as_ref(),
            snapshot.memory.source.as_str(),
            snapshot.memory.error.as_deref(),
            selected_id,
            memory_body(&snapshot.memory, selected_id, selected_kind),
        ),
        Screen::System => compose_detail(
            "SYSTEM",
            snapshot.system.freshness,
            snapshot.system.as_of_utc.as_ref(),
            snapshot.system.source.as_str(),
            snapshot.system.error.as_deref(),
            selected_id,
            system_body(&snapshot.system, selected_id, selected_kind),
        ),
        Screen::Impact | Screen::Portfolio | Screen::Agents | Screen::Timeline => (
            "DIRECT DETAIL UNAVAILABLE".to_owned(),
            vec![format!(
                "DIRECT DETAIL UNAVAILABLE - {} is rendered by its owning screen.",
                screen_label(screen)
            )],
        ),
    }
}

fn compose_detail(
    screen_label: &'static str,
    freshness: Freshness,
    as_of_utc: Option<&UtcTimestamp>,
    source: &str,
    error: Option<&str>,
    selected_id: Option<&str>,
    body: Option<DetailBody>,
) -> (String, Vec<String>) {
    let mut lines = vec![
        format!("SCREEN SOURCE: {}", safe_text(source)),
        format!("SCREEN FRESHNESS: {}", freshness_label(freshness)),
        format!(
            "SCREEN AS OF: {}",
            as_of_utc.map_or_else(|| "UNAVAILABLE".to_owned(), format_eastern_time)
        ),
        format!(
            "SCREEN ERROR: {}",
            error.map_or_else(|| "NONE".to_owned(), safe_text)
        ),
        String::new(),
    ];
    match (selected_id, body) {
        (Some(_), Some(body)) => {
            lines.extend(body.lines);
            (body.title.to_owned(), lines)
        }
        (Some(selected_id), None) => {
            lines.push(format!(
                "DIRECT DETAIL UNAVAILABLE - Selected ID {} is not present in the current {screen_label} snapshot.",
                safe_text(selected_id)
            ));
            ("DIRECT DETAIL UNAVAILABLE".to_owned(), lines)
        }
        (None, _) => {
            lines.push("DIRECT DETAIL UNAVAILABLE - No selected ID was provided.".to_owned());
            ("DIRECT DETAIL UNAVAILABLE".to_owned(), lines)
        }
    }
}

fn orders_body(
    view: &OrdersView,
    selected_id: Option<&str>,
    selected_kind: Option<DetailKind>,
) -> Option<DetailBody> {
    let selected_id = selected_id?;
    if kind_matches(selected_kind, DetailKind::Order)
        && let Some(order) = view
            .rows
            .iter()
            .find(|row| row.order_id.as_str() == selected_id)
    {
        return Some(order_body(order));
    }
    if kind_matches(selected_kind, DetailKind::Fill)
        && let Some((order, fill)) = view.rows.iter().find_map(|order| {
            order
                .fills
                .iter()
                .find(|fill| fill.fill_id.as_str() == selected_id)
                .map(|fill| (order, fill))
        })
    {
        return Some(fill_body(order, fill));
    }
    if kind_matches(selected_kind, DetailKind::Agent)
        && let Some(agent) = view
            .reconciliation_agents
            .iter()
            .find(|row| row.work_id.as_str() == selected_id)
    {
        return Some(agent_body(agent, &view.history));
    }
    if kind_matches(selected_kind, DetailKind::Event) {
        return view
            .history
            .iter()
            .find(|row| row.event_id.as_str() == selected_id)
            .map(|row| timeline_body("ORDER HISTORY DETAIL", row));
    }
    None
}

fn order_body(row: &OrderRow) -> DetailBody {
    let mut lines = vec![
        format!("ORDER ID: {}", safe_text(row.order_id.as_str())),
        format!(
            "SYMBOL: {} | SIDE: {} | QUANTITY: {}",
            safe_text(row.symbol.as_str()),
            order_side_label(row.side),
            row.quantity.as_str()
        ),
        format!(
            "STATUS: {} | RECONCILIATION: {}",
            order_status_label(row.status),
            reconciliation_label(row.reconciliation)
        ),
        format!(
            "SUBMITTED: {}",
            row.submitted_at_utc
                .as_ref()
                .map_or_else(|| "UNAVAILABLE".to_owned(), format_eastern_time)
        ),
        format!(
            "BROKER ORDER ID: {}",
            row.broker_order_id
                .as_deref()
                .map_or_else(|| "UNAVAILABLE".to_owned(), safe_text)
        ),
        format!(
            "EXPECTED PRICE: {} | ACTUAL PRICE: {}",
            row.expected_price
                .as_ref()
                .map_or("UNAVAILABLE", |value| value.as_str()),
            row.actual_price
                .as_ref()
                .map_or("UNAVAILABLE", |value| value.as_str())
        ),
        format!("FILLS ({})", row.fills.len()),
    ];
    if row.fills.is_empty() {
        lines.push("NONE REPORTED".to_owned());
    } else {
        lines.extend(row.fills.iter().take(MAX_FILL_ROWS).map(|fill| {
            format!(
                "{} | quantity {} | price {} | fee {} | {}",
                safe_text(fill.fill_id.as_str()),
                fill.quantity.as_str(),
                fill.price.as_str(),
                fill.fee.as_str(),
                format_eastern_time(&fill.filled_at_utc)
            )
        }));
        if row.fills.len() > MAX_FILL_ROWS {
            lines.push(format!(
                "FILLS OMITTED: {}",
                row.fills.len() - MAX_FILL_ROWS
            ));
        }
    }
    DetailBody::new("ORDER DETAIL", lines)
}

fn fill_body(order: &OrderRow, fill: &FillRow) -> DetailBody {
    DetailBody::new(
        "ORDER FILL DETAIL",
        vec![
            format!("FILL ID: {}", safe_text(fill.fill_id.as_str())),
            format!("ORDER ID: {}", safe_text(order.order_id.as_str())),
            format!("SYMBOL: {}", safe_text(order.symbol.as_str())),
            format!("QUANTITY: {}", fill.quantity.as_str()),
            format!("PRICE: {}", fill.price.as_str()),
            format!("FEE: {}", fill.fee.as_str()),
            format!("FILLED: {}", format_eastern_time(&fill.filled_at_utc)),
        ],
    )
}

fn agent_body(row: &AgentCard, history: &[TimelineRow]) -> DetailBody {
    let mut lines = vec![
        format!("WORK ID: {}", safe_text(row.work_id.as_str())),
        format!("AGENT: {}", safe_text(row.agent.as_str())),
        format!("TASK: {}", safe_text(row.title.as_str())),
        format!(
            "STAGE: {} | PRIORITY: {} | URGENT: {}",
            agent_stage_label(row.stage),
            row.priority.get(),
            yes_no(row.urgent)
        ),
        format!(
            "ELAPSED: {}",
            row.elapsed_seconds
                .map_or_else(|| "UNAVAILABLE".to_owned(), |value| format!("{value:.1}s"))
        ),
        format!(
            "MODEL: {}",
            row.model
                .as_deref()
                .map_or_else(|| "UNAVAILABLE".to_owned(), safe_text)
        ),
        format!(
            "AFFECTED AREAS: {}",
            bounded_list(
                row.affected_areas.iter().map(String::as_str),
                row.affected_areas.len()
            )
        ),
        format!(
            "SESSION ID: {}",
            row.session_id.as_ref().map_or_else(
                || "UNAVAILABLE".to_owned(),
                |value| safe_text(value.as_str())
            )
        ),
        format!(
            "CONTEXT: {}",
            row.context_percent
                .map_or_else(|| "UNAVAILABLE".to_owned(), |value| format!("{value:.1}%"))
        ),
        format!(
            "DETAIL NEXT CURSOR: {}",
            row.detail_next_cursor
                .as_ref()
                .map_or_else(|| "NONE".to_owned(), |value| safe_text(value.as_str()))
        ),
        format!(
            "CHAT AGENT: {}",
            row.chat_agent_id.as_ref().map_or_else(
                || "UNAVAILABLE".to_owned(),
                |value| safe_text(value.as_str())
            )
        ),
        format!("PLAN STEPS ({})", row.plan_steps.len()),
    ];
    if row.plan_steps.is_empty() {
        lines.push("UNAVAILABLE".to_owned());
    } else {
        lines.extend(
            row.plan_steps
                .iter()
                .take(MAX_LIST_ITEMS)
                .enumerate()
                .map(|(index, step)| format!("{}. {}", index + 1, safe_text(step.as_str()))),
        );
        if row.plan_steps.len() > MAX_LIST_ITEMS {
            lines.push(format!(
                "PLAN STEPS OMITTED: {}",
                row.plan_steps.len() - MAX_LIST_ITEMS
            ));
        }
    }
    lines.push(format!("ACTIVITY ({})", row.activity.len()));
    if row.activity.is_empty() {
        lines.push("UNAVAILABLE".to_owned());
    } else {
        lines.extend(row.activity.iter().take(MAX_LIST_ITEMS).map(|activity| {
            format!(
                "[{}] {} | {} | EVIDENCE {}",
                activity_kind_label(activity.kind),
                safe_text(activity.summary.as_str()),
                format_eastern_time(&activity.occurred_at_utc),
                bounded_list(
                    activity.evidence_ids.iter().map(|value| value.as_str()),
                    activity.evidence_ids.len()
                )
            )
        }));
        if row.activity.len() > MAX_LIST_ITEMS {
            lines.push(format!(
                "ACTIVITY OMITTED: {}",
                row.activity.len() - MAX_LIST_ITEMS
            ));
        }
    }
    lines.push(format!(
        "EVIDENCE: {}",
        bounded_list(
            row.evidence_ids.iter().map(|value| value.as_str()),
            row.evidence_ids.len()
        )
    ));
    let linked = history
        .iter()
        .filter(|event| event.work_id.as_ref() == Some(&row.work_id))
        .collect::<Vec<_>>();
    lines.push(format!("WORK-LINKED HISTORY ({})", linked.len()));
    if linked.is_empty() {
        lines.push("UNAVAILABLE".to_owned());
    } else {
        lines.extend(linked.iter().take(MAX_LIST_ITEMS).map(|event| {
            format!(
                "{} | {} | {} | EVIDENCE {}",
                safe_text(event.event_id.as_str()),
                safe_text(event.summary.as_str()),
                format_eastern_time(&event.occurred_at_utc),
                bounded_list(
                    event.evidence_ids.iter().map(|value| value.as_str()),
                    event.evidence_ids.len()
                )
            )
        }));
    }
    DetailBody::new("RECONCILIATION AGENT DETAIL", lines)
}

fn models_body(
    view: &ModelsView,
    selected_id: Option<&str>,
    selected_kind: Option<DetailKind>,
) -> Option<DetailBody> {
    let selected_id = selected_id?;
    if kind_matches(selected_kind, DetailKind::ModelOpinion)
        && let Some(row) = view
            .opinions
            .iter()
            .find(|row| row.model_id.as_str() == selected_id)
    {
        return Some(model_opinion_body(row));
    }
    if kind_matches(selected_kind, DetailKind::ModelCandidate)
        && let Some(row) = view
            .candidates
            .iter()
            .find(|row| row.candidate_id.as_str() == selected_id)
    {
        return Some(candidate_body(row));
    }
    if kind_matches(selected_kind, DetailKind::Metric)
        && let Some(row) = view
            .metrics
            .iter()
            .find(|row| row.metric_id.as_str() == selected_id)
    {
        return Some(metric_body("MODEL METRIC DETAIL", row));
    }
    if kind_matches(selected_kind, DetailKind::Evidence) {
        return view
            .evidence
            .iter()
            .find(|row| row.evidence_id.as_str() == selected_id)
            .map(|row| evidence_body("MODEL EVIDENCE DETAIL", row));
    }
    None
}

fn model_opinion_body(row: &ModelOpinionRow) -> DetailBody {
    DetailBody::new(
        "MODEL OPINION DETAIL",
        vec![
            format!("MODEL ID: {}", safe_text(row.model_id.as_str())),
            format!(
                "REGIME: {} | CONFIDENCE: {:.1}%",
                safe_text(row.regime.as_str()),
                row.confidence * 100.0
            ),
            format!("AS OF: {}", format_eastern_time(&row.as_of_utc)),
        ],
    )
}

fn candidate_body(row: &CandidateRow) -> DetailBody {
    DetailBody::new(
        "MODEL CANDIDATE DETAIL",
        vec![
            format!("CANDIDATE ID: {}", safe_text(row.candidate_id.as_str())),
            format!(
                "FAMILY: {} | STRATEGY: {} | STATUS: {}",
                safe_text(row.family.as_str()),
                strategy_label(row.strategy),
                candidate_status_label(row.status)
            ),
            format!("CREATED: {}", format_eastern_time(&row.created_at_utc)),
            format!(
                "FEATURE SET: {}",
                row.feature_set_id.as_ref().map_or_else(
                    || "UNAVAILABLE".to_owned(),
                    |value| safe_text(value.as_str())
                )
            ),
            format!(
                "DATA IDENTITY: {}",
                row.data_identity
                    .as_ref()
                    .map_or_else(|| "UNAVAILABLE".to_owned(), sha256_text)
            ),
            format!(
                "EVALUATION CONTRACT: {}",
                row.evaluation_contract
                    .as_ref()
                    .map_or_else(|| "UNAVAILABLE".to_owned(), sha256_text)
            ),
            format!(
                "STATUS REASON: {}",
                row.status_reason.as_ref().map_or_else(
                    || "UNAVAILABLE".to_owned(),
                    |value| safe_text(value.as_str())
                )
            ),
            format!(
                "STATUS AT: {}",
                row.status_at_utc
                    .as_ref()
                    .map_or_else(|| "UNAVAILABLE".to_owned(), format_eastern_time)
            ),
            format!(
                "EVIDENCE: {}",
                bounded_list(
                    row.evidence_ids.iter().map(|value| value.as_str()),
                    row.evidence_ids.len()
                )
            ),
        ],
    )
}

fn risk_body(
    view: &RiskView,
    selected_id: Option<&str>,
    selected_kind: Option<DetailKind>,
) -> Option<DetailBody> {
    let selected_id = selected_id?;
    if kind_matches(selected_kind, DetailKind::RiskLimit)
        && let Some(row) = view
            .limits
            .iter()
            .find(|row| row.limit_id.as_str() == selected_id)
    {
        return Some(risk_limit_body(row));
    }
    if kind_matches(selected_kind, DetailKind::Approval)
        && let Some(row) = view
            .approvals
            .iter()
            .find(|row| row.approval_id.as_str() == selected_id)
    {
        return Some(approval_body(row));
    }
    if kind_matches(selected_kind, DetailKind::Alert)
        && let Some(row) = view
            .alerts
            .iter()
            .find(|row| row.alert_id.as_str() == selected_id)
    {
        return Some(alert_body(row));
    }
    if kind_matches(selected_kind, DetailKind::Metric) {
        return view
            .metrics
            .iter()
            .find(|row| row.metric_id.as_str() == selected_id)
            .map(|row| metric_body("RISK METRIC DETAIL", row));
    }
    None
}

fn risk_limit_body(row: &RiskLimitRow) -> DetailBody {
    DetailBody::new(
        "RISK LIMIT DETAIL",
        vec![
            format!("LIMIT ID: {}", safe_text(row.limit_id.as_str())),
            format!("CURRENT: {}", row.current_value.as_str()),
            format!(
                "PROPOSED: {}",
                row.proposed_value
                    .as_ref()
                    .map_or("UNAVAILABLE", |value| value.as_str())
            ),
            format!("STATUS: {}", risk_limit_status_label(row.status)),
            format!(
                "PROPOSAL REASON: {}",
                row.proposal_reason.as_ref().map_or_else(
                    || "UNAVAILABLE".to_owned(),
                    |value| safe_text(value.as_str())
                )
            ),
            format!("REVIEW: {}", risk_review_state_label(row.review_state)),
            format!(
                "EVIDENCE: {}",
                bounded_list(
                    row.evidence_ids.iter().map(|value| value.as_str()),
                    row.evidence_ids.len()
                )
            ),
        ],
    )
}

fn approval_body(row: &ApprovalRow) -> DetailBody {
    let mut lines = vec![
        format!("APPROVAL ID: {}", safe_text(row.approval_id.as_str())),
        format!("RUN ID: {}", safe_text(row.run_id.as_str())),
        format!("CHECKPOINT ID: {}", safe_text(row.checkpoint_id.as_str())),
        format!("STATE: {}", approval_state_label(row.state)),
        format!(
            "REASON: {}",
            row.reason
                .as_deref()
                .map_or_else(|| "UNAVAILABLE".to_owned(), safe_text)
        ),
        format!("REQUESTED: {}", format_eastern_time(&row.requested_at_utc)),
        format!(
            "EVIDENCE: {}",
            bounded_list(
                row.evidence_ids.iter().map(|value| value.as_str()),
                row.evidence_ids.len()
            )
        ),
        format!(
            "AFFECTED SYMBOLS: {}",
            bounded_list(
                row.affected_symbols.iter().map(|value| value.as_str()),
                row.affected_symbols.len()
            )
        ),
        format!("WEIGHT CHANGES ({})", row.weight_changes.len()),
    ];
    if row.weight_changes.is_empty() {
        lines.push("NONE REPORTED".to_owned());
    } else {
        lines.extend(
            row.weight_changes
                .iter()
                .take(MAX_LIST_ITEMS)
                .map(|change| {
                    format!(
                        "{}: {:.1}% -> {:.1}%",
                        safe_text(change.symbol.as_str()),
                        change.current_weight * 100.0,
                        change.proposed_weight * 100.0
                    )
                }),
        );
    }
    lines.extend([
        format!(
            "RISKS: {}",
            bounded_list(
                row.risks.iter().map(|value| value.as_str()),
                row.risks.len()
            )
        ),
        format!(
            "EXPECTED CONSEQUENCES: {}",
            bounded_list(
                row.expected_consequences.iter().map(|value| value.as_str()),
                row.expected_consequences.len()
            )
        ),
        format!(
            "BASIS SHA256: {}",
            row.basis_sha256
                .as_ref()
                .map_or_else(|| "UNAVAILABLE".to_owned(), sha256_text)
        ),
        format!(
            "STALE REASON: {}",
            row.stale_reason
                .as_ref()
                .map_or_else(|| "NONE".to_owned(), |value| safe_text(value.as_str()))
        ),
    ]);
    DetailBody::new("APPROVAL DETAIL", lines)
}

fn alert_body(row: &AlertView) -> DetailBody {
    DetailBody::new(
        "RISK ALERT DETAIL",
        vec![
            format!("ALERT ID: {}", safe_text(row.alert_id.as_str())),
            format!("SEVERITY: {}", severity_label(row.severity)),
            format!("SUMMARY: {}", safe_text(row.summary.as_str())),
            format!("CREATED: {}", format_eastern_time(&row.created_at_utc)),
            format!(
                "RESOLVED: {}",
                row.resolved_at_utc.as_ref().map_or_else(
                    || {
                        if row.severity == AlertSeverity::Resolved {
                            "RESOLUTION TIME UNAVAILABLE".to_owned()
                        } else {
                            "NOT RESOLVED".to_owned()
                        }
                    },
                    format_eastern_time,
                )
            ),
        ],
    )
}

fn data_body(
    view: &DataView,
    selected_id: Option<&str>,
    selected_kind: Option<DetailKind>,
) -> Option<DetailBody> {
    let selected_id = selected_id?;
    if kind_matches(selected_kind, DetailKind::Source)
        && let Some(row) = view
            .sources
            .iter()
            .find(|row| row.source_id.as_str() == selected_id)
    {
        return Some(source_body(row));
    }
    if kind_matches(selected_kind, DetailKind::Evidence) {
        return view
            .evidence
            .iter()
            .find(|row| row.evidence_id.as_str() == selected_id)
            .map(|row| evidence_body("DATA EVIDENCE DETAIL", row));
    }
    None
}

fn source_body(row: &SourceRow) -> DetailBody {
    DetailBody::new(
        "DATA SOURCE DETAIL",
        vec![
            format!("SOURCE ID: {}", safe_text(row.source_id.as_str())),
            format!("FRESHNESS: {}", freshness_label(row.freshness)),
            format!(
                "AS OF: {}",
                row.as_of_utc
                    .as_ref()
                    .map_or_else(|| "UNAVAILABLE".to_owned(), format_eastern_time)
            ),
            format!(
                "AGE: {}",
                row.age_seconds
                    .map_or_else(|| "UNAVAILABLE".to_owned(), |value| format!("{value:.1}s"))
            ),
            format!(
                "COVERAGE: {}",
                row.coverage
                    .as_deref()
                    .map_or_else(|| "UNAVAILABLE".to_owned(), safe_text)
            ),
            format!(
                "ERROR: {}",
                row.error
                    .as_deref()
                    .map_or_else(|| "NONE".to_owned(), safe_text)
            ),
            format!(
                "CONSUMERS: {}",
                bounded_list(
                    row.consumers.iter().map(|value| value.as_str()),
                    row.consumers.len()
                )
            ),
            format!(
                "DEPENDENCIES: {}",
                bounded_list(
                    row.dependencies.iter().map(|value| value.as_str()),
                    row.dependencies.len()
                )
            ),
        ],
    )
}

fn evidence_body(title: &'static str, row: &EvidenceRow) -> DetailBody {
    let mut lines = vec![
        format!("EVIDENCE ID: {}", safe_text(row.evidence_id.as_str())),
        format!("TYPE: {}", safe_text(row.evidence_type.as_str())),
        format!("SOURCE: {}", safe_text(row.source.as_str())),
        format!("CREATED: {}", format_eastern_time(&row.created_at_utc)),
        format!("SHA256: {}", sha256_text(&row.sha256)),
        format!("SYMBOLS: {}", id_list(&row.symbols)),
        format!("AGENTS: {}", id_list(&row.agent_ids)),
        format!("MODELS: {}", id_list(&row.model_ids)),
        format!("ORDERS: {}", id_list(&row.order_ids)),
        format!("APPROVALS: {}", id_list(&row.approval_ids)),
        format!("SOURCES: {}", id_list(&row.source_ids)),
        format!(
            "RAW LOG ID: {}",
            row.raw_log_id.as_ref().map_or_else(
                || "UNAVAILABLE".to_owned(),
                |value| safe_text(value.as_str())
            )
        ),
        format!("RAW LOG EXCERPT ({})", row.raw_log_excerpt.len()),
    ];
    if row.raw_log_excerpt.is_empty() {
        lines.push("UNAVAILABLE".to_owned());
    } else {
        lines.extend(
            row.raw_log_excerpt
                .iter()
                .take(MAX_LIST_ITEMS)
                .enumerate()
                .map(|(index, value)| {
                    format!(
                        "{}. {}",
                        index + 1,
                        safe_text_with_limit(value.as_str(), MAX_FIELD_CHARS)
                    )
                }),
        );
        if row.raw_log_excerpt.len() > MAX_LIST_ITEMS {
            lines.push(format!(
                "RAW LOG LINES OMITTED: {}",
                row.raw_log_excerpt.len() - MAX_LIST_ITEMS
            ));
        }
    }
    lines.extend([
        format!("TRUNCATED: {}", yes_no(row.raw_log_truncated)),
        format!(
            "NEXT CURSOR: {}",
            row.raw_log_next_cursor
                .as_ref()
                .map_or_else(|| "NONE".to_owned(), |value| safe_text(value.as_str()))
        ),
    ]);
    DetailBody::new(title, lines)
}

fn memory_body(
    view: &MemoryView,
    selected_id: Option<&str>,
    selected_kind: Option<DetailKind>,
) -> Option<DetailBody> {
    let selected_id = selected_id?;
    if kind_matches(selected_kind, DetailKind::Memory)
        && let Some(row) = view
            .rows
            .iter()
            .find(|row| row.memory_id.as_str() == selected_id)
    {
        return Some(memory_row_body(row));
    }
    if kind_matches(selected_kind, DetailKind::Event) {
        return view
            .history
            .iter()
            .find(|row| row.event_id.as_str() == selected_id)
            .map(|row| timeline_body("MEMORY HISTORY DETAIL", row));
    }
    None
}

fn memory_row_body(row: &MemoryRow) -> DetailBody {
    DetailBody::new(
        "MEMORY DETAIL",
        vec![
            format!("MEMORY ID: {}", safe_text(row.memory_id.as_str())),
            format!("STATUS: {}", memory_status_label(row.status)),
            format!("SUMMARY: {}", safe_text(row.summary.as_str())),
            format!("UPDATED: {}", format_eastern_time(&row.updated_at_utc)),
            format!(
                "EVIDENCE: {}",
                bounded_list(
                    row.evidence_ids.iter().map(|value| value.as_str()),
                    row.evidence_ids.len()
                )
            ),
            format!("USED BY AGENTS: {}", id_list(&row.used_by_agents)),
            format!(
                "CHANGE REASON: {}",
                row.change_reason.as_ref().map_or_else(
                    || "UNAVAILABLE".to_owned(),
                    |value| safe_text(value.as_str())
                )
            ),
        ],
    )
}

fn timeline_body(title: &'static str, row: &TimelineRow) -> DetailBody {
    let links = [
        ("AGENT", row.agent_id.as_ref()),
        ("SYMBOL", row.symbol.as_ref()),
        ("MODEL", row.model_id.as_ref()),
        ("APPROVAL", row.approval_id.as_ref()),
        ("ORDER", row.order_id.as_ref()),
        ("WORK", row.work_id.as_ref()),
    ]
    .into_iter()
    .filter_map(|(label, value)| value.map(|value| format!("{label}: {}", value.as_str())))
    .collect::<Vec<_>>();
    DetailBody::new(
        title,
        vec![
            format!("EVENT ID: {}", safe_text(row.event_id.as_str())),
            format!("OCCURRED: {}", format_eastern_time(&row.occurred_at_utc)),
            format!(
                "IMPACT: {} | SEVERITY: {}",
                yes_no(row.impact),
                severity_label(row.severity)
            ),
            format!("SUMMARY: {}", safe_text(row.summary.as_str())),
            format!(
                "LINKS: {}",
                if links.is_empty() {
                    "NONE REPORTED".to_owned()
                } else {
                    bounded_list(links.iter().map(String::as_str), links.len())
                }
            ),
            format!(
                "EVIDENCE: {}",
                bounded_list(
                    row.evidence_ids.iter().map(|value| value.as_str()),
                    row.evidence_ids.len()
                )
            ),
        ],
    )
}

fn system_body(
    view: &SystemView,
    selected_id: Option<&str>,
    selected_kind: Option<DetailKind>,
) -> Option<DetailBody> {
    let selected_id = selected_id?;
    if kind_matches(selected_kind, DetailKind::Service)
        && let Some(row) = view
            .services
            .iter()
            .find(|row| row.service_id.as_str() == selected_id)
    {
        return Some(service_body(row));
    }
    if kind_matches(selected_kind, DetailKind::Metric)
        && let Some(row) = view
            .metrics
            .iter()
            .find(|row| row.metric_id.as_str() == selected_id)
    {
        return Some(metric_body("SYSTEM METRIC DETAIL", row));
    }
    if kind_matches(selected_kind, DetailKind::Repository) {
        return view
            .repositories
            .iter()
            .find(|row| row.repository_id.as_str() == selected_id)
            .map(repository_body);
    }
    None
}

fn kind_matches(selected: Option<DetailKind>, expected: DetailKind) -> bool {
    selected.is_none_or(|selected| selected == expected)
}

fn service_body(row: &ServiceRow) -> DetailBody {
    DetailBody::new(
        "SERVICE DETAIL",
        vec![
            format!("SERVICE ID: {}", safe_text(row.service_id.as_str())),
            format!("STATE: {}", service_state_label(row.state)),
            format!(
                "HEALTH REASON: {}",
                row.health_reason
                    .as_deref()
                    .map_or_else(|| "NONE".to_owned(), safe_text)
            ),
            format!("OBSERVED: {}", format_eastern_time(&row.observed_at_utc)),
        ],
    )
}

fn metric_body(title: &'static str, row: &MetricRow) -> DetailBody {
    DetailBody::new(
        title,
        vec![
            format!("METRIC ID: {}", safe_text(row.metric_id.as_str())),
            format!(
                "VALUE: {} {}",
                row.value
                    .map_or_else(|| "UNAVAILABLE".to_owned(), |value| format!("{value:.4}")),
                safe_text(row.unit.as_str())
            ),
            format!("FRESHNESS: {}", freshness_label(row.freshness)),
            format!(
                "OBSERVED: {}",
                row.observed_at_utc
                    .as_ref()
                    .map_or_else(|| "UNAVAILABLE".to_owned(), format_eastern_time)
            ),
            format!(
                "ERROR: {}",
                row.error
                    .as_deref()
                    .map_or_else(|| "NONE".to_owned(), safe_text)
            ),
        ],
    )
}

fn repository_body(row: &RepositoryRow) -> DetailBody {
    let mut lines = vec![
        format!("REPOSITORY ID: {}", safe_text(row.repository_id.as_str())),
        format!("FRESHNESS: {}", freshness_label(row.freshness)),
        format!(
            "AS OF: {}",
            row.as_of_utc
                .as_ref()
                .map_or_else(|| "UNAVAILABLE".to_owned(), format_eastern_time)
        ),
        format!("SOURCE: {}", safe_text(row.source.as_str())),
        format!(
            "ERROR: {}",
            row.error
                .as_deref()
                .map_or_else(|| "NONE".to_owned(), safe_text)
        ),
        format!(
            "BRANCH: {}",
            row.branch.as_ref().map_or_else(
                || "UNAVAILABLE".to_owned(),
                |value| safe_text(value.as_str())
            )
        ),
        format!(
            "REVISION: {}",
            row.revision.as_ref().map_or_else(
                || "UNAVAILABLE".to_owned(),
                |value| safe_text(value.as_str())
            )
        ),
        format!(
            "CLEAN: {} | UNPUSHED COMMITS: {}",
            row.clean.map_or("UNAVAILABLE", yes_no),
            row.unpushed_commit_count
                .map_or_else(|| "UNAVAILABLE".to_owned(), |value| value.to_string())
        ),
        format!(
            "WORKTREES: {}",
            bounded_list(
                row.worktrees.iter().map(|value| value.as_str()),
                row.worktrees.len()
            )
        ),
        format!("REPOSITORY CHECKS ({})", row.checks.len()),
    ];
    if row.checks.is_empty() {
        lines.push("UNAVAILABLE".to_owned());
    } else {
        lines.extend(row.checks.iter().take(MAX_LIST_ITEMS).map(|check| {
            format!(
                "{} | {} | {} | REASON {}",
                safe_text(check.check_id.as_str()),
                repository_check_state_label(check.state),
                check
                    .observed_at_utc
                    .as_ref()
                    .map_or_else(|| "UNAVAILABLE".to_owned(), format_eastern_time),
                check
                    .reason
                    .as_ref()
                    .map_or_else(|| "NONE".to_owned(), |value| safe_text(value.as_str()))
            )
        }));
    }
    DetailBody::new("REPOSITORY DETAIL", lines)
}

fn id_list(values: &[crate::contract::SafeId]) -> String {
    bounded_list(values.iter().map(|value| value.as_str()), values.len())
}

fn bounded_list<'a>(values: impl Iterator<Item = &'a str>, total: usize) -> String {
    let mut items = values
        .take(MAX_LIST_ITEMS)
        .map(|value| safe_text_with_limit(value, MAX_LIST_ITEM_CHARS))
        .collect::<Vec<_>>();
    if total > items.len() {
        items.push(format!("+{} more", total - items.len()));
    }
    if items.is_empty() {
        "NONE REPORTED".to_owned()
    } else {
        items.join(", ")
    }
}

fn safe_text(value: &str) -> String {
    safe_text_with_limit(value, MAX_FIELD_CHARS)
}

fn safe_text_with_limit(value: &str, maximum: usize) -> String {
    let sanitized = value
        .chars()
        .map(|character| {
            if character.is_control()
                || is_unicode_format(character)
                || character.width().unwrap_or(0) == 0
            {
                '?'
            } else {
                character
            }
        })
        .collect::<String>();
    if sanitized.chars().count() <= maximum {
        return sanitized;
    }
    let retained = maximum.saturating_sub(3);
    format!(
        "{}...",
        sanitized.chars().take(retained).collect::<String>()
    )
}

fn sha256_text(value: &Sha256Hex) -> String {
    serde_json::to_value(value)
        .ok()
        .and_then(|value| value.as_str().map(str::to_owned))
        .unwrap_or_else(|| "UNAVAILABLE".to_owned())
}

fn screen_label(screen: Screen) -> &'static str {
    match screen {
        Screen::Impact => "IMPACT",
        Screen::Portfolio => "PORTFOLIO",
        Screen::Orders => "ORDERS",
        Screen::Agents => "AGENTS",
        Screen::ModelsRegime => "MODELS",
        Screen::Timeline => "TIMELINE",
        Screen::RiskApprovals => "RISK",
        Screen::DataEvidence => "DATA",
        Screen::Memory => "MEMORY",
        Screen::System => "SYSTEM",
    }
}

fn freshness_label(value: Freshness) -> &'static str {
    match value {
        Freshness::Loading => "LOADING",
        Freshness::Fresh => "FRESH",
        Freshness::Stale => "STALE",
        Freshness::Unavailable => "UNAVAILABLE",
    }
}

fn order_side_label(value: OrderSide) -> &'static str {
    match value {
        OrderSide::Buy => "BUY",
        OrderSide::Sell => "SELL",
    }
}

fn order_status_label(value: OrderStatus) -> &'static str {
    match value {
        OrderStatus::Proposed => "PROPOSED",
        OrderStatus::Approved => "APPROVED",
        OrderStatus::Submitted => "SUBMITTED",
        OrderStatus::Partial => "PARTIAL",
        OrderStatus::Filled => "FILLED",
        OrderStatus::Rejected => "REJECTED",
        OrderStatus::Cancelled => "CANCELLED",
    }
}

fn reconciliation_label(value: OrderReconciliation) -> &'static str {
    match value {
        OrderReconciliation::Pending => "PENDING",
        OrderReconciliation::Matched => "MATCHED",
        OrderReconciliation::Mismatch => "MISMATCH",
        OrderReconciliation::Unavailable => "UNAVAILABLE",
    }
}

fn agent_stage_label(value: AgentStage) -> &'static str {
    match value {
        AgentStage::Backlog => "BACKLOG",
        AgentStage::Queued => "QUEUED",
        AgentStage::Running => "RUNNING",
        AgentStage::Waiting => "WAITING",
        AgentStage::Done => "DONE",
        AgentStage::Failed => "FAILED",
    }
}

fn activity_kind_label(value: AgentActivityKind) -> &'static str {
    match value {
        AgentActivityKind::Stage => "STAGE",
        AgentActivityKind::Tool => "TOOL",
        AgentActivityKind::File => "FILE",
        AgentActivityKind::Decision => "DECISION",
        AgentActivityKind::Error => "ERROR",
        AgentActivityKind::Result => "RESULT",
    }
}

fn strategy_label(value: StrategyName) -> &'static str {
    match value {
        StrategyName::MlModel => "ml_model",
        StrategyName::Momentum => "momentum",
    }
}

fn candidate_status_label(value: CandidateStatus) -> &'static str {
    match value {
        CandidateStatus::Training => "TRAINING",
        CandidateStatus::Evaluating => "EVALUATING",
        CandidateStatus::Passed => "PASSED",
        CandidateStatus::Failed => "FAILED",
        CandidateStatus::Rejected => "REJECTED",
        CandidateStatus::Active => "ACTIVE",
        CandidateStatus::Rollback => "ROLLBACK",
    }
}

fn risk_limit_status_label(value: RiskLimitStatus) -> &'static str {
    match value {
        RiskLimitStatus::Within => "WITHIN",
        RiskLimitStatus::Violated => "VIOLATED",
        RiskLimitStatus::Pending => "PENDING",
        RiskLimitStatus::Unavailable => "UNAVAILABLE",
    }
}

fn risk_review_state_label(value: RiskReviewState) -> &'static str {
    match value {
        RiskReviewState::NotRequired => "NOT REQUIRED",
        RiskReviewState::Pending => "PENDING",
        RiskReviewState::Approved => "APPROVED",
        RiskReviewState::Rejected => "REJECTED",
        RiskReviewState::Unavailable => "UNAVAILABLE",
    }
}

fn approval_state_label(value: ApprovalState) -> &'static str {
    match value {
        ApprovalState::Pending => "PENDING",
        ApprovalState::Approved => "APPROVED",
        ApprovalState::Held => "HELD",
        ApprovalState::Rejected => "REJECTED",
        ApprovalState::Rework => "REWORK",
        ApprovalState::Stale => "STALE",
    }
}

fn severity_label(value: AlertSeverity) -> &'static str {
    match value {
        AlertSeverity::Info => "INFO",
        AlertSeverity::Active => "ACTIVE",
        AlertSeverity::Waiting => "WAITING",
        AlertSeverity::Urgent => "URGENT",
        AlertSeverity::Resolved => "RESOLVED",
    }
}

fn memory_status_label(value: MemoryStatus) -> &'static str {
    match value {
        MemoryStatus::Core => "CORE",
        MemoryStatus::Archived => "ARCHIVED",
    }
}

fn service_state_label(value: ServiceState) -> &'static str {
    match value {
        ServiceState::Running => "RUNNING",
        ServiceState::Paused => "PAUSED",
        ServiceState::Stopped => "STOPPED",
        ServiceState::Failed => "FAILED",
        ServiceState::Unavailable => "UNAVAILABLE",
    }
}

fn repository_check_state_label(value: RepositoryCheckState) -> &'static str {
    match value {
        RepositoryCheckState::Pass => "PASS",
        RepositoryCheckState::Fail => "FAIL",
        RepositoryCheckState::Running => "RUNNING",
        RepositoryCheckState::Unavailable => "UNAVAILABLE",
    }
}

fn yes_no(value: bool) -> &'static str {
    if value { "YES" } else { "NO" }
}

fn is_unicode_format(character: char) -> bool {
    matches!(
        character as u32,
        0x00AD
            | 0x0600..=0x0605
            | 0x061C
            | 0x06DD
            | 0x070F
            | 0x0890..=0x0891
            | 0x08E2
            | 0x180E
            | 0x200B..=0x200F
            | 0x202A..=0x202E
            | 0x2060..=0x2064
            | 0x2066..=0x206F
            | 0xFEFF
            | 0xFFF9..=0xFFFB
            | 0x110BD
            | 0x110CD
            | 0x13430..=0x1343F
            | 0x1BCA0..=0x1BCA3
            | 0x1D173..=0x1D17A
            | 0xE0001
            | 0xE0020..=0xE007F
    )
}
