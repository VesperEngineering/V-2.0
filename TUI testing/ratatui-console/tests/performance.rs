use std::convert::Infallible;
use std::path::PathBuf;
use std::process::Command;
use std::thread;
use std::time::Instant;

use crossterm::event::{KeyCode, KeyEvent, KeyModifiers, MouseButton, MouseEvent, MouseEventKind};
use ratatui::Terminal;
use ratatui::backend::{Backend, ClearType, TestBackend, WindowSize};
use ratatui::buffer::{Buffer, Cell};
use ratatui::layout::{Position, Rect, Size};
use serde_json::{Value, json};
use vesper_ratatui_console::app::{POLL_INTERVAL, key_to_input, mouse_to_input};
use vesper_ratatui_console::contract::{ConsoleSnapshot, Envelope};
use vesper_ratatui_console::input::InputEvent;
use vesper_ratatui_console::layout::shell_layout;
use vesper_ratatui_console::render_plan::{RenderPlan, ShellRegion};
use vesper_ratatui_console::renderer::{RenderKind, Renderer};
use vesper_ratatui_console::state::{AppState, LocalMode, ReduceOutcome, Screen};
use windows_sys::Win32::Foundation::FILETIME;
use windows_sys::Win32::System::Threading::{GetCurrentProcess, GetProcessTimes};

const WIDTH: u16 = 140;
const HEIGHT: u16 = 40;
const REQUIRED_WARMUPS: usize = 10;
const REQUIRED_SAMPLES: usize = 100;
const ONE_SECOND_NS: u64 = 1_000_000_000;
const EVENT_P95_LIMIT_NS: u64 = 250_000_000;
const INPUT_P95_LIMIT_NS: u64 = 50_000_000;

#[derive(Debug)]
pub struct BenchmarkReceipt {
    pub name: String,
    pub unit: &'static str,
    pub samples: Vec<u64>,
    pub median: u64,
    pub p95: u64,
    pub max: u64,
}

impl BenchmarkReceipt {
    fn from_samples(name: &str, unit: &'static str, samples: Vec<u64>) -> Self {
        assert!(!samples.is_empty(), "benchmark requires samples");
        let mut ordered = samples.clone();
        ordered.sort_unstable();
        let middle = ordered.len() / 2;
        let median = if ordered.len().is_multiple_of(2) {
            ((u128::from(ordered[middle - 1]) + u128::from(ordered[middle])) / 2) as u64
        } else {
            ordered[middle]
        };
        let p95_index = (ordered.len() * 95).div_ceil(100) - 1;
        let p95 = ordered[p95_index];
        let max = ordered[ordered.len() - 1];
        Self {
            name: name.to_owned(),
            unit,
            samples,
            median,
            p95,
            max,
        }
    }

    fn record(&self) {
        println!(
            "{} unit={} samples={:?} median={} p95={} max={}",
            self.name, self.unit, self.samples, self.median, self.p95, self.max
        );
    }

    fn assert_sample_count(&self) {
        assert_eq!(self.samples.len(), REQUIRED_SAMPLES);
        assert!(self.median <= self.p95);
        assert!(self.p95 <= self.max);
    }
}

#[derive(Debug)]
struct InputReceipts {
    total: BenchmarkReceipt,
    poll: BenchmarkReceipt,
    dispatch: BenchmarkReceipt,
    reduce: BenchmarkReceipt,
    draw: BenchmarkReceipt,
}

impl InputReceipts {
    fn all(&self) -> [&BenchmarkReceipt; 5] {
        [
            &self.total,
            &self.poll,
            &self.dispatch,
            &self.reduce,
            &self.draw,
        ]
    }
}

#[derive(Clone, Debug)]
struct RenderScopeReceipt {
    kind: RenderKind,
    regions: Vec<ShellRegion>,
    draw_calls: usize,
    cell_writes: usize,
    clear_calls: usize,
    outside_region_writes: usize,
}

