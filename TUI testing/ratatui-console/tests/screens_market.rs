use std::path::PathBuf;

use ratatui::Terminal;
use ratatui::backend::TestBackend;
use ratatui::buffer::Buffer;
use serde_json::{Value, json};
use vesper_ratatui_console::ConsoleSnapshot;
use vesper_ratatui_console::contract::AssetType;
use vesper_ratatui_console::input::InputEvent;
use vesper_ratatui_console::layout::DisplayMode;
use vesper_ratatui_console::screens::impact::render_impact;
use vesper_ratatui_console::screens::orders::render_orders;
use vesper_ratatui_console::screens::portfolio::render_portfolio;
use vesper_ratatui_console::screens::{PerformancePeriod, ScreenState};
use vesper_ratatui_console::state::{AppState, LocalMode, Screen};
use vesper_ratatui_console::theme::Theme;
use vesper_ratatui_console::ui;

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
    .expect("strict snapshot JSON")
}

fn snapshot(value: Value) -> ConsoleSnapshot {
    serde_json::from_value(value).expect("strict console snapshot")
}

fn render(width: u16, height: u16, draw: impl FnOnce(&mut ratatui::Frame<'_>)) -> Buffer {
    let backend = TestBackend::new(width, height);
    let mut terminal = Terminal::new(backend).expect("test terminal");
    terminal.draw(draw).expect("draw market screen");
    terminal.backend().buffer().clone()
}

fn buffer_text(buffer: &Buffer) -> String {
    let area = buffer.area;
    (area.y..area.y + area.height)
        .map(|y| {
            (area.x..area.x + area.width)
                .map(|x| buffer[(x, y)].symbol())
                .collect::<String>()
        })
        .collect::<Vec<_>>()
        .join("\n")
}

fn text_position(buffer: &Buffer, needle: &str) -> Option<(u16, u16)> {
    let width = u16::try_from(needle.chars().count()).ok()?;
    for y in buffer.area.y..buffer.area.y + buffer.area.height {
        for x in buffer.area.x..buffer.area.x + buffer.area.width.saturating_sub(width) {
            let candidate = (0..width)
                .map(|offset| buffer[(x + offset, y)].symbol())
                .collect::<String>();
            if candidate == needle {
                return Some((x, y));
            }
        }
    }
    None
}

fn state() -> ScreenState {
    ScreenState {
        theme: Theme::WarmWhite,
        display_mode: DisplayMode::Standard,
        ..ScreenState::default()
    }
}

#[test]
fn impact_uses_portfolio_dominant_wide_layout_and_narrow_panel_focus() {
    let snapshot = snapshot(snapshot_value());
    let wide = render(140, 36, |frame| {
        render_impact(frame, frame.area(), &snapshot.impact, &state());
    });
    let wide = buffer_text(&wide);
    assert!(wide.contains("HOLDINGS"));
    assert!(wide.contains("IMPACT FEED"));
    assert!(wide.contains("AGENT WORK"));
    assert!(wide.contains("AAPL"));
    assert!(wide.find("HOLDINGS").unwrap() < wide.find("IMPACT FEED").unwrap());

    let narrow_state = ScreenState {
        narrow_panel: 1,
        ..state()
    };
    let narrow = render(72, 24, |frame| {
        render_impact(frame, frame.area(), &snapshot.impact, &narrow_state);
    });
    let narrow = buffer_text(&narrow);
    assert!(narrow.contains("IMPACT FEED"));
    assert!(narrow.contains("PANEL 2/3"));
    assert!(!narrow.contains("AGENT WORK"));

    let large = ScreenState {
        display_mode: DisplayMode::LargeText,
        ..state()
    };
    let tiny = buffer_text(&render(80, 3, |frame| {
        render_impact(frame, frame.area(), &snapshot.impact, &large);
    }));
    assert!(
        tiny.contains("AAPL"),
        "tiny Large Text must keep real data\n{tiny}"
    );
}

#[test]
fn portfolio_preserves_controller_row_order_until_confirmed_execution() {
    let mut value = snapshot_value();
    let mut msft = value["portfolio"]["rows"][0].clone();
    msft["symbol"] = json!("MSFT");
    msft["current_weight"] = json!(0.2);
    msft["proposed_weight"] = json!(0.8);
    msft["confirmed_rank"] = Value::Null;
    value["portfolio"]["rows"]
        .as_array_mut()
        .unwrap()
        .push(msft.clone());
    let proposed = snapshot(value.clone());
    let proposed_text = buffer_text(&render(130, 32, |frame| {
        render_portfolio(frame, frame.area(), &proposed.portfolio, &state());
    }));
    assert!(proposed_text.find("AAPL").unwrap() < proposed_text.find("MSFT").unwrap());

    value["portfolio"]["rows"] = json!([msft, value["portfolio"]["rows"][0].clone()]);
    let confirmed = snapshot(value);
    let confirmed_text = buffer_text(&render(130, 32, |frame| {
        render_portfolio(frame, frame.area(), &confirmed.portfolio, &state());
    }));
    assert!(confirmed_text.find("MSFT").unwrap() < confirmed_text.find("AAPL").unwrap());
}

#[test]
fn portfolio_shows_all_equal_return_components_benchmark_metrics_and_period() {
    let mut value = snapshot_value();
    value["portfolio"]["metrics"] = json!([
        {"metric_id":"drawdown","value":-0.02,"unit":"percent","freshness":"fresh","observed_at_utc":"2026-08-03T00:00:00Z","error":null},
        {"metric_id":"largest-holding","value":0.25,"unit":"percent","freshness":"fresh","observed_at_utc":"2026-08-03T00:00:00Z","error":null},
        {"metric_id":"volatility","value":0.12,"unit":"percent","freshness":"fresh","observed_at_utc":"2026-08-03T00:00:00Z","error":null},
        {"metric_id":"cash-level","value":0.08,"unit":"percent","freshness":"fresh","observed_at_utc":"2026-08-03T00:00:00Z","error":null}
    ]);
    let snapshot = snapshot(value);
    for (period, label) in [
        (PerformancePeriod::Today, "PERFORMANCE | TODAY"),
        (
            PerformancePeriod::SinceRebalance,
            "PERFORMANCE | SINCE REBALANCE",
        ),
        (PerformancePeriod::SinceStart, "PERFORMANCE | SINCE START"),
    ] {
        let screen_state = ScreenState {
            performance_period: period,
            ..state()
        };
        let text = buffer_text(&render(130, 36, |frame| {
            render_portfolio(frame, frame.area(), &snapshot.portfolio, &screen_state);
        }));
        assert!(text.contains(label), "missing {label}\n{text}");
    }
    let screen_state = ScreenState {
        performance_period: PerformancePeriod::SinceStart,
        ..state()
    };
    let text = buffer_text(&render(130, 36, |frame| {
        render_portfolio(frame, frame.area(), &snapshot.portfolio, &screen_state);
    }));
    for expected in [
        "SINCE START",
        "PRICE",
        "DIVIDENDS",
        "CASH INTEREST",
        "FEES",
        "S&P 500 TOTAL RETURN",
        "drawdown",
        "largest-holding",
        "volatility",
        "cash-level",
    ] {
        assert!(text.contains(expected), "missing {expected}\n{text}");
    }
    assert_eq!(
        screen_state.performance_period,
        PerformancePeriod::SinceStart
    );
}

#[test]
fn portfolio_period_persists_in_app_state_and_drives_real_ui() {
    let mut app = AppState::controller();
    app.snapshot = Some(snapshot(snapshot_value()));
    app.screen = Screen::Portfolio;
    app.set_performance_period(PerformancePeriod::SinceStart);
    let first = buffer_text(&render(140, 46, |frame| ui::render(frame, &app)));
    assert!(first.contains("SINCE START"));

    app.handle(InputEvent::Char('1'));
    app.handle(InputEvent::Char('2'));
    let second = buffer_text(&render(140, 46, |frame| ui::render(frame, &app)));
    assert!(second.contains("SINCE START"));
    assert_eq!(
        app.screen_state().performance_period,
        PerformancePeriod::SinceStart
    );
}

#[test]
fn keyboard_controls_reach_panels_periods_scrolling_and_symbol_detail() {
    let mut app = AppState::controller();
    app.snapshot = Some(snapshot(snapshot_value()));

    app.handle(InputEvent::Right);
    assert_eq!(app.screen_state().narrow_panel, 1);
    app.handle(InputEvent::Left);
    assert_eq!(app.screen_state().narrow_panel, 0);
    app.handle(InputEvent::Down);
    assert_eq!(app.screen_state().selected_id.as_deref(), Some("AAPL"));
    let selected = buffer_text(&render(80, 12, |frame| {
        render_impact(
            frame,
            frame.area(),
            &app.snapshot.as_ref().unwrap().impact,
            &app.screen_state(),
        );
    }));
    assert!(
        selected.contains("> AAPL"),
        "selection needs a non-color marker\n{selected}"
    );

    app.handle(InputEvent::Char('o'));
    assert_eq!(app.screen, Screen::Portfolio);
    assert_eq!(app.mode, LocalMode::Open);
    assert!(app.screen_state().detail_open);
    let opened = buffer_text(&render(140, 46, |frame| ui::render(frame, &app)));
    assert!(opened.contains("AAPL HISTORY"));
    app.handle(InputEvent::Escape);
    assert!(!app.screen_state().detail_open);

    app.handle(InputEvent::Right);
    assert_eq!(
        app.screen_state().performance_period,
        PerformancePeriod::SinceRebalance
    );
    let period = buffer_text(&render(140, 46, |frame| ui::render(frame, &app)));
    assert!(period.contains("SINCE REBALANCE"));

    app.handle(InputEvent::Char('3'));
    app.handle(InputEvent::Down);
    assert_eq!(app.screen_state().scroll_offset, 1);
    app.handle(InputEvent::Up);
    assert_eq!(app.screen_state().scroll_offset, 0);
}

#[test]
fn portfolio_scrolls_all_holdings_and_accepts_only_supported_asset_types() {
    let mut value = snapshot_value();
    let base = value["portfolio"]["rows"][0].clone();
    value["portfolio"]["rows"] = Value::Array(
        (0..30)
            .map(|index| {
                let mut row = base.clone();
                row["symbol"] = json!(format!("S{index:02}"));
                row["asset_type"] = json!(match index % 3 {
                    0 => "stock",
                    1 => "etf",
                    _ => "cash",
                });
                row["confirmed_rank"] = json!(index + 1);
                row
            })
            .collect(),
    );
    let snapshot = snapshot(value);
    assert!(matches!(
        snapshot.portfolio.rows[0].asset_type,
        AssetType::Stock
    ));
    assert!(matches!(
        snapshot.portfolio.rows[1].asset_type,
        AssetType::Etf
    ));
    assert!(matches!(
        snapshot.portfolio.rows[2].asset_type,
        AssetType::Cash
    ));

    let screen_state = ScreenState {
        scroll_offset: 20,
        ..state()
    };
    let text = buffer_text(&render(130, 36, |frame| {
        render_portfolio(frame, frame.area(), &snapshot.portfolio, &screen_state);
    }));
    assert!(!text.contains("S00"));
    assert!(text.contains("S20"));
    assert!(text.contains("S29"));
}

#[test]
fn portfolio_highlights_only_changed_cells_then_the_whole_reconciling_row() {
    let palette = Theme::WarmWhite.palette();
    let proposed = snapshot(snapshot_value());
    let buffer = render(130, 32, |frame| {
        render_portfolio(frame, frame.area(), &proposed.portfolio, &state());
    });
    let current = text_position(&buffer, "10.00%").expect("current weight");
    let changed = text_position(&buffer, "11.00%").expect("proposed weight");
    assert_eq!(buffer[current].fg, palette.foreground);
    assert_eq!(buffer[current].bg, palette.background);
    assert_eq!(
        buffer[changed].fg,
        palette.active.fg.expect("active foreground")
    );
    assert_eq!(
        buffer[changed].bg,
        palette.active.bg.expect("active background")
    );

    let mut value = snapshot_value();
    value["portfolio"]["rows"][0]["change_state"] = json!("unchanged");
    value["portfolio"]["rows"][0]["proposed_weight"] = Value::Null;
    let unchanged = snapshot(value);
    let buffer = render(130, 32, |frame| {
        render_portfolio(frame, frame.area(), &unchanged.portfolio, &state());
    });
    for needle in ["AAPL", "10.00%"] {
        let position = text_position(&buffer, needle).expect("unchanged row cell");
        assert_eq!(buffer[position].fg, palette.foreground);
        assert_eq!(buffer[position].bg, palette.background);
    }

    let mut value = snapshot_value();
    value["portfolio"]["rows"][0]["change_state"] = json!("executing");
    value["portfolio"]["rows"][0]["approved_weight"] = json!(0.11);
    let executing = snapshot(value);
    let buffer = render(130, 32, |frame| {
        render_portfolio(frame, frame.area(), &executing.portfolio, &state());
    });
    for needle in ["AAPL", "10.00%", "11.00%"] {
        let position = text_position(&buffer, needle).expect("executing row cell");
        assert_eq!(
            buffer[position].fg,
            palette.active.fg.expect("active foreground")
        );
        assert_eq!(
            buffer[position].bg,
            palette.active.bg.expect("active background")
        );
    }

    let mut value = snapshot_value();
    value["portfolio"]["rows"][0]["change_state"] = json!("reconciling");
    value["portfolio"]["rows"][0]["approved_weight"] = json!(0.11);
    let reconciling = snapshot(value);
    let buffer = render(130, 32, |frame| {
        render_portfolio(frame, frame.area(), &reconciling.portfolio, &state());
    });
    for needle in ["AAPL", "10.00%", "11.00%"] {
        let position = text_position(&buffer, needle).expect("reconciling row cell");
        assert_eq!(
            buffer[position].fg,
            palette.waiting.fg.expect("waiting foreground")
        );
        assert_eq!(
            buffer[position].bg,
            palette.waiting.bg.expect("waiting background")
        );
    }
}

#[test]
fn opening_symbol_pins_full_current_facts_and_ordered_history() {
    let mut value = snapshot_value();
    let mut newer = value["portfolio"]["history"][0].clone();
    newer["event_id"] = json!("event:newer");
    newer["occurred_at_utc"] = json!("2026-08-04T00:00:00Z");
    newer["summary"] = json!("Newer AAPL event");
    let mut older = value["portfolio"]["history"][0].clone();
    older["event_id"] = json!("event:older");
    older["occurred_at_utc"] = json!("2026-08-01T00:00:00Z");
    older["summary"] = json!("Older AAPL event");
    value["portfolio"]["history"] = json!([newer, older]);
    let snapshot = snapshot(value);
    let screen_state = ScreenState {
        selected_id: Some("AAPL".to_owned()),
        detail_open: true,
        ..state()
    };
    let text = buffer_text(&render(130, 36, |frame| {
        render_portfolio(frame, frame.area(), &snapshot.portfolio, &screen_state);
    }));
    for expected in [
        "AAPL HISTORY",
        "PINNED AAPL",
        "STOCK",
        "quantity 10",
        "price 100.25",
        "value 1002.50",
        "Newer AAPL event",
        "Older AAPL event",
    ] {
        assert!(text.contains(expected), "missing {expected}\n{text}");
    }
    assert!(text.find("Newer AAPL event").unwrap() < text.find("Older AAPL event").unwrap());
}

#[test]
fn orders_group_by_symbol_newest_first_and_show_execution_truth() {
    let mut value = snapshot_value();
    let first = value["orders"]["rows"][0].clone();
    let mut older = first.clone();
    older["order_id"] = json!("order:older");
    older["submitted_at_utc"] = json!("2026-08-01T00:00:00Z");
    older["status"] = json!("partial");
    older["reconciliation"] = json!("pending");
    let first_fill = older["fills"][0].clone();
    let mut second_fill = first_fill.clone();
    second_fill["fill_id"] = json!("fill:2");
    second_fill["quantity"] = json!("3");
    second_fill["fee"] = json!("0.25");
    older["fills"] = json!([first_fill, second_fill]);
    let mut newest = first.clone();
    newest["order_id"] = json!("order:newest");
    newest["submitted_at_utc"] = json!("2026-08-04T00:00:00Z");
    newest["reconciliation"] = json!("mismatch");
    let mut same_second_later = newest.clone();
    same_second_later["order_id"] = json!("order:fractional");
    same_second_later["submitted_at_utc"] = json!("2026-08-04T00:00:00.500000Z");
    let mut msft = first;
    msft["order_id"] = json!("order:msft");
    msft["symbol"] = json!("MSFT");
    value["orders"]["rows"] = json!([older, msft, newest, same_second_later]);
    value["orders"]["reconciliation_agents"] = json!([{
        "work_id":"work:reconcile-aapl","agent":"reconciliation-agent","title":"Repair AAPL mismatch","stage":"running","priority":100,"urgent":true,"elapsed_seconds":30.0,"model":"qwen:64k","affected_areas":["AAPL","orders"]
    }]);
    let snapshot = snapshot(value);
    let text = buffer_text(&render(150, 38, |frame| {
        render_orders(frame, frame.area(), &snapshot.orders, &state());
    }));
    assert!(text.find("order:fractional").unwrap() < text.find("order:newest").unwrap());
    assert!(text.find("order:newest").unwrap() < text.find("order:older").unwrap());
    for expected in [
        "AAPL",
        "MSFT",
        "PARTIAL",
        "FILLED",
        "paper-order-1",
        "FILLS",
        "fill:2",
        "0.25",
        "FEE",
        "EXPECTED",
        "ACTUAL",
        "SLIPPAGE",
        "MISMATCH",
        "reconciliation-agent",
    ] {
        assert!(text.contains(expected), "missing {expected}\n{text}");
    }
}

#[test]
fn unavailable_market_views_keep_layout_reason_and_no_fixture_rows() {
    let mut value = snapshot_value();
    for view in ["impact", "portfolio", "orders"] {
        value[view]["freshness"] = json!("unavailable");
        value[view]["as_of_utc"] = Value::Null;
        value[view]["error"] = json!("Controller source is unavailable.");
    }
    value["impact"]["holdings"] = json!([]);
    value["impact"]["events"] = json!([]);
    value["impact"]["agents"] = json!([]);
    value["portfolio"]["rows"] = json!([]);
    value["orders"]["rows"] = json!([]);
    let snapshot = snapshot(value);

    for text in [
        buffer_text(&render(130, 30, |frame| {
            render_impact(frame, frame.area(), &snapshot.impact, &state());
        })),
        buffer_text(&render(130, 30, |frame| {
            render_portfolio(frame, frame.area(), &snapshot.portfolio, &state());
        })),
        buffer_text(&render(130, 30, |frame| {
            render_orders(frame, frame.area(), &snapshot.orders, &state());
        })),
    ] {
        assert!(text.contains("UNAVAILABLE"));
        assert!(text.contains("Controller source is unavailable."));
        assert!(!text.contains("AAPL"));
    }
    let portfolio = buffer_text(&render(130, 30, |frame| {
        render_portfolio(frame, frame.area(), &snapshot.portfolio, &state());
    }));
    assert!(!portfolio.contains("PRICE: 0.01"));
    assert!(!portfolio.contains("metric:cpu"));
}

#[test]
fn stale_market_views_keep_last_valid_rows_and_show_the_reason() {
    let mut value = snapshot_value();
    for view in ["impact", "portfolio", "orders"] {
        value[view]["freshness"] = json!("stale");
        value[view]["error"] = json!("Last refresh failed; retained prior sample.");
    }
    let snapshot = snapshot(value);
    for (text, retained) in [
        (
            buffer_text(&render(130, 32, |frame| {
                render_impact(frame, frame.area(), &snapshot.impact, &state());
            })),
            "AAPL",
        ),
        (
            buffer_text(&render(130, 32, |frame| {
                render_portfolio(frame, frame.area(), &snapshot.portfolio, &state());
            })),
            "AAPL",
        ),
        (
            buffer_text(&render(130, 32, |frame| {
                render_orders(frame, frame.area(), &snapshot.orders, &state());
            })),
            "order:1",
        ),
    ] {
        assert!(text.contains("STALE"));
        assert!(text.contains("Last refresh failed"));
        assert!(text.contains(retained));
    }
}

#[test]
fn reviewed_impact_snapshot_covers_wide_standard_layout() {
    let snapshot = snapshot(snapshot_value());
    let wide_impact = buffer_text(&render(140, 32, |frame| {
        render_impact(frame, frame.area(), &snapshot.impact, &state());
    }));
    insta::assert_snapshot!("impact_wide", wide_impact);
}

#[test]
fn reviewed_portfolio_snapshot_covers_narrow_large_text_layout() {
    let snapshot = snapshot(snapshot_value());
    let narrow_portfolio = buffer_text(&render(76, 28, |frame| {
        let large = ScreenState {
            display_mode: DisplayMode::LargeText,
            ..state()
        };
        render_portfolio(frame, frame.area(), &snapshot.portfolio, &large);
    }));
    insta::assert_snapshot!("portfolio_narrow", narrow_portfolio);
}

#[test]
fn reviewed_orders_snapshot_covers_wide_standard_layout() {
    let snapshot = snapshot(snapshot_value());
    let wide_orders = buffer_text(&render(150, 34, |frame| {
        render_orders(frame, frame.area(), &snapshot.orders, &state());
    }));
    insta::assert_snapshot!("orders_wide", wide_orders);
}
