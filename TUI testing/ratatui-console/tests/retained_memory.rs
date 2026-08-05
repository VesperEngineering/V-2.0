use std::alloc::{GlobalAlloc, Layout, System};
use std::ffi::c_void;
use std::mem::size_of;
use std::path::PathBuf;
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};
use std::thread;
use std::time::{Duration, Instant};

use ratatui::Terminal;
use ratatui::backend::TestBackend;
use ratatui::layout::Rect;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use vesper_ratatui_console::chat::MAX_VISIBLE_MESSAGES_PER_AGENT;
use vesper_ratatui_console::contract::{ConsoleSnapshot, Envelope};
use vesper_ratatui_console::input::InputEvent;
use vesper_ratatui_console::render_plan::RenderPlan;
use vesper_ratatui_console::renderer::Renderer;
use vesper_ratatui_console::state::{AppState, LocalMode, ReduceOutcome};
use windows_sys::Win32::Foundation::HANDLE;
use windows_sys::Win32::System::Threading::GetCurrentProcess;

const WIDTH: u16 = 140;
const HEIGHT: u16 = 40;
const MAX_MEMORY_GROWTH_BYTES: u64 = 10 * 1024 * 1024;
const RETAINED_MEMORY_STEADY_STATE_MESSAGES: usize = MAX_VISIBLE_MESSAGES_PER_AGENT * 2;
const RETAINED_MESSAGE_BYTES: usize = 2_067;

struct TrackingAllocator {
    live_allocated_bytes: AtomicU64,
    peak_live_allocated_bytes: AtomicU64,
}

#[global_allocator]
static GLOBAL_ALLOCATOR: TrackingAllocator = TrackingAllocator::new();

impl TrackingAllocator {
    const fn new() -> Self {
        Self {
            live_allocated_bytes: AtomicU64::new(0),
            peak_live_allocated_bytes: AtomicU64::new(0),
        }
    }

    fn record_allocation(&self, size: usize) {
        let bytes = allocation_bytes(size);
        let previous = self
            .live_allocated_bytes
            .fetch_update(Ordering::Relaxed, Ordering::Relaxed, |current| {
                current.checked_add(bytes)
            })
            .unwrap_or_else(|_| std::process::abort());
        let current = previous
            .checked_add(bytes)
            .unwrap_or_else(|| std::process::abort());
        self.peak_live_allocated_bytes
            .fetch_max(current, Ordering::Relaxed);
    }

    fn record_deallocation(&self, size: usize) {
        let bytes = allocation_bytes(size);
        if self
            .live_allocated_bytes
            .fetch_update(Ordering::Relaxed, Ordering::Relaxed, |current| {
                current.checked_sub(bytes)
            })
            .is_err()
        {
            std::process::abort();
        }
    }

    fn live_allocated_bytes(&self) -> u64 {
        self.live_allocated_bytes.load(Ordering::Relaxed)
    }

    fn reset_live_allocation_peak(&self) {
        self.peak_live_allocated_bytes
            .store(self.live_allocated_bytes(), Ordering::Relaxed);
    }

    fn peak_live_allocated_bytes(&self) -> u64 {
        self.peak_live_allocated_bytes.load(Ordering::Relaxed)
    }
}

// SAFETY: every operation delegates to System with the original allocation layout. The atomics
// only observe successful allocation size changes and never touch the returned memory.
unsafe impl GlobalAlloc for TrackingAllocator {
    unsafe fn alloc(&self, layout: Layout) -> *mut u8 {
        // SAFETY: callers uphold GlobalAlloc::alloc's layout contract.
        let pointer = unsafe { System.alloc(layout) };
        if !pointer.is_null() {
            self.record_allocation(layout.size());
        }
        pointer
    }

    unsafe fn dealloc(&self, pointer: *mut u8, layout: Layout) {
        // SAFETY: callers provide the pointer and layout returned by this allocator.
        unsafe { System.dealloc(pointer, layout) };
        self.record_deallocation(layout.size());
    }

    unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 {
        // SAFETY: callers uphold GlobalAlloc::alloc_zeroed's layout contract.
        let pointer = unsafe { System.alloc_zeroed(layout) };
        if !pointer.is_null() {
            self.record_allocation(layout.size());
        }
        pointer
    }

    unsafe fn realloc(&self, pointer: *mut u8, layout: Layout, new_size: usize) -> *mut u8 {
        // SAFETY: callers provide the original pointer/layout and a valid new size.
        let resized = unsafe { System.realloc(pointer, layout, new_size) };
        if !resized.is_null() {
            if new_size >= layout.size() {
                self.record_allocation(new_size - layout.size());
            } else {
                self.record_deallocation(layout.size() - new_size);
            }
        }
        resized
    }
}