#[test]
fn production_renderer_performance_gates_are_recorded() {
    record_environment();
    let small = shared_snapshot();
    let large = large_fixture();
    assert_eq!(large.timeline.rows.len(), 10_000);
    assert_eq!(large.impact.holdings.len(), 1_000);
    assert_eq!(large.portfolio.rows.len(), 1_000);
    assert_eq!(large.orders.rows.len(), 1_000);
    assert_eq!(large.agents.rows.len(), 500);

    let cached = benchmark_cached_first_screen(&small, REQUIRED_WARMUPS, REQUIRED_SAMPLES);
    let (event, event_scope) =
        benchmark_event_visibility(&large, REQUIRED_WARMUPS, REQUIRED_SAMPLES);
    let keyboard = benchmark_input_latency(&small, REQUIRED_WARMUPS, REQUIRED_SAMPLES);
    let mouse = benchmark_mouse_input_latency(&small, REQUIRED_WARMUPS, REQUIRED_SAMPLES);
    let navigation = benchmark_navigation(&large, REQUIRED_WARMUPS, REQUIRED_SAMPLES);
    let chat = benchmark_long_chat(&small, REQUIRED_WARMUPS, REQUIRED_SAMPLES);
    let shutdown = benchmark_shutdown(&small, REQUIRED_WARMUPS, REQUIRED_SAMPLES);

    for receipt in [&cached, &event, &navigation, &chat, &shutdown] {
        receipt.record();
        receipt.assert_sample_count();
    }
    for receipt in keyboard.all().into_iter().chain(mouse.all()) {
        receipt.record();
        receipt.assert_sample_count();
    }
    println!("event_render_scope={event_scope:?}");
    println!(
        "sources cache=in-memory-auth-result-plus-stale-envelope-to-test-backend-component event=rust-envelope-reduce-to-test-backend-component keyboard=synthetic-10ms-poll-key-dispatch-reduce-to-test-backend-component mouse=synthetic-10ms-poll-mouse-dispatch-reduce-to-test-backend-component navigation=10k-timeline-component chat=bounded-stream-component shutdown=in-process-drop-component"
    );

    assert!(
        cached.p95 <= ONE_SECOND_NS,
        "cached first screen p95 was {} ns",
        cached.p95
    );
    assert!(
        event.p95 <= EVENT_P95_LIMIT_NS,
        "event visibility p95 was {} ns",
        event.p95
    );
    assert!(
        keyboard.total.p95 <= INPUT_P95_LIMIT_NS,
        "keyboard input p95 was {} ns",
        keyboard.total.p95
    );
    assert!(
        mouse.total.p95 <= INPUT_P95_LIMIT_NS,
        "mouse input p95 was {} ns",
        mouse.total.p95
    );
    assert_eq!(event_scope.kind, RenderKind::Partial);
    assert_eq!(event_scope.regions, vec![ShellRegion::Body]);
    assert_eq!(event_scope.draw_calls, 1);
    assert_eq!(event_scope.clear_calls, 0);
    assert_eq!(event_scope.outside_region_writes, 0);
    assert!(event_scope.cell_writes > 0);
    assert!(event_scope.cell_writes < usize::from(WIDTH) * usize::from(HEIGHT));
}

fn benchmark_cached_first_screen(
    fixture: &ConsoleSnapshot,
    warmups: usize,
    samples: usize,
) -> BenchmarkReceipt {
    assert_sampling(warmups, samples);
    let stale = stale_cache_snapshot(3, fixture);
    let mut measured = Vec::with_capacity(samples);

    for iteration in 0..warmups + samples {
        let mut state = AppState::locked();
        state.reduce(server_hello(1)).unwrap();
        state.handle(InputEvent::Char('x'));
        state.handle(InputEvent::Enter);
        state.take_render_plan();
        let mut terminal = Terminal::new(CountingBackend::new(WIDTH, HEIGHT)).unwrap();
        let mut renderer = Renderer::new();

        let started = Instant::now();
        assert_eq!(
            state.reduce(auth_result(2, true, "viewer")),
            Ok(ReduceOutcome::RequestSnapshot)
        );
        assert_eq!(state.reduce(stale.clone()), Ok(ReduceOutcome::Changed));
        state.set_terminal_area(Rect::new(0, 0, WIDTH, HEIGHT));
        let plan = state
            .take_render_plan()
            .expect("cache projection is visible");
        let receipt = renderer.draw(&mut terminal, &state, plan).unwrap();
        let elapsed = elapsed_ns(started);
        assert_eq!(receipt.kind, RenderKind::Full);
        assert!(buffer_text(renderer.committed_buffer().unwrap()).contains("STALE CACHE"));
        if iteration >= warmups {
            measured.push(elapsed);
        }
    }
    BenchmarkReceipt::from_samples(
        "component-auth-result-and-injected-stale-envelope-to-test-backend",
        "ns",
        measured,
    )
}

