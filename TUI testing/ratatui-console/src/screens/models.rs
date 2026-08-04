use ratatui::Frame;
use ratatui::layout::{Constraint, Layout, Rect};
use ratatui::style::Style;
use ratatui::text::Line;
use ratatui::widgets::{Block, Borders, Paragraph, Wrap};
use unicode_width::UnicodeWidthChar;

use crate::contract::{CandidateStatus, Freshness, ModelsView, StrategyName};
use crate::layout::DisplayMode;
use crate::screens::{DetailKind, ScreenState};
use crate::theme::Palette;
use crate::ui::format_eastern_time;

pub fn render_models(frame: &mut Frame<'_>, area: Rect, view: &ModelsView, state: &ScreenState) {
    let area = render_stale_notice(frame, area, view, state);
    let unavailable = unavailable_message(view.freshness, view.error.as_deref());
    if area.width < 120 {
        let index = state.narrow_panel % 3;
        let (title, lines) = match index {
            0 => (
                "MODEL OPINIONS / FINAL - PANEL 1/3",
                unavailable
                    .as_deref()
                    .map_or_else(|| opinion_lines(view, state), status_lines),
            ),
            1 => (
                "CANDIDATES - PANEL 2/3",
                unavailable
                    .as_deref()
                    .map_or_else(|| candidate_lines(view, state), status_lines),
            ),
            _ => (
                "EVIDENCE & METRICS - PANEL 3/3",
                unavailable
                    .as_deref()
                    .map_or_else(|| evidence_metric_lines(view, state), status_lines),
            ),
        };
        render_panel(
            frame,
            area,
            title,
            lines,
            state,
            true,
            models_scroll_offset(view, state, index),
        );
        return;
    }

    let panels = Layout::horizontal([
        Constraint::Percentage(32),
        Constraint::Percentage(43),
        Constraint::Percentage(25),
    ])
    .split(area);
    render_panel(
        frame,
        panels[0],
        focus_title(
            "MODEL OPINIONS / FINAL",
            state.narrow_panel.is_multiple_of(3),
        ),
        unavailable
            .as_deref()
            .map_or_else(|| opinion_lines(view, state), status_lines),
        state,
        state.narrow_panel.is_multiple_of(3),
        models_scroll_offset(view, state, 0),
    );
    render_panel(
        frame,
        panels[1],
        focus_title("CANDIDATES", state.narrow_panel % 3 == 1),
        unavailable
            .as_deref()
            .map_or_else(|| candidate_lines(view, state), status_lines),
        state,
        state.narrow_panel % 3 == 1,
        models_scroll_offset(view, state, 1),
    );
    render_panel(
        frame,
        panels[2],
        focus_title("EVIDENCE & METRICS", state.narrow_panel % 3 == 2),
        unavailable
            .as_deref()
            .map_or_else(|| evidence_metric_lines(view, state), status_lines),
        state,
        state.narrow_panel % 3 == 2,
        models_scroll_offset(view, state, 2),
    );
}

fn opinion_lines(view: &ModelsView, state: &ScreenState) -> Vec<Line<'static>> {
    let consensus = agreed_regime(view)
        .map(safe_text)
        .unwrap_or_else(|| "UNCERTAIN".to_owned());
    let mut lines = vec![
        Line::from("FINAL REGIME: UNAVAILABLE - controller truth not provided"),
        Line::from(format!("OPINION CONSENSUS: {consensus}")),
    ];
    if view.opinions.is_empty() {
        lines.push(Line::from("No model opinions reported."));
        return lines;
    }
    lines.push(Line::default());
    for opinion in &view.opinions {
        lines.push(Line::from(format!(
            "{}{} | {} | {:.1}%",
            marker(state, opinion.model_id.as_str(), DetailKind::ModelOpinion),
            safe_text(opinion.model_id.as_str()),
            safe_text(opinion.regime.as_str()),
            opinion.confidence * 100.0
        )));
        lines.push(Line::from(format_eastern_time(&opinion.as_of_utc)));
        add_spacing(&mut lines, state.display_mode);
    }
    lines
}

fn agreed_regime(view: &ModelsView) -> Option<&str> {
    let first = view.opinions.first()?.regime.as_str();
    view.opinions
        .iter()
        .all(|opinion| opinion.regime.as_str() == first)
        .then_some(first)
}

