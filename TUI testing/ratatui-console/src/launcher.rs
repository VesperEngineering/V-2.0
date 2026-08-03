use std::env;
use std::fmt;
use std::io;
use std::mem::size_of;
use std::os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle};
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::time::{Duration, Instant};

use tokio::io::AsyncReadExt;
use tokio::process::{Child, Command};
use windows_sys::Win32::Foundation::{HANDLE, INVALID_HANDLE_VALUE};
use windows_sys::Win32::System::Diagnostics::ToolHelp::{
    CreateToolhelp32Snapshot, TH32CS_SNAPTHREAD, THREADENTRY32, Thread32First, Thread32Next,
};
use windows_sys::Win32::System::JobObjects::{
    AssignProcessToJobObject, CreateJobObjectW, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    JOBOBJECT_BASIC_ACCOUNTING_INFORMATION, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
    JobObjectBasicAccountingInformation, JobObjectExtendedLimitInformation,
    QueryInformationJobObject, SetInformationJobObject, TerminateJobObject,
};
use windows_sys::Win32::System::Threading::{
    CREATE_SUSPENDED, OpenThread, ResumeThread, THREAD_SUSPEND_RESUME,
};

use crate::transport::PipeTransport;

const PIPE_PREFIX: &str = r"\\.\pipe\vesper-v20-tui-";
const PIPE_HASH_LENGTH: usize = 16;
const STDOUT_LIMIT: usize = 256;
const CONNECT_TIMEOUT: Duration = Duration::from_secs(3);
const DISCOVERY_TIMEOUT: Duration = Duration::from_secs(2);
const PROCESS_TREE_CLEANUP_TIMEOUT: Duration = Duration::from_secs(2);
const PROCESS_TREE_POLL_DELAY: Duration = Duration::from_millis(10);

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

struct ProcessJob {
    handle: Option<OwnedHandle>,
}

impl ProcessJob {
    fn armed() -> io::Result<Self> {
        // SAFETY: null security/name pointers request an unnamed job with default security.
        let raw = unsafe { CreateJobObjectW(std::ptr::null(), std::ptr::null()) };
        if raw.is_null() {
            return Err(io::Error::last_os_error());
        }
        // SAFETY: CreateJobObjectW returned a new owned handle checked above.
        let handle = unsafe { OwnedHandle::from_raw_handle(raw) };
        let job = Self {
            handle: Some(handle),
        };
        job.set_kill_on_close(true)?;
        Ok(job)
    }

    fn raw_handle(&self) -> HANDLE {
        self.handle
            .as_ref()
            .expect("job handle is present")
            .as_raw_handle() as HANDLE
    }

    fn set_kill_on_close(&self, enabled: bool) -> io::Result<()> {
        let mut limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
        if enabled {
            limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        }
        // SAFETY: limits points to the correctly sized information structure for this class.
        let success = unsafe {
            SetInformationJobObject(
                self.raw_handle(),
                JobObjectExtendedLimitInformation,
                (&raw const limits).cast(),
                size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            )
        };
        if success == 0 {
            Err(io::Error::last_os_error())
        } else {
            Ok(())
        }
    }

    fn assign(&self, child: &Child) -> io::Result<()> {
        let process_handle = child
            .raw_handle()
            .ok_or_else(|| io::Error::other("spawned process handle is unavailable"))?;
        // SAFETY: both handles are valid for the duration of this call.
        let success =
            unsafe { AssignProcessToJobObject(self.raw_handle(), process_handle as HANDLE) };
        if success == 0 {
            Err(io::Error::last_os_error())
        } else {
            Ok(())
        }
    }

    fn terminate(&self) -> io::Result<()> {
        // SAFETY: the job handle is valid and owned for the duration of this call.
        let success = unsafe { TerminateJobObject(self.raw_handle(), 1) };
        if success == 0 {
            Err(io::Error::last_os_error())
        } else {
            Ok(())
        }
    }