fn benchmark_event_visibility(
    fixture: &ConsoleSnapshot,
    warmups: usize,
    samples: usize,
) -> (BenchmarkReceipt, RenderScopeReceipt) {
    assert_sampling(warmups, samples);
    let snapshot_value = serde_json::to_value(fixture).unwrap();
    let presentation = event_presentation(&snapshot_value);
    let mut state = state_with_snapshot(fixture.clone(), Screen::Timeline);
    let body = shell_layout(Rect::new(0, 0, WIDTH, HEIGHT), state.display_mode()).body;
    let mut terminal = Terminal::new(CountingBackend::new(WIDTH, HEIGHT)).unwrap();
    terminal.backend_mut().track_region(body);
    let mut renderer = Renderer::new();
    render_initial(&mut state, &mut terminal, &mut renderer);
    let mut measured = Vec::with_capacity(samples);
    let mut final_scope = None;

    for iteration in 0..warmups + samples {
        let sequence = u64::try_from(iteration + 2).unwrap();
        let event = timeline_event(&presentation, sequence, sequence, iteration);
        terminal.backend_mut().reset_counts();
        let started = Instant::now();
        assert_eq!(state.reduce(event), Ok(ReduceOutcome::Changed));
        let plan = state.take_render_plan().expect("event requests a render");
        let receipt = renderer.draw(&mut terminal, &state, plan).unwrap();
        let elapsed = elapsed_ns(started);
        assert_eq!(receipt.kind, RenderKind::Partial);
        assert_eq!(receipt.regions, [ShellRegion::Body].into_iter().collect());
        assert_eq!(terminal.backend().draw_calls, 1);
        assert_eq!(terminal.backend().clear_calls, 0);
        assert_eq!(terminal.backend().outside_region_writes, 0);
        assert!(terminal.backend().cell_writes > 0);
        if iteration >= warmups {
            measured.push(elapsed);
        }
        final_scope = Some(RenderScopeReceipt {
            kind: receipt.kind,
            regions: receipt.regions.into_iter().collect(),
            draw_calls: terminal.backend().draw_calls,
            cell_writes: terminal.backend().cell_writes,
            clear_calls: terminal.backend().clear_calls,
            outside_region_writes: terminal.backend().outside_region_writes,
        });
    }

    (
        BenchmarkReceipt::from_samples(
            "component-event-reduce-to-test-backend-partial",
            "ns",
            measured,
        ),
        final_scope.unwrap(),
    )
}