fn allocation_bytes(size: usize) -> u64 {
    u64::try_from(size).unwrap_or_else(|_| std::process::abort())
}

fn live_allocated_bytes() -> u64 {
    GLOBAL_ALLOCATOR.live_allocated_bytes()
}

fn reset_live_allocation_peak() {
    GLOBAL_ALLOCATOR.reset_live_allocation_peak();
}

fn peak_live_allocated_bytes() -> u64 {
    GLOBAL_ALLOCATOR.peak_live_allocated_bytes()
}

#[test]
fn tracking_allocator_balances_alloc_zeroed_realloc_and_dealloc() {
    let allocator = TrackingAllocator::new();
    let before = allocator.live_allocated_bytes();
    let initial_layout = Layout::from_size_align(64, 8).unwrap();
    // SAFETY: the layout is valid and every successful pointer is released with its current layout.
    let pointer = unsafe { allocator.alloc(initial_layout) };
    assert!(!pointer.is_null());
    assert_eq!(allocator.live_allocated_bytes(), before + 64);

    // SAFETY: pointer and layout came from the allocator above; 128 is a valid non-zero size.
    let pointer = unsafe { allocator.realloc(pointer, initial_layout, 128) };
    assert!(!pointer.is_null());
    assert_eq!(allocator.live_allocated_bytes(), before + 128);
    let grown_layout = Layout::from_size_align(128, 8).unwrap();

    // SAFETY: pointer and layout describe the current allocation; 32 is valid and non-zero.
    let pointer = unsafe { allocator.realloc(pointer, grown_layout, 32) };
    assert!(!pointer.is_null());
    assert_eq!(allocator.live_allocated_bytes(), before + 32);
    let shrunk_layout = Layout::from_size_align(32, 8).unwrap();
    // SAFETY: pointer and layout describe the current allocation.
    unsafe { allocator.dealloc(pointer, shrunk_layout) };
    assert_eq!(allocator.live_allocated_bytes(), before);

    let zeroed_layout = Layout::from_size_align(32, 8).unwrap();
    // SAFETY: the layout is valid and the successful pointer is released below.
    let zeroed = unsafe { allocator.alloc_zeroed(zeroed_layout) };
    assert!(!zeroed.is_null());
    // SAFETY: zeroed points to a live 32-byte allocation.
    assert!(
        unsafe { std::slice::from_raw_parts(zeroed, 32) }
            .iter()
            .all(|byte| *byte == 0)
    );
    assert_eq!(allocator.live_allocated_bytes(), before + 32);
    // SAFETY: pointer and layout describe the current allocation.
    unsafe { allocator.dealloc(zeroed, zeroed_layout) };
    assert_eq!(allocator.live_allocated_bytes(), before);
}

#[test]
#[ignore = "one-hour retained-memory measurement entrypoint"]
fn retained_memory_one_hour_entrypoint() {
    record_environment();
    let mut state = chat_state();
    let mut terminal = Terminal::new(TestBackend::new(WIDTH, HEIGHT)).unwrap();
    let mut renderer = Renderer::new();
    render_initial(&mut state, &mut terminal, &mut renderer);
    let mut live_samples = Vec::with_capacity(61);
    let mut private_samples = Vec::with_capacity(61);
    let pre_warm_live = live_allocated_bytes();
    let pre_warm_private = process_private_bytes();
    let mut sequence =
        warm_retained_memory_to_steady_state(&mut state, &mut terminal, &mut renderer, 1);
    let start_live = live_allocated_bytes();
    let start_private = process_private_bytes();
    reset_live_allocation_peak();
    let run_started = Instant::now();

    for offset in 0..3_600 {
        let index = RETAINED_MEMORY_STEADY_STATE_MESSAGES + offset;
        sequence =
            apply_complete_chat_message(&mut state, &mut terminal, &mut renderer, sequence, index);
        let deadline = run_started + Duration::from_secs(u64::try_from(offset + 1).unwrap());
        if let Some(remaining) = deadline.checked_duration_since(Instant::now()) {
            thread::sleep(remaining);
        }
        if (offset + 1) % 60 == 0 {
            live_samples.push(live_allocated_bytes());
            private_samples.push(process_private_bytes());
        }
    }

    assert_retained_memory_is_at_steady_state(&state);
    let end_live = live_allocated_bytes();
    let end_private = process_private_bytes();
    live_samples.push(end_live);
    private_samples.push(end_private);
    assert_eq!(live_samples.len(), 61);
    assert_eq!(private_samples.len(), 61);
    record_and_assert_receipt(
        "retained-memory",
        3_600,
        pre_warm_live,
        pre_warm_private,
        start_live,
        start_private,
        end_live,
        end_private,
        &live_samples,
        &private_samples,
        &state,
    );
}

