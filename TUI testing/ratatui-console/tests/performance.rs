use std::collections::BTreeSet;
use std::convert::Infallible;
use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Instant;

use ratatui::Terminal;
use ratatui::backend::{Backend, ClearType, TestBackend, WindowSize};
use ratatui::buffer::Cell;
use ratatui::layout::{Position, Rect, Size};
use serde_json::{Value, json};
use vesper_ratatui_console::contract::{ConsoleSnapshot, Envelope, EventTarget};
use vesper_ratatui_console::layout::DisplayMode;
use vesper_ratatui_console::reducer::{EventEnvelope, ReduceOutcome, SnapshotReducer};
use vesper_ratatui_console::screens::ScreenState;
use vesper_ratatui_console::screens::timeline::render_timeline;
use vesper_ratatui_console::theme::Theme;

const WIDTH: u16 = 140;
const HEIGHT: u16 = 40;
const PANEL_AREA: Rect = Rect::new(10, 4, 120, 32);

static DIRTY_PANEL_CALLS: AtomicUsize = AtomicUsize::new(0);
static BACKEND_DRAW_CALLS: AtomicUsize = AtomicUsize::new(0);
static BACKEND_CELL_WRITES: AtomicUsize = AtomicUsize::new(0);
static BACKEND_CLEAR_CALLS: AtomicUsize = AtomicUsize::new(0);
static OUTSIDE_PANEL_WRITES: AtomicUsize = AtomicUsize::new(0);
static FULL_SCREEN_MARKS: AtomicUsize = AtomicUsize::new(0);

#[derive(Debug)]
pub struct BenchmarkReceipt {
    pub name: String,
    pub samples_ns: Vec<u64>,
    pub median_ns: u64,
    pub p95_ns: u64,
    pub max_ns: u64,
}

impl BenchmarkReceipt {
    fn from_samples(name: &str, samples_ns: Vec<u64>) -> Self {
        assert!(!samples_ns.is_empty(), "benchmark requires samples");
        let mut ordered = samples_ns.clone();
        ordered.sort_unstable();
        let middle = ordered.len() / 2;
        let median_ns = if ordered.len().is_multiple_of(2) {
            ((u128::from(ordered[middle - 1]) + u128::from(ordered[middle])) / 2) as u64
        } else {
            ordered[middle]
        };
        let p95_index = (ordered.len() * 95).div_ceil(100) - 1;
        let p95_ns = ordered[p95_index];
        let max_ns = ordered[ordered.len() - 1];
        Self {
            name: name.to_owned(),
            samples_ns,
            median_ns,
            p95_ns,
            max_ns,
        }
    }

    fn record(&self) {
        println!(
            "{} samples_ns={:?} median_ns={} p95_ns={} max_ns={}",
            self.name, self.samples_ns, self.median_ns, self.p95_ns, self.max_ns
        );
    }
}

pub fn benchmark_reducer(
    fixture: &ConsoleSnapshot,
    warmups: usize,
    samples: usize,
) -> BenchmarkReceipt {
    assert!(samples > 0, "benchmark requires samples");
    let snapshot_value = serde_json::to_value(fixture).expect("serialize large fixture");
    let presentation = event_presentation(&snapshot_value);
    let mut reducer = SnapshotReducer::default();
    assert_eq!(
        reducer.apply_snapshot(fixture.clone()),
        ReduceOutcome::Changed
    );
    let mut samples_ns = Vec::with_capacity(samples);

    for iteration in 0..warmups + samples {
        let sequence = u64::try_from(iteration + 1).expect("bounded benchmark sequence");
        let event = timeline_event(
            &presentation,
            sequence,
            fixture.shell.state_version + sequence,
            iteration,
        );
        let started = Instant::now();
        let outcome = reducer.apply_event(event).expect("ordered benchmark event");
        let elapsed_ns = elapsed_ns(started);
        assert_eq!(outcome, ReduceOutcome::Changed);
        if iteration >= warmups {
            samples_ns.push(elapsed_ns);
        }
    }
    assert_eq!(reducer.state().snapshot.timeline.rows.len(), 10_000);
    BenchmarkReceipt::from_samples("event-reducer", samples_ns)
}