fn benchmark_input_latency(
    fixture: &ConsoleSnapshot,
    warmups: usize,
    samples: usize,
) -> InputReceipts {
    assert_sampling(warmups, samples);
    let mut state = state_with_snapshot(fixture.clone(), Screen::Impact);
    let mut terminal = Terminal::new(CountingBackend::new(WIDTH, HEIGHT)).unwrap();
    let mut renderer = Renderer::new();
    render_initial(&mut state, &mut terminal, &mut renderer);
    let mut total = Vec::with_capacity(samples);
    let mut poll = Vec::with_capacity(samples);
    let mut dispatch = Vec::with_capacity(samples);
    let mut reduce = Vec::with_capacity(samples);
    let mut draw = Vec::with_capacity(samples);

    for iteration in 0..warmups + samples {
        let key = if state.screen == Screen::Impact {
            '2'
        } else {
            '1'
        };
        let total_started = Instant::now();

        let poll_started = Instant::now();
        thread::sleep(POLL_INTERVAL);
        let poll_ns = elapsed_ns(poll_started);

        let dispatch_started = Instant::now();
        let input = key_to_input(KeyEvent::new(KeyCode::Char(key), KeyModifiers::NONE))
            .expect("screen key dispatches");
        let dispatch_ns = elapsed_ns(dispatch_started);

        let reduce_started = Instant::now();
        assert!(state.handle(input).is_empty());
        let reduce_ns = elapsed_ns(reduce_started);

        terminal.backend_mut().reset_counts();
        let draw_started = Instant::now();
        let plan = state.take_render_plan().expect("screen change is visible");
        let receipt = renderer.draw(&mut terminal, &state, plan).unwrap();
        let draw_ns = elapsed_ns(draw_started);
        let total_ns = elapsed_ns(total_started);
        assert_eq!(receipt.kind, RenderKind::Full);
        assert!(terminal.backend().cell_writes > 0);

        if iteration >= warmups {
            total.push(total_ns);
            poll.push(poll_ns);
            dispatch.push(dispatch_ns);
            reduce.push(reduce_ns);
            draw.push(draw_ns);
        }
    }

    InputReceipts {
        total: BenchmarkReceipt::from_samples(
            "component-keyboard-input-total-with-synthetic-10ms-poll",
            "ns",
            total,
        ),
        poll: BenchmarkReceipt::from_samples("component-keyboard-input-poll", "ns", poll),
        dispatch: BenchmarkReceipt::from_samples(
            "component-keyboard-input-dispatch",
            "ns",
            dispatch,
        ),
        reduce: BenchmarkReceipt::from_samples("component-keyboard-input-reduce", "ns", reduce),
        draw: BenchmarkReceipt::from_samples(
            "component-keyboard-input-test-backend-draw",
            "ns",
            draw,
        ),
    }
}

fn benchmark_mouse_input_latency(
    fixture: &ConsoleSnapshot,
    warmups: usize,
    samples: usize,
) -> InputReceipts {
    assert_sampling(warmups, samples);
    let area = Rect::new(0, 0, WIDTH, HEIGHT);
    let mut state = state_with_snapshot(fixture.clone(), Screen::Impact);
    let mut terminal = Terminal::new(CountingBackend::new(WIDTH, HEIGHT)).unwrap();
    let mut renderer = Renderer::new();
    render_initial(&mut state, &mut terminal, &mut renderer);
    let mut total = Vec::with_capacity(samples);
    let mut poll = Vec::with_capacity(samples);
    let mut dispatch = Vec::with_capacity(samples);
    let mut reduce = Vec::with_capacity(samples);
    let mut draw = Vec::with_capacity(samples);

    for iteration in 0..warmups + samples {
        let navigation = shell_layout(area, state.display_mode()).navigation;
        let (column, expected_screen) = if state.screen == Screen::Impact {
            (navigation.x.saturating_add(14), Screen::Portfolio)
        } else {
            (navigation.x.saturating_add(1), Screen::Impact)
        };
        let mouse = MouseEvent {
            kind: MouseEventKind::Down(MouseButton::Left),
            column,
            row: navigation.y.saturating_add(1),
            modifiers: KeyModifiers::NONE,
        };
        let total_started = Instant::now();

        let poll_started = Instant::now();
        thread::sleep(POLL_INTERVAL);
        let poll_ns = elapsed_ns(poll_started);

        let dispatch_started = Instant::now();
        let input = mouse_to_input(mouse, area, &state).expect("navigation click dispatches");
        let dispatch_ns = elapsed_ns(dispatch_started);

        let reduce_started = Instant::now();
        assert!(state.handle(input).is_empty());
        let reduce_ns = elapsed_ns(reduce_started);
        assert_eq!(state.screen, expected_screen);

        terminal.backend_mut().reset_counts();
        let draw_started = Instant::now();
        let plan = state
            .take_render_plan()
            .expect("mouse screen change is visible");
        let receipt = renderer.draw(&mut terminal, &state, plan).unwrap();
        let draw_ns = elapsed_ns(draw_started);
        let total_ns = elapsed_ns(total_started);
        assert_eq!(receipt.kind, RenderKind::Full);
        assert!(terminal.backend().cell_writes > 0);

        if iteration >= warmups {
            total.push(total_ns);
            poll.push(poll_ns);
            dispatch.push(dispatch_ns);
            reduce.push(reduce_ns);
            draw.push(draw_ns);
        }
    }

    InputReceipts {
        total: BenchmarkReceipt::from_samples(
            "component-mouse-input-total-with-synthetic-10ms-poll",
            "ns",
            total,
        ),
        poll: BenchmarkReceipt::from_samples("component-mouse-input-poll", "ns", poll),
        dispatch: BenchmarkReceipt::from_samples("component-mouse-input-dispatch", "ns", dispatch),
        reduce: BenchmarkReceipt::from_samples("component-mouse-input-reduce", "ns", reduce),
        draw: BenchmarkReceipt::from_samples("component-mouse-input-test-backend-draw", "ns", draw),
    }
}