#[test]
#[ignore = "short release retained-memory steady-state probe"]
fn retained_memory_steady_state_probe_stays_bounded() {
    let mut state = chat_state();
    let mut terminal = Terminal::new(TestBackend::new(WIDTH, HEIGHT)).unwrap();
    let mut renderer = Renderer::new();
    render_initial(&mut state, &mut terminal, &mut renderer);
    let mut live_samples = Vec::with_capacity(11);
    let mut private_samples = Vec::with_capacity(11);
    let pre_warm_live = live_allocated_bytes();
    let pre_warm_private = process_private_bytes();
    let mut sequence =
        warm_retained_memory_to_steady_state(&mut state, &mut terminal, &mut renderer, 1);
    let start_live = live_allocated_bytes();
    let start_private = process_private_bytes();
    reset_live_allocation_peak();

    for offset in 0..100 {
        let index = RETAINED_MEMORY_STEADY_STATE_MESSAGES + offset;
        sequence =
            apply_complete_chat_message(&mut state, &mut terminal, &mut renderer, sequence, index);
        if (offset + 1) % 10 == 0 {
            live_samples.push(live_allocated_bytes());
            private_samples.push(process_private_bytes());
        }
    }

    assert_retained_memory_is_at_steady_state(&state);
    let end_live = live_allocated_bytes();
    let end_private = process_private_bytes();
    live_samples.push(end_live);
    private_samples.push(end_private);
    assert_eq!(live_samples.len(), 11);
    assert_eq!(private_samples.len(), 11);
    record_and_assert_receipt(
        "retained-memory-probe",
        100,
        pre_warm_live,
        pre_warm_private,
        start_live,
        start_private,
        end_live,
        end_private,
        &live_samples,
        &private_samples,
        &state,
    );
}

#[allow(clippy::too_many_arguments)]
fn record_and_assert_receipt(
    label: &str,
    measured_messages: usize,
    pre_warm_live: u64,
    pre_warm_private: u64,
    start_live: u64,
    start_private: u64,
    end_live: u64,
    end_private: u64,
    live_samples: &[u64],
    private_samples: &[u64],
    state: &AppState,
) {
    let sampled_peak = *live_samples.iter().max().unwrap();
    let peak_live = peak_live_allocated_bytes().max(sampled_peak);
    let max_live_growth = peak_live
        .checked_sub(start_live)
        .expect("live peak resets at the post-warm baseline");
    let end_live_growth = end_live.saturating_sub(start_live);
    let (retained_messages, evidence, retained_text_bytes) = retained_memory_counts(state);
    println!(
        "{label}-initialization unit=bytes live_pre_warm={pre_warm_live} live_steady_start={start_live} live_delta={} private_pre_warm={pre_warm_private} private_steady_start={start_private} private_delta={} informational=true",
        signed_delta(start_live, pre_warm_live),
        signed_delta(start_private, pre_warm_private),
    );
    println!(
        "{label}-live gate_scope=post-steady-state allocator=System unit=bytes warmup_messages={} measured_messages={measured_messages} samples={live_samples:?} start={start_live} end={end_live} peak={peak_live} max_growth={max_live_growth} end_growth={end_live_growth} limit={} retained_messages={retained_messages} evidence={evidence} retained_text_bytes={retained_text_bytes}",
        RETAINED_MEMORY_STEADY_STATE_MESSAGES, MAX_MEMORY_GROWTH_BYTES,
    );
    println!(
        "{label}-private gate=false informational=true unit=bytes samples={private_samples:?} start={start_private} end={end_private} delta={}",
        signed_delta(end_private, start_private),
    );
    assert!(
        max_live_growth < MAX_MEMORY_GROWTH_BYTES,
        "peak live allocated memory grew by {max_live_growth} bytes"
    );
    assert!(
        end_live_growth < MAX_MEMORY_GROWTH_BYTES,
        "end live allocated memory grew by {end_live_growth} bytes"
    );
}

fn signed_delta(end: u64, start: u64) -> i128 {
    i128::from(end) - i128::from(start)
}

fn warm_retained_memory_to_steady_state(
    state: &mut AppState,
    terminal: &mut Terminal<TestBackend>,
    renderer: &mut Renderer,
    mut sequence: u64,
) -> u64 {
    for index in 0..RETAINED_MEMORY_STEADY_STATE_MESSAGES {
        sequence = apply_complete_chat_message(state, terminal, renderer, sequence, index);
    }
    assert_retained_memory_is_at_steady_state(state);
    sequence
}