pub fn benchmark_changed_panel(
    fixture: &ConsoleSnapshot,
    warmups: usize,
    samples: usize,
) -> BenchmarkReceipt {
    assert!(samples > 0, "benchmark requires samples");
    let snapshot_value = serde_json::to_value(fixture).expect("serialize large fixture");
    let presentation = event_presentation(&snapshot_value);
    let mut reducer = SnapshotReducer::default();
    assert_eq!(
        reducer.apply_snapshot(fixture.clone()),
        ReduceOutcome::Changed
    );
    let backend = CountingBackend::new(WIDTH, HEIGHT, PANEL_AREA);
    let mut terminal = Terminal::new(backend).expect("counting terminal");
    let state = timeline_state(0);
    terminal
        .draw(|frame| render_timeline(frame, PANEL_AREA, &fixture.timeline, &state))
        .expect("initial timeline render");
    let mut samples_ns = Vec::with_capacity(samples);

    for iteration in 0..warmups + samples {
        let sequence = u64::try_from(iteration + 1).expect("bounded benchmark sequence");
        let event = timeline_event(
            &presentation,
            sequence,
            fixture.shell.state_version + sequence,
            iteration,
        );
        let dirty = dirty_panels(&event);
        assert_eq!(dirty.len(), 1);
        assert!(!dirty.contains(&DirtyPanel::FullScreen));
        assert_eq!(
            reducer.apply_event(event).expect("ordered benchmark event"),
            ReduceOutcome::Changed
        );
        terminal.backend_mut().reset_counts();
        let mut renderer_calls = 0;
        let started = Instant::now();
        terminal
            .draw(|frame| {
                for panel in &dirty {
                    match panel {
                        DirtyPanel::Timeline => {
                            renderer_calls += 1;
                            render_timeline(
                                frame,
                                PANEL_AREA,
                                &reducer.state().snapshot.timeline,
                                &state,
                            );
                        }
                        DirtyPanel::FullScreen => panic!("one-panel event marked full screen"),
                    }
                }
            })
            .expect("changed timeline panel render");
        let elapsed_ns = elapsed_ns(started);
        assert_eq!(renderer_calls, 1);
        assert_eq!(terminal.backend().draw_calls, 1);
        assert_eq!(terminal.backend().clear_calls, 0);
        assert_eq!(terminal.backend().outside_region_writes, 0);
        assert!(terminal.backend().cell_writes > 0);
        assert!(terminal.backend().cell_writes < usize::from(WIDTH) * usize::from(HEIGHT));
        record_probe(terminal.backend(), renderer_calls, &dirty);
        if iteration >= warmups {
            samples_ns.push(elapsed_ns);
        }
    }

    BenchmarkReceipt::from_samples("changed-timeline-panel", samples_ns)
}

pub fn benchmark_navigation(
    fixture: &ConsoleSnapshot,
    warmups: usize,
    samples: usize,
) -> BenchmarkReceipt {
    assert!(samples > 0, "benchmark requires samples");
    let backend = TestBackend::new(WIDTH, HEIGHT);
    let mut terminal = Terminal::new(backend).expect("navigation terminal");
    let last = fixture.timeline.rows.len() - 1;
    let mut samples_ns = Vec::with_capacity(samples);

    for iteration in 0..warmups + samples {
        let state = timeline_state(last.saturating_sub(iteration % 20));
        let started = Instant::now();
        terminal
            .draw(|frame| render_timeline(frame, PANEL_AREA, &fixture.timeline, &state))
            .expect("10,000-row navigation render");
        let elapsed_ns = elapsed_ns(started);
        if iteration >= warmups {
            samples_ns.push(elapsed_ns);
        }
    }

    BenchmarkReceipt::from_samples("10k-timeline-navigation", samples_ns)
}