    fn active_processes(&self) -> io::Result<u32> {
        let mut accounting = JOBOBJECT_BASIC_ACCOUNTING_INFORMATION::default();
        // SAFETY: accounting is the correct writable structure for this information class.
        let success = unsafe {
            QueryInformationJobObject(
                self.raw_handle(),
                JobObjectBasicAccountingInformation,
                (&raw mut accounting).cast(),
                size_of::<JOBOBJECT_BASIC_ACCOUNTING_INFORMATION>() as u32,
                std::ptr::null_mut(),
            )
        };
        if success == 0 {
            Err(io::Error::last_os_error())
        } else {
            Ok(accounting.ActiveProcesses)
        }
    }

    async fn wait_until_empty(&self) -> io::Result<()> {
        let deadline = Instant::now() + PROCESS_TREE_CLEANUP_TIMEOUT;
        loop {
            if self.active_processes()? == 0 {
                return Ok(());
            }
            if Instant::now() >= deadline {
                return Err(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "managed process tree did not exit",
                ));
            }
            tokio::time::sleep(PROCESS_TREE_POLL_DELAY).await;
        }
    }

    fn disarm(&self) -> io::Result<()> {
        self.set_kill_on_close(false)
    }

    fn close(&mut self) {
        drop(self.handle.take());
    }

    fn into_handle(mut self) -> OwnedHandle {
        self.handle.take().expect("job handle is present")
    }
}

#[doc(hidden)]
pub struct ManagedChild {
    child: Child,
    job: ProcessJob,
}

impl ManagedChild {
    async fn terminate(mut self) -> io::Result<()> {
        let mut first_error = self.job.terminate().err();
        if first_error.is_some() {
            let _ = self.child.start_kill();
        }
        match tokio::time::timeout(PROCESS_TREE_CLEANUP_TIMEOUT, self.child.wait()).await {
            Ok(Ok(_)) => {}
            Ok(Err(error)) if first_error.is_none() => first_error = Some(error),
            Err(_) if first_error.is_none() => {
                first_error = Some(io::Error::new(
                    io::ErrorKind::TimedOut,
                    "managed process did not exit",
                ));
            }
            _ => {}
        }
        if let Err(error) = self.job.wait_until_empty().await
            && first_error.is_none()
        {
            first_error = Some(error);
        }
        self.job.close();
        match first_error {
            Some(error) => Err(error),
            None => Ok(()),
        }
    }

    fn split(self) -> (Child, OwnedHandle) {
        (self.child, self.job.into_handle())
    }
}

#[doc(hidden)]
pub async fn spawn_managed_command(command: Command) -> io::Result<ManagedChild> {
    let mut command = command;
    let mut job = ProcessJob::armed()?;
    command.creation_flags(CREATE_SUSPENDED);
    let mut child = command.spawn()?;
    let Some(process_id) = child.id() else {
        job.close();
        let _ = child.start_kill();
        let _ = child.wait().await;
        return Err(io::Error::other("spawned process has no ID"));
    };
    if let Err(error) = job.assign(&child) {
        job.close();
        let _ = child.start_kill();
        let _ = child.wait().await;
        return Err(error);
    }
    let process = ManagedChild { child, job };
    if let Err(error) = resume_primary_thread(process_id) {
        return match process.terminate().await {
            Ok(()) => Err(error),
            Err(cleanup_error) => Err(cleanup_error),
        };
    }
    Ok(process)
}