fn candidate_lines(view: &ModelsView, state: &ScreenState) -> Vec<Line<'static>> {
    if view.candidates.is_empty() {
        return vec![Line::from("No model candidates reported.")];
    }
    let mut lines = Vec::new();
    for candidate in &view.candidates {
        lines.push(Line::from(format!(
            "{}{} | FAMILY {} | STRATEGY {} | {}",
            marker(
                state,
                candidate.candidate_id.as_str(),
                DetailKind::ModelCandidate,
            ),
            safe_text(candidate.candidate_id.as_str()),
            safe_text(candidate.family.as_str()),
            strategy_label(candidate.strategy),
            format_eastern_time(&candidate.created_at_utc)
        )));
        lines.push(Line::from(format!(
            "STATUS {} | RETENTION POLICY {} | EVIDENCE {}",
            candidate_status(candidate.status),
            retention_policy_label(candidate.status),
            evidence_list(&candidate.evidence_ids)
        )));
        add_spacing(&mut lines, state.display_mode);
    }
    lines
}

fn evidence_metric_lines(view: &ModelsView, state: &ScreenState) -> Vec<Line<'static>> {
    let mut lines = vec![Line::from("METRICS")];
    if view.metrics.is_empty() {
        lines.push(Line::from("No metrics reported."));
    } else {
        for metric in &view.metrics {
            let value = metric
                .value
                .map_or_else(|| "UNAVAILABLE".to_owned(), |value| format!("{value:.4}"));
            let observed = metric
                .observed_at_utc
                .as_ref()
                .map_or_else(|| "UNAVAILABLE".to_owned(), format_eastern_time);
            let error = metric
                .error
                .as_deref()
                .map_or_else(|| "NONE".to_owned(), safe_text);
            lines.push(Line::from(format!(
                "{}{} | {value} {} | {} | {observed} | ERROR {error}",
                marker(state, metric.metric_id.as_str(), DetailKind::Metric),
                safe_text(metric.metric_id.as_str()),
                safe_text(metric.unit.as_str()),
                freshness_label(metric.freshness)
            )));
            add_spacing(&mut lines, state.display_mode);
        }
    }
    lines.push(Line::from("EVIDENCE"));
    if view.evidence.is_empty() {
        lines.push(Line::from("No evidence reported."));
    } else {
        for evidence in &view.evidence {
            lines.push(Line::from(format!(
                "{}{} | {} | SOURCE {}",
                marker(state, evidence.evidence_id.as_str(), DetailKind::Evidence),
                safe_text(evidence.evidence_id.as_str()),
                safe_text(evidence.evidence_type.as_str()),
                safe_text(evidence.source.as_str())
            )));
            lines.push(Line::from(format!(
                "{} | SHA256 {}",
                format_eastern_time(&evidence.created_at_utc),
                sha256_text(&evidence.sha256)
            )));
            add_spacing(&mut lines, state.display_mode);
        }
    }
    lines
}

fn add_spacing(lines: &mut Vec<Line<'static>>, display_mode: DisplayMode) {
    match display_mode {
        DisplayMode::Compact => {}
        DisplayMode::Standard => lines.push(Line::default()),
        DisplayMode::LargeText => {
            lines.push(Line::default());
            lines.push(Line::default());
        }
    }
}

fn models_scroll_offset(view: &ModelsView, state: &ScreenState, panel_index: usize) -> usize {
    let Some(selected_id) = state.selected_id.as_deref() else {
        return 0;
    };
    let spacing = match state.display_mode {
        DisplayMode::Compact => 0,
        DisplayMode::Standard => 1,
        DisplayMode::LargeText => 2,
    };
    match panel_index {
        0 if state.selected_kind == Some(DetailKind::ModelOpinion) => view
            .opinions
            .iter()
            .position(|row| row.model_id.as_str() == selected_id)
            .map_or(0, |index| 3 + index * (2 + spacing)),
        1 if state.selected_kind == Some(DetailKind::ModelCandidate) => view
            .candidates
            .iter()
            .position(|row| row.candidate_id.as_str() == selected_id)
            .map_or(0, |index| index * (2 + spacing)),
        2 if state.selected_kind == Some(DetailKind::Metric) => view
            .metrics
            .iter()
            .position(|row| row.metric_id.as_str() == selected_id)
            .map_or(0, |index| 1 + index * (1 + spacing)),
        2 if state.selected_kind == Some(DetailKind::Evidence) => {
            let evidence_start = if view.metrics.is_empty() {
                3
            } else {
                2 + view.metrics.len() * (1 + spacing)
            };
            view.evidence
                .iter()
                .position(|row| row.evidence_id.as_str() == selected_id)
                .map_or(0, |index| evidence_start + index * (2 + spacing))
        }
        _ => 0,
    }
}

fn is_selected(state: &ScreenState, id: &str, kind: DetailKind) -> bool {
    state.selected_id.as_deref() == Some(id) && state.selected_kind == Some(kind)
}