fn benchmark_navigation(
    fixture: &ConsoleSnapshot,
    warmups: usize,
    samples: usize,
) -> BenchmarkReceipt {
    assert_sampling(warmups, samples);
    let mut state = state_with_snapshot(fixture.clone(), Screen::Timeline);
    let mut terminal = Terminal::new(CountingBackend::new(WIDTH, HEIGHT)).unwrap();
    let mut renderer = Renderer::new();
    render_initial(&mut state, &mut terminal, &mut renderer);
    let mut measured = Vec::with_capacity(samples);

    for iteration in 0..warmups + samples {
        if state.mode != LocalMode::Browse {
            state.handle(InputEvent::Escape);
        }
        let index = 9_999 - (iteration % 100);
        let expected_id = format!("event:{index:05}");
        let started = Instant::now();
        state.handle(InputEvent::OpenBrowseRow { panel: 0, index });
        let plan = state.take_render_plan().expect("row navigation is visible");
        renderer.draw(&mut terminal, &state, plan).unwrap();
        let elapsed = elapsed_ns(started);
        assert!(buffer_text(renderer.committed_buffer().unwrap()).contains(&expected_id));
        if iteration >= warmups {
            measured.push(elapsed);
        }
    }

    BenchmarkReceipt::from_samples("10k-timeline-navigation", "ns", measured)
}

fn benchmark_long_chat(
    fixture: &ConsoleSnapshot,
    warmups: usize,
    samples: usize,
) -> BenchmarkReceipt {
    assert_sampling(warmups, samples);
    let mut state = chat_state(fixture.clone());
    let mut terminal = Terminal::new(CountingBackend::new(WIDTH, HEIGHT)).unwrap();
    let mut renderer = Renderer::new();
    render_initial(&mut state, &mut terminal, &mut renderer);
    let events = (0..warmups + samples)
        .map(|iteration| {
            let chunk_sequence = u64::try_from(iteration + 1).unwrap();
            let sequence = chunk_sequence + 1;
            let text = format!("{} chat-chunk-{iteration:05}", "x".repeat(4_096));
            chat_chunk_envelope(
                sequence,
                &format!("event:performance:{iteration}:chunk"),
                "message:performance",
                chunk_sequence,
                &text,
            )
        })
        .collect::<Vec<_>>();
    let mut measured = Vec::with_capacity(samples);

    for (iteration, event) in events.into_iter().enumerate() {
        let started = Instant::now();
        assert_eq!(state.reduce(event), Ok(ReduceOutcome::Changed));
        let plan = state.take_render_plan().expect("chat stream is visible");
        renderer.draw(&mut terminal, &state, plan).unwrap();
        let elapsed = elapsed_ns(started);
        if iteration >= warmups {
            measured.push(elapsed);
        }
    }
    let agent = state.selected_chat_agent().unwrap();
    assert!(
        state.chat_store().thread(agent).messages()[0]
            .content()
            .ends_with("chat-chunk-00109")
    );
    assert!(buffer_text(renderer.committed_buffer().unwrap()).contains("TAIL WINDOW"));
    BenchmarkReceipt::from_samples("long-chat-streaming", "ns", measured)
}