fn resume_primary_thread(process_id: u32) -> io::Result<()> {
    // SAFETY: the flags and process ID follow the ToolHelp API contract.
    let raw_snapshot = unsafe { CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0) };
    if raw_snapshot == INVALID_HANDLE_VALUE {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: ToolHelp returned a new owned snapshot handle checked above.
    let _snapshot = unsafe { OwnedHandle::from_raw_handle(raw_snapshot) };
    let mut entry = THREADENTRY32 {
        dwSize: size_of::<THREADENTRY32>() as u32,
        ..THREADENTRY32::default()
    };
    // SAFETY: entry has the required size and remains writable for the call.
    let mut found = unsafe { Thread32First(raw_snapshot, &raw mut entry) } != 0;
    let mut thread_id = None;
    while found {
        if entry.th32OwnerProcessID == process_id && thread_id.replace(entry.th32ThreadID).is_some()
        {
            return Err(io::Error::other(
                "suspended process has more than one thread",
            ));
        }
        // SAFETY: entry and snapshot remain valid across enumeration calls.
        found = unsafe { Thread32Next(raw_snapshot, &raw mut entry) } != 0;
    }
    let thread_id = thread_id.ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::NotFound,
            "suspended process thread was not found",
        )
    })?;
    // SAFETY: the thread ID came from the current ToolHelp snapshot.
    let raw_thread = unsafe { OpenThread(THREAD_SUSPEND_RESUME, 0, thread_id) };
    if raw_thread.is_null() {
        return Err(io::Error::last_os_error());
    }
    // SAFETY: OpenThread returned a new owned handle checked above.
    let thread = unsafe { OwnedHandle::from_raw_handle(raw_thread) };
    // SAFETY: the handle grants THREAD_SUSPEND_RESUME access.
    let previous_count = unsafe { ResumeThread(thread.as_raw_handle() as HANDLE) };
    if previous_count == u32::MAX {
        return Err(io::Error::last_os_error());
    }
    if previous_count != 1 {
        return Err(io::Error::other(format!(
            "suspended process had unexpected suspend count {previous_count}"
        )));
    }
    Ok(())
}

pub struct GatewayLauncher;

impl GatewayLauncher {
    pub async fn connect_or_start(repo_root: &Path) -> Result<PipeTransport, LaunchError> {
        let pipe_name = discover_pipe_name(repo_root).await?;
        match PipeTransport::connect(&pipe_name, CONNECT_TIMEOUT).await {
            Ok(transport) => Ok(transport),
            Err(error) if error.raw_os_error() == Some(2) => {
                let state_root = canonical_state_root()?;
                let process = start_gateway(repo_root, &state_root, &pipe_name).await?;
                connect_started_gateway(process, &pipe_name, CONNECT_TIMEOUT).await
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
    command
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    let mut process = spawn_managed_command(command).await?;
    let Some(stdout) = process.child.stdout.take() else {
        process.terminate().await?;
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
        Ok(DiscoveryOutcome::Complete(
            bytes,
            process.child.wait().await?,
        ))
    };
    let outcome = tokio::time::timeout(timeout, operation).await;
    process.terminate().await?;
    match outcome {
        Ok(Ok(DiscoveryOutcome::Complete(bytes, status))) if status.success() => {
            let output = std::str::from_utf8(&bytes).map_err(|_| LaunchError::InvalidPipeName)?;
            validate_pipe_name(output)
        }
        Ok(Ok(DiscoveryOutcome::Complete(_, _))) => Err(LaunchError::DiscoveryFailed),
        Ok(Ok(DiscoveryOutcome::Oversized)) => Err(LaunchError::InvalidPipeName),
        Ok(Err(error)) => Err(LaunchError::Io(error)),
        Err(_) => Err(LaunchError::DiscoveryFailed),
    }
}

#[doc(hidden)]
pub async fn connect_started_gateway(
    process: ManagedChild,
    pipe_name: &str,
    timeout: Duration,
) -> Result<PipeTransport, LaunchError> {
    match PipeTransport::connect(pipe_name, timeout).await {
        Ok(mut transport) => {
            if let Err(error) = process.job.disarm() {
                return match process.terminate().await {
                    Ok(()) => Err(LaunchError::Io(error)),
                    Err(cleanup_error) => Err(LaunchError::Io(cleanup_error)),
                };
            }
            let (child, job) = process.split();
            transport.retain_gateway_process(child, job);
            Ok(transport)
        }
        Err(error) => {
            process.terminate().await?;
            Err(LaunchError::Io(error))
        }
    }
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

async fn start_gateway(
    repo_root: &Path,
    state_root: &Path,
    pipe_name: &str,
) -> io::Result<ManagedChild> {
    let mut command = Command::new("uv");
    command
        .current_dir(repo_root)
        .args(gateway_args(state_root, pipe_name, std::process::id()))
        .stdin(Stdio::null());
    spawn_managed_command(command).await
}