fn marker(state: &ScreenState, id: &str, kind: DetailKind) -> &'static str {
    if is_selected(state, id, kind) {
        "> "
    } else {
        "  "
    }
}

fn render_panel(
    frame: &mut Frame<'_>,
    area: Rect,
    title: impl Into<Line<'static>>,
    lines: Vec<Line<'static>>,
    state: &ScreenState,
    focused: bool,
    selected_scroll: usize,
) {
    let palette = state.theme.palette();
    frame.render_widget(
        Paragraph::new(lines)
            .style(base_style(palette))
            .wrap(Wrap { trim: false })
            .scroll((
                if focused {
                    u16::try_from(selected_scroll).unwrap_or(u16::MAX)
                } else {
                    0
                },
                0,
            ))
            .block(panel(title, palette)),
        area,
    );
}

fn focus_title(title: &'static str, focused: bool) -> Line<'static> {
    if focused {
        Line::from(format!("> {title}"))
    } else {
        Line::from(title)
    }
}

fn status_lines(message: &str) -> Vec<Line<'static>> {
    vec![Line::from(message.to_owned())]
}

fn render_stale_notice(
    frame: &mut Frame<'_>,
    area: Rect,
    view: &ModelsView,
    state: &ScreenState,
) -> Rect {
    if view.freshness != Freshness::Stale {
        return area;
    }
    let palette = state.theme.palette();
    let reason = view
        .error
        .as_deref()
        .map_or_else(|| "Reason unavailable.".to_owned(), safe_text);
    let sections = Layout::vertical([Constraint::Length(3), Constraint::Min(0)]).split(area);
    frame.render_widget(
        Paragraph::new(format!("[~] STALE - {reason}"))
            .style(base_style(palette))
            .wrap(Wrap { trim: true })
            .block(panel("SOURCE STATUS", palette)),
        sections[0],
    );
    sections[1]
}

fn unavailable_message(freshness: Freshness, error: Option<&str>) -> Option<String> {
    match freshness {
        Freshness::Fresh | Freshness::Stale => None,
        Freshness::Loading => Some("[..] LOADING - Waiting for controller data.".to_owned()),
        Freshness::Unavailable => Some(format!(
            "[?] UNAVAILABLE - {}",
            error.map_or_else(|| "Source reason unavailable.".to_owned(), safe_text)
        )),
    }
}

fn candidate_status(status: CandidateStatus) -> &'static str {
    match status {
        CandidateStatus::Training => "TRAINING",
        CandidateStatus::Evaluating => "EVALUATING",
        CandidateStatus::Passed => "PASSED",
        CandidateStatus::Failed => "FAILED",
        CandidateStatus::Rejected => "REJECTED",
        CandidateStatus::Active => "ACTIVE",
        CandidateStatus::Rollback => "ROLLBACK",
    }
}

fn retention_policy_label(status: CandidateStatus) -> &'static str {
    match status {
        CandidateStatus::Training | CandidateStatus::Evaluating => "UNAVAILABLE",
        CandidateStatus::Failed | CandidateStatus::Rejected => "30 DAYS",
        CandidateStatus::Passed => "90 DAYS",
        CandidateStatus::Active | CandidateStatus::Rollback => "PERMANENT",
    }
}

fn strategy_label(strategy: StrategyName) -> &'static str {
    match strategy {
        StrategyName::MlModel => "ml_model",
        StrategyName::Momentum => "momentum",
    }
}

fn freshness_label(freshness: Freshness) -> &'static str {
    match freshness {
        Freshness::Loading => "LOADING",
        Freshness::Fresh => "FRESH",
        Freshness::Stale => "STALE",
        Freshness::Unavailable => "UNAVAILABLE",
    }
}

fn evidence_list(ids: &[crate::contract::SafeId]) -> String {
    if ids.is_empty() {
        "NONE REPORTED".to_owned()
    } else {
        ids.iter()
            .map(|value| safe_text(value.as_str()))
            .collect::<Vec<_>>()
            .join(", ")
    }
}

fn sha256_text(value: &crate::contract::Sha256Hex) -> String {
    serde_json::to_value(value)
        .ok()
        .and_then(|value| value.as_str().map(safe_text))
        .unwrap_or_else(|| "UNAVAILABLE".to_owned())
}

fn panel<'a>(title: impl Into<Line<'a>>, palette: Palette) -> Block<'a> {
    Block::default()
        .borders(Borders::ALL)
        .title(title)
        .style(base_style(palette))
}

fn base_style(palette: Palette) -> Style {
    Style::default()
        .fg(palette.foreground)
        .bg(palette.background)
}

fn safe_text(value: &str) -> String {
    value
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
        .collect()
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
