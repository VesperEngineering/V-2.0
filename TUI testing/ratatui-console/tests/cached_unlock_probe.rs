use std::io;
use std::path::PathBuf;
use std::process::Stdio;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use ratatui::Terminal;
use ratatui::backend::TestBackend;
use serde_json::json;
use tokio::io::{AsyncBufRead, AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, ChildStdin, ChildStdout, Command};
use vesper_ratatui_console::app::{
    App, FoundationClient, FoundationSession, SessionError, SessionStep,
};
use vesper_ratatui_console::contract::{CapabilityState, Envelope};
use vesper_ratatui_console::input::InputEvent;
use vesper_ratatui_console::renderer::{RenderKind, Renderer};
use vesper_ratatui_console::state::{AccessState, AppState};
use vesper_ratatui_console::transport::{MAX_FRAME_BYTES, TransportError};

const WIDTH: u16 = 140;
const HEIGHT: u16 = 42;
const WARMUPS: usize = 10;
const SAMPLES: usize = 100;
const PROBE_IO_TIMEOUT: Duration = Duration::from_secs(10);
const PROBE_SHUTDOWN_TIMEOUT: Duration = Duration::from_secs(10);
const PROBE_REAP_TIMEOUT: Duration = Duration::from_secs(5);
const PROBE_LINE_LIMIT: usize = MAX_FRAME_BYTES + 1;

#[tokio::test(flavor = "current_thread")]
#[ignore = "runs 110 real Windows DPAPI and Python gateway samples"]
async fn real_dpapi_cached_unlock_reaches_the_backend_and_reaps_the_probe() {
    let mut probe = ProbeTransport::spawn()
        .await
        .expect("start disposable stdio probe");
    let probe_pid = probe.process_id();
    let mut samples_ns = Vec::with_capacity(SAMPLES);

    for iteration in 0..WARMUPS + SAMPLES {
        let password = synthetic_password(iteration);
        probe
            .begin_case(&password)
            .await
            .expect("start isolated cached-unlock case");
        let mut client = FoundationClient::from_app(App::new(AppState::locked()));
        let mut renderer = Renderer::new();
        let mut terminal = Terminal::new(TestBackend::new(WIDTH, HEIGHT)).expect("test terminal");

        let locked_plan = client
            .app_mut()
            .take_render_plan()
            .expect("locked view starts dirty");
        renderer
            .draw(&mut terminal, client.app().state(), locked_plan)
            .expect("render locked frame");

        client.start(&mut probe).await.expect("send client hello");
        assert_eq!(
            client
                .receive(&mut probe)
                .await
                .expect("receive server hello"),
            SessionStep::Continue
        );
        for character in password.chars() {
            assert_eq!(
                client
                    .handle_input(InputEvent::Char(character), &mut probe)
                    .await
                    .expect("enter synthetic password"),
                SessionStep::Continue
            );
        }
        let started = Instant::now();
        assert_eq!(
            client
                .handle_input(InputEvent::Enter, &mut probe)
                .await
                .expect("submit synthetic password"),
            SessionStep::Continue
        );
        assert_eq!(
            client
                .receive(&mut probe)
                .await
                .expect("receive successful authentication"),
            SessionStep::Continue
        );
        assert_eq!(client.app().state().access, AccessState::Viewer);

        assert_eq!(
            client
                .receive(&mut probe)
                .await
                .expect("receive cached snapshot"),
            SessionStep::Continue
        );
        let plan = client
            .app_mut()
            .take_render_plan()
            .expect("authentication and cached snapshot require a frame");
        let receipt = renderer
            .draw(&mut terminal, client.app().state(), plan)
            .expect("render cached frame");
        let elapsed_ns = u64::try_from(started.elapsed().as_nanos()).unwrap_or(u64::MAX);

        assert_eq!(receipt.kind, RenderKind::Full);
        assert!(
            backend_text(terminal.backend()).contains("STALE CACHE"),
            "first backend frame after authentication must identify cached state"
        );
        let snapshot = client
            .app()
            .state()
            .snapshot
            .as_ref()
            .expect("cached snapshot is retained");
        assert_eq!(snapshot.shell.header.qwen_state, "STALE CACHE");
        assert!(snapshot.command_specs.is_empty());
        assert!(
            snapshot
                .shell
                .capabilities
                .iter()
                .all(|capability| capability.state == CapabilityState::Disabled)
        );

        if iteration >= WARMUPS {
            samples_ns.push(elapsed_ns);
        }
    }

    let summary = TimingSummary::new(&samples_ns);
    println!(
        "cached_unlock start=auth-unlock-send end=first-test-backend-stale-frame transport=disposable-stdio cache=task9-current-user-dpapi warmups={WARMUPS} samples={SAMPLES} raw_ns={:?} median_ns={} p95_ns={} max_ns={}",
        samples_ns, summary.median_ns, summary.p95_ns, summary.max_ns
    );
    assert_eq!(samples_ns.len(), SAMPLES);
    assert!(
        summary.max_ns <= 1_000_000_000,
        "cached frame exceeded one second: {} ns",
        summary.max_ns
    );

    let reaped_pid = probe
        .shutdown()
        .await
        .expect("reap disposable probe process");
    assert_eq!(reaped_pid, probe_pid);
}