fn benchmark_shutdown(
    fixture: &ConsoleSnapshot,
    warmups: usize,
    samples: usize,
) -> BenchmarkReceipt {
    assert_sampling(warmups, samples);
    let mut measured = Vec::with_capacity(samples);
    for iteration in 0..warmups + samples {
        let mut state = state_with_snapshot(fixture.clone(), Screen::Impact);
        let mut terminal = Terminal::new(CountingBackend::new(WIDTH, HEIGHT)).unwrap();
        let mut renderer = Renderer::new();
        render_initial(&mut state, &mut terminal, &mut renderer);
        let started = Instant::now();
        drop(renderer);
        drop(terminal);
        drop(state);
        let elapsed = elapsed_ns(started);
        if iteration >= warmups {
            measured.push(elapsed);
        }
    }
    BenchmarkReceipt::from_samples("clean-in-process-shutdown", "ns", measured)
}

#[test]
#[ignore = "10-minute idle Tick/render component CPU measurement entrypoint"]
fn idle_tick_component_ten_minute_entrypoint() {
    record_environment();
    let mut state = state_with_snapshot(shared_snapshot(), Screen::Impact);
    let mut terminal = Terminal::new(CountingBackend::new(WIDTH, HEIGHT)).unwrap();
    let mut renderer = Renderer::new();
    render_initial(&mut state, &mut terminal, &mut renderer);
    for _ in 0..REQUIRED_WARMUPS {
        state.mark_dirty();
        let plan = state.take_render_plan().unwrap();
        renderer.draw(&mut terminal, &state, plan).unwrap();
    }

    let mut one_second_observations = Vec::with_capacity(600);
    let mut ten_second_windows = Vec::with_capacity(60);
    for _ in 0..60 {
        let mut window_cpu_ns = 0_u64;
        let mut window_wall_ns = 0_u64;
        for _ in 0..10 {
            let cpu_before = process_cpu_ns();
            let wall_started = Instant::now();
            for _ in 0..100 {
                let tick_started = Instant::now();
                state.handle(InputEvent::Tick(POLL_INTERVAL));
                if let Some(plan) = state.take_render_plan() {
                    renderer.draw(&mut terminal, &state, plan).unwrap();
                }
                if let Some(remaining) = POLL_INTERVAL.checked_sub(tick_started.elapsed()) {
                    thread::sleep(remaining);
                }
            }
            let wall_ns = elapsed_ns(wall_started).max(1);
            let cpu_ns = process_cpu_ns().saturating_sub(cpu_before);
            one_second_observations.push(cpu_ns.saturating_mul(10_000) / wall_ns);
            window_cpu_ns = window_cpu_ns.saturating_add(cpu_ns);
            window_wall_ns = window_wall_ns.saturating_add(wall_ns);
        }
        ten_second_windows.push(window_cpu_ns.saturating_mul(10_000) / window_wall_ns.max(1));
    }
    let observations = BenchmarkReceipt::from_samples(
        "idle-tick-component-cpu-one-second-observations",
        "percent-basis-points",
        one_second_observations,
    );
    let receipt = BenchmarkReceipt::from_samples(
        "idle-tick-component-cpu-ten-second-windows",
        "percent-basis-points",
        ten_second_windows,
    );
    observations.record();
    receipt.record();
    println!(
        "idle_tick_component_cpu_gate=ten-second-windows one_second_observations=600 windows=60 limit_percent_basis_points=100"
    );
    assert_eq!(observations.samples.len(), 600);
    assert_eq!(receipt.samples.len(), 60);
    assert!(
        receipt.p95 < 100,
        "idle Tick/render component CPU ten-second-window p95 must remain below 1 percent"
    );
}

