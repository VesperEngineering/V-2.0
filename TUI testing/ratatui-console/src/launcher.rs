use std::env;
use std::fmt;
use std::io;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::time::Duration;

use tokio::io::AsyncReadExt;
use tokio::process::{Child, Command};

use crate::transport::PipeTransport;

const PIPE_PREFIX: &str = r"\\.\pipe\vesper-v20-tui-";
const PIPE_HASH_LENGTH: usize = 16;
const STDOUT_LIMIT: usize = 256;
const CONNECT_TIMEOUT: Duration = Duration::from_secs(3);
const DISCOVERY_TIMEOUT: Duration = Duration::from_secs(2);

#[derive(Debug)]
pub enum LaunchError {
    Io(io::Error),
    DiscoveryFailed,
    InvalidPipeName,
    MissingLocalAppData,
    InvalidStateRoot,
}

impl fmt::Display for LaunchError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(error) => write!(formatter, "gateway launch I/O failed: {error}"),
            Self::DiscoveryFailed => formatter.write_str("gateway discovery command failed"),
            Self::InvalidPipeName => formatter.write_str("gateway returned an invalid pipe name"),
            Self::MissingLocalAppData => formatter.write_str("LOCALAPPDATA is unavailable"),
            Self::InvalidStateRoot => formatter.write_str("LOCALAPPDATA state root is invalid"),
        }
    }
}

impl std::error::Error for LaunchError {}

impl From<io::Error> for LaunchError {
    fn from(value: io::Error) -> Self {
        Self::Io(value)
    }
}

pub struct GatewayLauncher;

impl GatewayLauncher {
    pub async fn connect_or_start(repo_root: &Path) -> Result<PipeTransport, LaunchError> {
        let pipe_name = discover_pipe_name(repo_root).await?;
        match PipeTransport::connect(&pipe_name, CONNECT_TIMEOUT).await {
            Ok(transport) => Ok(transport),
            Err(error) if error.raw_os_error() == Some(2) => {
                let state_root = canonical_state_root()?;
                let child = start_gateway(repo_root, &state_root, &pipe_name)?;
                connect_started_gateway(child, &pipe_name, CONNECT_TIMEOUT).await
            }
            Err(error) => Err(LaunchError::Io(error)),
        }
    }
}

async fn discover_pipe_name(repo_root: &Path) -> Result<String, LaunchError> {
    let mut command = Command::new("uv");
    command.current_dir(repo_root).args([
        "run",
        "--locked",
        "vesper-tui-gateway",
        "--print-pipe-name",
    ]);
    discover_pipe_name_from_command(command, DISCOVERY_TIMEOUT).await
}

enum DiscoveryOutcome {
    Complete(Vec<u8>, std::process::ExitStatus),
    Oversized,
}

#[doc(hidden)]
pub async fn discover_pipe_name_from_command(
    mut command: Command,
    timeout: Duration,
) -> Result<String, LaunchError> {
    let mut child = command
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()?;
    let Some(stdout) = child.stdout.take() else {
        terminate_child(&mut child).await;
        return Err(LaunchError::DiscoveryFailed);
    };
    let operation = async {
        let mut bytes = Vec::new();
        stdout
            .take((STDOUT_LIMIT + 1) as u64)
            .read_to_end(&mut bytes)
            .await?;
        if bytes.len() > STDOUT_LIMIT {
            return Ok::<DiscoveryOutcome, io::Error>(DiscoveryOutcome::Oversized);
        }
        Ok(DiscoveryOutcome::Complete(bytes, child.wait().await?))
    };
    match tokio::time::timeout(timeout, operation).await {
        Ok(Ok(DiscoveryOutcome::Complete(bytes, status))) if status.success() => {
            let output = std::str::from_utf8(&bytes).map_err(|_| LaunchError::InvalidPipeName)?;
            validate_pipe_name(output)
        }
        Ok(Ok(DiscoveryOutcome::Complete(_, _))) => Err(LaunchError::DiscoveryFailed),
        Ok(Ok(DiscoveryOutcome::Oversized)) => {
            terminate_child(&mut child).await;
            Err(LaunchError::InvalidPipeName)
        }
        Ok(Err(error)) => {
            terminate_child(&mut child).await;
            Err(LaunchError::Io(error))
        }
        Err(_) => {
            terminate_child(&mut child).await;
            Err(LaunchError::DiscoveryFailed)
        }
    }
}

#[doc(hidden)]
pub async fn connect_started_gateway(
    mut child: Child,
    pipe_name: &str,
    timeout: Duration,
) -> Result<PipeTransport, LaunchError> {
    match PipeTransport::connect(pipe_name, timeout).await {
        Ok(mut transport) => {
            transport.retain_gateway_child(child);
            Ok(transport)
        }
        Err(error) => {
            terminate_child(&mut child).await;
            Err(LaunchError::Io(error))
        }
    }
}

async fn terminate_child(child: &mut Child) {
    let _ = child.start_kill();
    let _ = child.wait().await;
}

pub fn validate_pipe_name(output: &str) -> Result<String, LaunchError> {
    let name = output
        .strip_suffix("\r\n")
        .or_else(|| output.strip_suffix('\n'))
        .unwrap_or(output);
    let Some(hash) = name.strip_prefix(PIPE_PREFIX) else {
        return Err(LaunchError::InvalidPipeName);
    };
    if hash.len() != PIPE_HASH_LENGTH
        || !hash
            .bytes()
            .all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f'))
    {
        return Err(LaunchError::InvalidPipeName);
    }
    Ok(name.to_owned())
}

pub fn canonical_state_root() -> Result<PathBuf, LaunchError> {
    let local = env::var_os("LOCALAPPDATA").ok_or(LaunchError::MissingLocalAppData)?;
    let root = PathBuf::from(local).join("Vesper").join("v20").join("tui");
    if !root.is_absolute() || root.to_string_lossy().starts_with(r"\\") || root.to_str().is_none() {
        return Err(LaunchError::InvalidStateRoot);
    }
    Ok(root)
}

pub fn gateway_args(state_root: &Path, pipe_name: &str, parent_pid: u32) -> Vec<String> {
    vec![
        "run".into(),
        "--locked".into(),
        "vesper-tui-gateway".into(),
        "--state-root".into(),
        state_root.to_string_lossy().into_owned(),
        "--pipe-name".into(),
        pipe_name.into(),
        "--parent-pid".into(),
        parent_pid.to_string(),
    ]
}

fn start_gateway(repo_root: &Path, state_root: &Path, pipe_name: &str) -> io::Result<Child> {
    Command::new("uv")
        .current_dir(repo_root)
        .args(gateway_args(state_root, pipe_name, std::process::id()))
        .stdin(Stdio::null())
        .spawn()
}
