use ratatui::style::Style;
use ratatui::text::Span;

use crate::contract::{AgentStage, AlertSeverity, Freshness};
use crate::theme::Palette;

pub fn alert_badge(severity: AlertSeverity, palette: Palette) -> Span<'static> {
    match severity {
        AlertSeverity::Info => badge("[i]", "INFO", base_style(palette)),
        AlertSeverity::Active => badge("[>]", "ACTIVE", palette.active),
        AlertSeverity::Waiting => badge("[~]", "WAITING", palette.waiting),
        AlertSeverity::Urgent => badge("[!]", "URGENT", palette.urgent),
        AlertSeverity::Resolved => badge("[OK]", "RESOLVED", palette.resolved),
    }
}

pub fn freshness_badge(freshness: Freshness, palette: Palette) -> Span<'static> {
    match freshness {
        Freshness::Loading => badge("[..]", "LOADING", palette.active),
        Freshness::Fresh => badge("[OK]", "FRESH", palette.resolved),
        Freshness::Stale => badge("[~]", "STALE", palette.waiting),
        Freshness::Unavailable => badge("[?]", "UNAVAILABLE", base_style(palette)),
    }
}

pub fn agent_stage_badge(stage: AgentStage, palette: Palette) -> Span<'static> {
    match stage {
        AgentStage::Backlog => badge("[ ]", "BACKLOG", base_style(palette)),
        AgentStage::Queued => badge("[+]", "QUEUED", base_style(palette)),
        AgentStage::Running => badge("[>]", "RUNNING", palette.active),
        AgentStage::Waiting => badge("[~]", "WAITING", palette.waiting),
        AgentStage::Done => badge("[OK]", "DONE", palette.resolved),
        AgentStage::Failed => badge("[!]", "FAILED", palette.urgent),
    }
}

fn badge(symbol: &str, word: &str, style: Style) -> Span<'static> {
    Span::styled(format!("{symbol} {word}"), style)
}

fn base_style(palette: Palette) -> Style {
    Style::default()
        .fg(palette.foreground)
        .bg(palette.background)
}