fn render_initial(
    state: &mut AppState,
    terminal: &mut Terminal<CountingBackend>,
    renderer: &mut Renderer,
) {
    state.set_terminal_area(Rect::new(0, 0, WIDTH, HEIGHT));
    let plan = state.take_render_plan().unwrap_or(RenderPlan::Full);
    renderer.draw(terminal, state, plan).unwrap();
}

fn state_with_snapshot(snapshot: ConsoleSnapshot, screen: Screen) -> AppState {
    let mut state = AppState::controller();
    let state_version = snapshot.shell.state_version;
    assert_eq!(
        state.reduce(snapshot_envelope(1, state_version, snapshot)),
        Ok(ReduceOutcome::Changed)
    );
    state.screen = screen;
    state.mark_dirty();
    state
}

fn chat_state(snapshot: ConsoleSnapshot) -> AppState {
    let mut state = AppState::controller();
    state.snapshot = Some(snapshot);
    state.handle(InputEvent::Char('4'));
    state.handle(InputEvent::Char('i'));
    assert_eq!(state.mode, LocalMode::AgentSelector);
    assert_eq!(state.handle(InputEvent::Enter).len(), 1);
    assert_eq!(state.mode, LocalMode::AgentChat);
    assert_eq!(
        state.reduce(chat_history_result_envelope(1)),
        Ok(ReduceOutcome::Changed)
    );
    state
}

fn assert_sampling(warmups: usize, samples: usize) {
    assert!(warmups >= REQUIRED_WARMUPS);
    assert!(samples >= REQUIRED_SAMPLES);
}

#[derive(Debug)]
struct CountingBackend {
    inner: TestBackend,
    tracked_region: Option<Rect>,
    draw_calls: usize,
    cell_writes: usize,
    clear_calls: usize,
    outside_region_writes: usize,
}

impl CountingBackend {
    fn new(width: u16, height: u16) -> Self {
        Self {
            inner: TestBackend::new(width, height),
            tracked_region: None,
            draw_calls: 0,
            cell_writes: 0,
            clear_calls: 0,
            outside_region_writes: 0,
        }
    }

    fn track_region(&mut self, region: Rect) {
        self.tracked_region = Some(region);
    }

    fn reset_counts(&mut self) {
        self.draw_calls = 0;
        self.cell_writes = 0;
        self.clear_calls = 0;
        self.outside_region_writes = 0;
    }