fn assert_retained_memory_is_at_steady_state(state: &AppState) {
    let (retained_messages, evidence, retained_text_bytes) = retained_memory_counts(state);
    assert_eq!(retained_messages, MAX_VISIBLE_MESSAGES_PER_AGENT);
    assert_eq!(evidence, MAX_VISIBLE_MESSAGES_PER_AGENT * 2);
    assert_eq!(
        retained_text_bytes,
        MAX_VISIBLE_MESSAGES_PER_AGENT * RETAINED_MESSAGE_BYTES
    );
}

fn retained_memory_counts(state: &AppState) -> (usize, usize, usize) {
    let agent = state.selected_chat_agent().unwrap();
    (
        state.chat_store().thread(agent).messages().len(),
        state.chat_store().event_evidence_len(),
        state.chat_store().retained_text_bytes(),
    )
}

fn apply_complete_chat_message(
    state: &mut AppState,
    terminal: &mut Terminal<TestBackend>,
    renderer: &mut Renderer,
    sequence: u64,
    index: usize,
) -> u64 {
    let message_id = format!("message:hour:{index:05}");
    let text = format!("{} hour-message-{index:05}", "x".repeat(2_048));
    let chunk_sequence = sequence + 1;
    state
        .reduce(chat_chunk_envelope(
            chunk_sequence,
            &format!("event:hour:{index}:chunk"),
            &message_id,
            1,
            &text,
        ))
        .unwrap();
    let complete_sequence = sequence + 2;
    state
        .reduce(chat_complete_envelope(
            complete_sequence,
            &format!("event:hour:{index}:complete"),
            &message_id,
            &text,
        ))
        .unwrap();
    let plan = state.take_render_plan().unwrap();
    renderer.draw(terminal, state, plan).unwrap();
    complete_sequence
}

fn render_initial(
    state: &mut AppState,
    terminal: &mut Terminal<TestBackend>,
    renderer: &mut Renderer,
) {
    state.set_terminal_area(Rect::new(0, 0, WIDTH, HEIGHT));
    let plan = state.take_render_plan().unwrap_or(RenderPlan::Full);
    renderer.draw(terminal, state, plan).unwrap();
}

fn chat_state() -> AppState {
    let mut state = AppState::controller();
    state.snapshot = Some(shared_snapshot());
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

fn shared_snapshot() -> ConsoleSnapshot {
    serde_json::from_str(include_str!("../../contracts/v1/controls_snapshot.json")).unwrap()
}

fn wire_envelope(sequence: u64, kind: &str, payload: Value) -> Envelope {
    serde_json::from_value(json!({
        "schema_version": 1,
        "message_id": format!("server:{sequence}"),
        "sequence": sequence,
        "state_version": 0,
        "timestamp_utc": "2026-08-03T00:00:00Z",
        "message_type": kind,
        "payload": payload,
    }))
    .unwrap()
}

fn chat_history_result_envelope(sequence: u64) -> Envelope {
    wire_envelope(
        sequence,
        "chat-history-result",
        json!({"agent_id": "v20-product", "next_cursor": null}),
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

fn chat_complete_envelope(
    sequence: u64,
    event_id: &str,
    message_id: &str,
    content: &str,
) -> Envelope {
    chat_envelope(
        sequence,
        event_id,
        message_id,
        "complete",
        None,
        None,
        Some(format!("{:x}", Sha256::digest(content.as_bytes()))),
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
        "environment os={} arch={} profile={} build_hash={} terminal={}x{}",
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
    );
}

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|path| path.parent())
        .unwrap()
        .to_path_buf()
}

#[repr(C)]
#[derive(Default)]
struct ProcessMemoryCountersEx {
    cb: u32,
    page_fault_count: u32,
    peak_working_set_size: usize,
    working_set_size: usize,
    quota_peak_paged_pool_usage: usize,
    quota_paged_pool_usage: usize,
    quota_peak_non_paged_pool_usage: usize,
    quota_non_paged_pool_usage: usize,
    pagefile_usage: usize,
    peak_pagefile_usage: usize,
    private_usage: usize,
}

#[link(name = "psapi")]
unsafe extern "system" {
    #[link_name = "GetProcessMemoryInfo"]
    fn get_process_memory_info(process: HANDLE, counters: *mut c_void, size: u32) -> i32;
}

fn process_private_bytes() -> u64 {
    let mut counters = ProcessMemoryCountersEx {
        cb: u32::try_from(size_of::<ProcessMemoryCountersEx>()).unwrap(),
        ..ProcessMemoryCountersEx::default()
    };
    // SAFETY: the struct layout matches PROCESS_MEMORY_COUNTERS_EX and cb is its exact size.
    let result = unsafe {
        get_process_memory_info(GetCurrentProcess(), (&raw mut counters).cast(), counters.cb)
    };
    assert_ne!(result, 0, "GetProcessMemoryInfo failed");
    u64::try_from(counters.private_usage).unwrap_or(u64::MAX)
}