#[test]
fn release_reducer_and_panel_budgets_are_recorded() {
    let fixture = large_fixture();
    assert_eq!(fixture.timeline.rows.len(), 10_000);
    assert_eq!(fixture.impact.holdings.len(), 1_000);
    assert_eq!(fixture.portfolio.rows.len(), 1_000);
    assert_eq!(fixture.orders.rows.len(), 1_000);
    assert_eq!(fixture.agents.rows.len(), 500);

    let reducer = benchmark_reducer(&fixture, 10, 100);
    let panel = benchmark_changed_panel(&fixture, 10, 100);
    let navigation = benchmark_navigation(&fixture, 10, 100);
    reducer.record();
    panel.record();
    navigation.record();
    println!(
        "dirty_panel_calls={} backend_draw_calls={} backend_cell_writes={} backend_clear_calls={} outside_panel_writes={} full_screen_marks={}",
        dirty_panel_calls(),
        backend_draw_calls(),
        backend_cell_writes(),
        backend_clear_calls(),
        outside_panel_writes(),
        full_screen_marks(),
    );

    for receipt in [&reducer, &panel, &navigation] {
        assert_eq!(receipt.samples_ns.len(), 100);
        assert!(receipt.median_ns <= receipt.p95_ns);
        assert!(receipt.p95_ns <= receipt.max_ns);
    }
    if !cfg!(debug_assertions) {
        assert!(
            reducer.p95_ns < 25_000_000,
            "reducer p95 was {} ns",
            reducer.p95_ns
        );
        assert!(
            panel.p95_ns < 50_000_000,
            "changed-panel p95 was {} ns",
            panel.p95_ns
        );
    }
    assert_eq!(dirty_panel_calls(), 1);
    assert_eq!(full_screen_marks(), 0);
    assert_eq!(backend_draw_calls(), 1);
    assert_eq!(backend_clear_calls(), 0);
    assert_eq!(outside_panel_writes(), 0);
    assert!(backend_cell_writes() > 0);
    assert!(backend_cell_writes() < usize::from(WIDTH) * usize::from(HEIGHT));
    assert!(render_at_last_row(&fixture).contains("ID event:09999"));
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
enum DirtyPanel {
    Timeline,
    FullScreen,
}

fn dirty_panels(event: &EventEnvelope) -> BTreeSet<DirtyPanel> {
    event
        .payload
        .targets
        .iter()
        .map(|target| match target {
            EventTarget::TimelineRows => DirtyPanel::Timeline,
            _ => DirtyPanel::FullScreen,
        })
        .collect()
}

fn record_probe(backend: &CountingBackend, renderer_calls: usize, dirty: &BTreeSet<DirtyPanel>) {
    DIRTY_PANEL_CALLS.store(renderer_calls, Ordering::Relaxed);
    BACKEND_DRAW_CALLS.store(backend.draw_calls, Ordering::Relaxed);
    BACKEND_CELL_WRITES.store(backend.cell_writes, Ordering::Relaxed);
    BACKEND_CLEAR_CALLS.store(backend.clear_calls, Ordering::Relaxed);
    OUTSIDE_PANEL_WRITES.store(backend.outside_region_writes, Ordering::Relaxed);
    FULL_SCREEN_MARKS.store(
        usize::from(dirty.contains(&DirtyPanel::FullScreen)),
        Ordering::Relaxed,
    );
}

fn dirty_panel_calls() -> usize {
    DIRTY_PANEL_CALLS.load(Ordering::Relaxed)
}

fn backend_draw_calls() -> usize {
    BACKEND_DRAW_CALLS.load(Ordering::Relaxed)
}

fn backend_cell_writes() -> usize {
    BACKEND_CELL_WRITES.load(Ordering::Relaxed)
}

fn backend_clear_calls() -> usize {
    BACKEND_CLEAR_CALLS.load(Ordering::Relaxed)
}

fn outside_panel_writes() -> usize {
    OUTSIDE_PANEL_WRITES.load(Ordering::Relaxed)
}

fn full_screen_marks() -> usize {
    FULL_SCREEN_MARKS.load(Ordering::Relaxed)
}

#[derive(Debug)]
struct CountingBackend {
    inner: TestBackend,
    tracked_region: Rect,
    draw_calls: usize,
    cell_writes: usize,
    clear_calls: usize,
    outside_region_writes: usize,
}

impl CountingBackend {
    fn new(width: u16, height: u16, tracked_region: Rect) -> Self {
        Self {
            inner: TestBackend::new(width, height),
            tracked_region,
            draw_calls: 0,
            cell_writes: 0,
            clear_calls: 0,
            outside_region_writes: 0,
        }
    }

    fn reset_counts(&mut self) {
        self.draw_calls = 0;
        self.cell_writes = 0;
        self.clear_calls = 0;
        self.outside_region_writes = 0;
    }

    fn tracked(&self, x: u16, y: u16) -> bool {
        x >= self.tracked_region.x
            && x < self.tracked_region.right()
            && y >= self.tracked_region.y
            && y < self.tracked_region.bottom()
    }
}

impl Backend for CountingBackend {
    type Error = Infallible;

    fn draw<'a, I>(&mut self, content: I) -> Result<(), Self::Error>
    where
        I: Iterator<Item = (u16, u16, &'a Cell)>,
    {
        let cells = content.collect::<Vec<_>>();
        self.draw_calls += 1;
        self.cell_writes += cells.len();
        self.outside_region_writes += cells
            .iter()
            .filter(|(x, y, _)| !self.tracked(*x, *y))
            .count();
        self.inner.draw(cells.into_iter())
    }

    fn hide_cursor(&mut self) -> Result<(), Self::Error> {
        self.inner.hide_cursor()
    }

    fn show_cursor(&mut self) -> Result<(), Self::Error> {
        self.inner.show_cursor()
    }

    fn get_cursor_position(&mut self) -> Result<Position, Self::Error> {
        self.inner.get_cursor_position()
    }

    fn set_cursor_position<P: Into<Position>>(&mut self, position: P) -> Result<(), Self::Error> {
        self.inner.set_cursor_position(position)
    }

    fn clear(&mut self) -> Result<(), Self::Error> {
        self.clear_calls += 1;
        self.inner.clear()
    }

    fn clear_region(&mut self, clear_type: ClearType) -> Result<(), Self::Error> {
        self.clear_calls += 1;
        self.inner.clear_region(clear_type)
    }

    fn size(&self) -> Result<Size, Self::Error> {
        self.inner.size()
    }

    fn window_size(&mut self) -> Result<WindowSize, Self::Error> {
        self.inner.window_size()
    }

    fn flush(&mut self) -> Result<(), Self::Error> {
        self.inner.flush()
    }
}

fn large_fixture() -> ConsoleSnapshot {
    let mut value = snapshot_value();
    value["shell"]["state_version"] = json!(1);

    let holding = value["portfolio"]["rows"][0].clone();
    let holdings = (0..1_000)
        .map(|index| {
            let mut row = holding.clone();
            row["symbol"] = json!(format!("STK{index:04}"));
            row["description"] = json!(format!("Holding {index:04}"));
            row["current_weight"] = json!(0.001);
            row["proposed_weight"] = Value::Null;
            row["change_state"] = json!("unchanged");
            row["confirmed_rank"] = json!(index + 1);
            row["reconciliation"] = json!("not-required");
            row
        })
        .collect::<Vec<_>>();
    value["impact"]["holdings"] = Value::Array(holdings.clone());
    value["portfolio"]["rows"] = Value::Array(holdings);

    let order = value["orders"]["rows"][0].clone();
    value["orders"]["rows"] = Value::Array(
        (0..1_000)
            .map(|index| {
                let mut row = order.clone();
                row["order_id"] = json!(format!("order:{index:04}"));
                row["symbol"] = json!(format!("STK{index:04}"));
                row["broker_order_id"] = json!(format!("paper-order-{index:04}"));
                row["fills"][0]["fill_id"] = json!(format!("fill:{index:04}"));
                row
            })
            .collect(),
    );

    let agent = value["agents"]["rows"][0].clone();
    let agents = (0..500)
        .map(|index| {
            let mut row = agent.clone();
            row["work_id"] = json!(format!("work:{index:04}"));
            row["agent"] = json!(format!("agent:{index:04}"));
            row["title"] = json!(format!("Agent task {index:04}"));
            row["priority"] = json!((index % 100) + 1);
            row
        })
        .collect::<Vec<_>>();
    value["impact"]["agents"] = Value::Array(agents.clone());
    value["agents"]["rows"] = Value::Array(agents);

    let timeline = value["timeline"]["rows"][0].clone();
    value["timeline"]["rows"] = Value::Array(
        (0..10_000)
            .map(|index| {
                let mut row = timeline.clone();
                row["event_id"] = json!(format!("event:{index:05}"));
                row["summary"] = json!(format!("Timeline row {index:05}"));
                row["agent_id"] = json!(format!("agent:{:04}", index % 500));
                row["symbol"] = json!(format!("STK{:04}", index % 1_000));
                row["order_id"] = json!(format!("order:{:04}", index % 1_000));
                row["evidence_ids"] = json!([]);
                row
            })
            .collect(),
    );

    serde_json::from_value(value).expect("deterministic large console fixture")
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

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .expect("crate is nested two levels under the repository")
        .to_path_buf()
}

fn event_presentation(snapshot: &Value) -> Value {
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

fn timeline_event(
    presentation: &Value,
    sequence: u64,
    state_version: u64,
    iteration: usize,
) -> EventEnvelope {
    let envelope: Envelope = serde_json::from_value(json!({
        "schema_version": 1,
        "message_id": format!("server:{sequence}"),
        "sequence": sequence,
        "state_version": state_version,
        "timestamp_utc": "2026-08-03T00:00:00Z",
        "message_type": "event",
        "payload": {
            "entity_type": "timeline-row",
            "entity_id": "event:00000",
            "operation": "upsert",
            "entity": {
                "event_id": "event:00000",
                "occurred_at_utc": "2026-08-03T00:00:00Z",
                "impact": true,
                "severity": "active",
                "summary": format!("Changed timeline row {iteration:06}"),
                "agent_id": "agent:0000",
                "symbol": "STK0000",
                "model_id": null,
                "approval_id": null,
                "order_id": "order:0000",
                "evidence_ids": []
            },
            "targets": ["timeline.rows"],
            "presentation": presentation.clone()
        }
    }))
    .expect("strict timeline benchmark event");
    EventEnvelope::try_from(envelope).expect("event envelope")
}

fn timeline_state(scroll_offset: usize) -> ScreenState {
    ScreenState {
        theme: Theme::WarmWhite,
        display_mode: DisplayMode::Compact,
        scroll_offset,
        show_all_events: true,
        ..ScreenState::default()
    }
}

fn render_at_last_row(fixture: &ConsoleSnapshot) -> String {
    let backend = TestBackend::new(WIDTH, HEIGHT);
    let mut terminal = Terminal::new(backend).expect("last-row terminal");
    let state = timeline_state(fixture.timeline.rows.len() - 1);
    terminal
        .draw(|frame| render_timeline(frame, PANEL_AREA, &fixture.timeline, &state))
        .expect("render last timeline row");
    let buffer = terminal.backend().buffer();
    (buffer.area.y..buffer.area.bottom())
        .flat_map(|y| (buffer.area.x..buffer.area.right()).map(move |x| buffer[(x, y)].symbol()))
        .collect::<String>()
}

fn elapsed_ns(started: Instant) -> u64 {
    u64::try_from(started.elapsed().as_nanos()).unwrap_or(u64::MAX)
}