#[derive(Debug)]
struct TimingSummary {
    median_ns: u64,
    p95_ns: u64,
    max_ns: u64,
}

impl TimingSummary {
    fn new(samples: &[u64]) -> Self {
        assert_eq!(samples.len(), SAMPLES);
        let mut ordered = samples.to_vec();
        ordered.sort_unstable();
        let middle = ordered.len() / 2;
        let median_ns =
            ((u128::from(ordered[middle - 1]) + u128::from(ordered[middle])) / 2) as u64;
        let p95_ns = ordered[(ordered.len() * 95).div_ceil(100) - 1];
        let max_ns = *ordered.last().expect("samples are nonempty");
        Self {
            median_ns,
            p95_ns,
            max_ns,
        }
    }
}

struct ProbeTransport {
    child: Child,
    stdin: Option<ChildStdin>,
    stdout: BufReader<ChildStdout>,
    process_id: u32,
}

impl ProbeTransport {
    async fn spawn() -> io::Result<Self> {
        let repo_root = repo_root();
        let helper = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("tests")
            .join("support")
            .join("cached_unlock_probe.py");
        let uv_cache = std::env::var_os("UV_CACHE_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|| std::env::temp_dir().join("v20-tui-probe-uv-cache"));
        let mut command = Command::new("uv");
        command
            .current_dir(repo_root)
            .args(["run", "--locked", "--offline", "python"])
            .arg(helper)
            .env("UV_CACHE_DIR", uv_cache)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .kill_on_drop(true);
        let mut child = command.spawn()?;
        let Some(process_id) = child.id() else {
            kill_and_reap(&mut child).await?;
            return Err(io::Error::other("probe process has no ID"));
        };
        let Some(stdin) = child.stdin.take() else {
            kill_and_reap(&mut child).await?;
            return Err(io::Error::other("probe stdin is unavailable"));
        };
        let Some(stdout) = child.stdout.take() else {
            kill_and_reap(&mut child).await?;
            return Err(io::Error::other("probe stdout is unavailable"));
        };
        Ok(Self {
            child,
            stdin: Some(stdin),
            stdout: BufReader::new(stdout),
            process_id,
        })
    }

    const fn process_id(&self) -> u32 {
        self.process_id
    }

    async fn begin_case(&mut self, password: &str) -> io::Result<()> {
        let mut setup = serde_json::to_vec(&json!({"setup_password": password}))?;
        setup.push(b'\n');
        let stdin = self
            .stdin
            .as_mut()
            .ok_or_else(|| io::Error::new(io::ErrorKind::BrokenPipe, "probe stdin is closed"))?;
        tokio::time::timeout(PROBE_IO_TIMEOUT, async {
            stdin.write_all(&setup).await?;
            stdin.flush().await
        })
        .await
        .map_err(|_| io::Error::new(io::ErrorKind::TimedOut, "probe setup write timed out"))?
    }

    async fn shutdown(mut self) -> io::Result<u32> {
        drop(self.stdin.take());
        let status = match tokio::time::timeout(PROBE_SHUTDOWN_TIMEOUT, self.child.wait()).await {
            Ok(status) => status?,
            Err(_) => {
                self.child.start_kill()?;
                tokio::time::timeout(PROBE_REAP_TIMEOUT, self.child.wait())
                    .await
                    .map_err(|_| {
                        io::Error::new(
                            io::ErrorKind::TimedOut,
                            "probe could not be reaped after forced stop",
                        )
                    })??
            }
        };
        if !status.success() {
            return Err(io::Error::other(format!("probe exited with {status}")));
        }
        Ok(self.process_id)
    }
}

impl Drop for ProbeTransport {
    fn drop(&mut self) {
        drop(self.stdin.take());
        if matches!(self.child.try_wait(), Ok(Some(_))) {
            return;
        }
        let _ = self.child.start_kill();
        let deadline = Instant::now() + PROBE_REAP_TIMEOUT;
        while Instant::now() < deadline {
            if matches!(self.child.try_wait(), Ok(Some(_))) {
                return;
            }
            std::thread::sleep(Duration::from_millis(10));
        }
    }
}

impl FoundationSession for ProbeTransport {
    async fn send<'a>(&'a mut self, envelope: &'a Envelope) -> Result<(), SessionError> {
        let mut body = serde_json::to_vec(envelope)
            .map_err(TransportError::from)
            .map_err(SessionError::from)?;
        body.push(b'\n');
        let stdin = self.stdin.as_mut().ok_or(SessionError::Disconnected)?;
        tokio::time::timeout(PROBE_IO_TIMEOUT, async {
            stdin.write_all(&body).await?;
            stdin.flush().await
        })
        .await
        .map_err(|_| {
            session_io_error(io::Error::new(
                io::ErrorKind::TimedOut,
                "probe send timed out",
            ))
        })?
        .map_err(TransportError::from)
        .map_err(SessionError::from)
    }