    fn tracked(&self, x: u16, y: u16) -> bool {
        self.tracked_region.is_none_or(|region| {
            x >= region.x && x < region.right() && y >= region.y && y < region.bottom()
        })
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

fn shared_snapshot() -> ConsoleSnapshot {
    serde_json::from_value(snapshot_value()).unwrap()
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

fn wire_envelope(sequence: u64, state_version: u64, kind: &str, payload: Value) -> Envelope {
    serde_json::from_value(json!({
        "schema_version": 1,
        "message_id": format!("server:{sequence}"),
        "sequence": sequence,
        "state_version": state_version,
        "timestamp_utc": "2026-08-03T00:00:00Z",
        "message_type": kind,
        "payload": payload,
    }))
    .unwrap()
}

fn snapshot_envelope(sequence: u64, state_version: u64, snapshot: ConsoleSnapshot) -> Envelope {
    wire_envelope(
        sequence,
        state_version,
        "snapshot",
        json!({"snapshot": snapshot}),
    )
}

fn server_hello(sequence: u64) -> Envelope {
    wire_envelope(
        sequence,
        0,
        "server-hello",
        json!({"server_version": "0.1.0", "requires_setup": false}),
    )
}

fn auth_result(sequence: u64, success: bool, access_state: &str) -> Envelope {
    wire_envelope(
        sequence,
        0,
        "auth-result",
        json!({
            "success": success,
            "access_state": access_state,
            "reason": if success { Value::Null } else { json!("Unlock failed.") },
        }),
    )
}

fn stale_cache_snapshot(sequence: u64, fixture: &ConsoleSnapshot) -> Envelope {
    let mut value = serde_json::to_value(fixture).unwrap();
    value["shell"]["state_version"] = json!(0);
    value["shell"]["header"]["qwen_state"] = json!("STALE CACHE");
    value["command_specs"] = json!([]);
    for capability in value["shell"]["capabilities"].as_array_mut().unwrap() {
        capability["state"] = json!("disabled");
        capability["reason"] = json!("Cached state cannot authorize actions.");
    }
    wire_envelope(sequence, 0, "snapshot", json!({"snapshot": value}))
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

fn timeline_event(
    presentation: &Value,
    sequence: u64,
    state_version: u64,
    iteration: usize,
) -> Envelope {
    wire_envelope(
        sequence,
        state_version,
        "event",
        json!({
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
                "evidence_ids": [],
                "work_id": "work:0000",
            },
            "targets": ["timeline.rows"],
            "presentation": presentation,
        }),
    )
}

fn chat_chunk_envelope(
    sequence: u64,
    event_id: &str,
    message_id: &str,
    chunk_sequence: u64,
    text: &str,
) -> Envelope {
    chat_envelope(
        sequence,
        event_id,
        message_id,
        "chunk",
        Some(chunk_sequence),
        Some(text),
        None,
    )
}

fn chat_history_result_envelope(sequence: u64) -> Envelope {
    wire_envelope(
        sequence,
        0,
        "chat-history-result",
        json!({"agent_id": "v20-product", "next_cursor": null}),
    )
}

fn chat_envelope(
    sequence: u64,
    event_id: &str,
    message_id: &str,
    operation: &str,
    chunk_sequence: Option<u64>,
    text: Option<&str>,
    raw_text_sha256: Option<String>,
) -> Envelope {
    wire_envelope(
        sequence,
        0,
        "chat-event",
        json!({
            "event_id": event_id,
            "agent_id": "v20-product",
            "message_id": message_id,
            "role": "agent",
            "operation": operation,
            "chunk_sequence": chunk_sequence,
            "text": text,
            "token_count": (operation == "chunk").then_some(3_u64),
            "message_created_at_utc": "2026-08-04T11:59:00Z",
            "occurred_at_utc": (operation != "chunk").then_some("2026-08-04T12:00:00Z"),
            "validation_receipt_id": (operation == "complete").then_some("receipt:performance"),
            "raw_text_sha256": raw_text_sha256,
        }),
    )
}

fn buffer_text(buffer: &Buffer) -> String {
    buffer.content.iter().map(|cell| cell.symbol()).collect()
}

fn elapsed_ns(started: Instant) -> u64 {
    u64::try_from(started.elapsed().as_nanos()).unwrap_or(u64::MAX)
}

fn record_environment() {
    let hash = Command::new("git")
        .args(["rev-parse", "HEAD"])
        .current_dir(repo_root())
        .output()
        .ok()
        .filter(|output| output.status.success())
        .map(|output| String::from_utf8_lossy(&output.stdout).trim().to_owned())
        .unwrap_or_else(|| "unavailable".to_owned());
    println!(
        "environment os={} arch={} profile={} build_hash={} terminal={}x{} poll_ms={}",
        std::env::consts::OS,
        std::env::consts::ARCH,
        if cfg!(debug_assertions) {
            "debug"
        } else {
            "release"
        },
        hash,
        WIDTH,
        HEIGHT,
        POLL_INTERVAL.as_millis(),
    );
}

fn filetime_ticks(value: FILETIME) -> u64 {
    (u64::from(value.dwHighDateTime) << 32) | u64::from(value.dwLowDateTime)
}

fn process_cpu_ns() -> u64 {
    let mut creation = FILETIME::default();
    let mut exit = FILETIME::default();
    let mut kernel = FILETIME::default();
    let mut user = FILETIME::default();
    // SAFETY: all pointers reference initialized writable FILETIME values for this process.
    let result = unsafe {
        GetProcessTimes(
            GetCurrentProcess(),
            &mut creation,
            &mut exit,
            &mut kernel,
            &mut user,
        )
    };
    assert_ne!(result, 0, "GetProcessTimes failed");
    filetime_ticks(kernel)
        .saturating_add(filetime_ticks(user))
        .saturating_mul(100)
}