    async fn recv(&mut self) -> Result<Envelope, SessionError> {
        let mut line = tokio::time::timeout(
            PROBE_IO_TIMEOUT,
            read_bounded_line(&mut self.stdout, PROBE_LINE_LIMIT),
        )
        .await
        .map_err(|_| {
            session_io_error(io::Error::new(
                io::ErrorKind::TimedOut,
                "probe receive timed out",
            ))
        })?
        .map_err(TransportError::from)
        .map_err(SessionError::from)?;
        while matches!(line.last(), Some(b'\r' | b'\n')) {
            line.pop();
        }
        let envelope: Envelope = serde_json::from_slice(&line)
            .map_err(TransportError::from)
            .map_err(SessionError::from)?;
        Ok(envelope)
    }
}

async fn read_bounded_line<R>(reader: &mut R, limit: usize) -> io::Result<Vec<u8>>
where
    R: AsyncBufRead + Unpin,
{
    let mut line = Vec::new();
    loop {
        let available = reader.fill_buf().await?;
        if available.is_empty() {
            return Err(io::Error::new(
                io::ErrorKind::UnexpectedEof,
                "probe output ended before a complete line",
            ));
        }
        let newline = available.iter().position(|byte| *byte == b'\n');
        let take = newline.map_or(available.len(), |index| index + 1);
        if line.len().saturating_add(take) > limit {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "probe output line exceeds the frame limit",
            ));
        }
        line.extend_from_slice(&available[..take]);
        reader.consume(take);
        if newline.is_some() {
            return Ok(line);
        }
    }
}

async fn kill_and_reap(child: &mut Child) -> io::Result<()> {
    let _ = child.start_kill();
    tokio::time::timeout(PROBE_REAP_TIMEOUT, child.wait())
        .await
        .map_err(|_| {
            io::Error::new(
                io::ErrorKind::TimedOut,
                "probe could not be reaped after spawn failure",
            )
        })??;
    Ok(())
}

fn session_io_error(error: io::Error) -> SessionError {
    SessionError::from(TransportError::from(error))
}

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .expect("crate is nested two levels under the repository")
        .to_path_buf()
}

fn synthetic_password(iteration: usize) -> String {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    format!("probe-{}-{iteration}-{nanos}", std::process::id())
}

fn backend_text(backend: &TestBackend) -> String {
    backend
        .buffer()
        .content
        .iter()
        .map(|cell| cell.symbol())
        .collect()
}

#[tokio::test(flavor = "current_thread")]
async fn probe_line_reader_rejects_oversized_output() {
    let (mut writer, reader) = tokio::io::duplex(32);
    let write = tokio::spawn(async move { writer.write_all(b"123456789\n").await });
    let error = read_bounded_line(&mut BufReader::new(reader), 8)
        .await
        .expect_err("oversized helper output must fail closed");
    assert_eq!(error.kind(), io::ErrorKind::InvalidData);
    write.await.unwrap().unwrap();
}
