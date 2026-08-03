use std::fmt;
use std::io;
use std::os::windows::io::OwnedHandle;
use std::time::{Duration, Instant};

use tokio::io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt};
use tokio::net::windows::named_pipe::ClientOptions;
use tokio::process::Child;
use tokio::time::sleep;

use crate::contract::Envelope;

pub const MAX_FRAME_BYTES: usize = 1_048_576;
const RETRY_DELAY: Duration = Duration::from_millis(50);
const ERROR_FILE_NOT_FOUND: i32 = 2;
const ERROR_PIPE_BUSY: i32 = 231;

#[derive(Debug)]
pub enum TransportError {
    Io(io::Error),
    Json(serde_json::Error),
    InvalidFrame(&'static str),
}

trait AsyncStream: AsyncRead + AsyncWrite + Unpin {}
impl<T: AsyncRead + AsyncWrite + Unpin> AsyncStream for T {}

enum ReceiveProgress {
    Header { bytes: [u8; 4], offset: usize },
    Body { bytes: Vec<u8>, offset: usize },
}

struct SendProgress {
    frame: Vec<u8>,
    offset: usize,
}

impl fmt::Display for TransportError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(error) => write!(formatter, "pipe I/O failed: {error}"),
            Self::Json(error) => write!(formatter, "invalid envelope: {error}"),
            Self::InvalidFrame(message) => formatter.write_str(message),
        }
    }
}

impl std::error::Error for TransportError {}

impl From<io::Error> for TransportError {
    fn from(value: io::Error) -> Self {
        Self::Io(value)
    }
}

impl From<serde_json::Error> for TransportError {
    fn from(value: serde_json::Error) -> Self {
        Self::Json(value)
    }
}

pub struct PipeTransport {
    stream: Box<dyn AsyncStream + Send>,
    receive_progress: ReceiveProgress,
    send_progress: Option<SendProgress>,
    poisoned: bool,
    _gateway_child: Option<Child>,
    _gateway_job: Option<OwnedHandle>,
}

impl PipeTransport {
    pub async fn connect(name: &str, timeout: Duration) -> io::Result<Self> {
        let deadline = Instant::now() + timeout;
        loop {
            match ClientOptions::new().open(name) {
                Ok(client) => {
                    return Ok(Self {
                        stream: Box::new(client),
                        receive_progress: ReceiveProgress::Header {
                            bytes: [0; 4],
                            offset: 0,
                        },
                        send_progress: None,
                        poisoned: false,
                        _gateway_child: None,
                        _gateway_job: None,
                    });
                }
                Err(error)
                    if matches!(
                        error.raw_os_error(),
                        Some(ERROR_FILE_NOT_FOUND | ERROR_PIPE_BUSY)
                    ) && Instant::now() < deadline =>
                {
                    sleep(RETRY_DELAY.min(deadline.saturating_duration_since(Instant::now())))
                        .await;
                }
                Err(error) => return Err(error),
            }
        }
    }

    #[doc(hidden)]
    pub fn from_stream<T>(stream: T) -> Self
    where
        T: AsyncRead + AsyncWrite + Unpin + Send + 'static,
    {
        Self {
            stream: Box::new(stream),
            receive_progress: ReceiveProgress::Header {
                bytes: [0; 4],
                offset: 0,
            },
            send_progress: None,
            poisoned: false,
            _gateway_child: None,
            _gateway_job: None,
        }
    }

    pub(crate) fn retain_gateway_process(&mut self, child: Child, job: OwnedHandle) {
        self._gateway_child = Some(child);
        self._gateway_job = Some(job);
    }

    pub async fn send(&mut self, envelope: &Envelope) -> Result<(), TransportError> {
        self.require_healthy()?;
        let body = serde_json::to_vec(envelope)?;
        let frame = encode_frame_bytes(&body)?;
        if let Some(pending) = &self.send_progress {
            if pending.frame == frame {
                return self.finish_pending_send().await;
            }
            self.finish_pending_send().await?;
        }
        self.send_progress = Some(SendProgress { frame, offset: 0 });
        self.finish_pending_send().await
    }

    pub async fn recv(&mut self) -> Result<Envelope, TransportError> {
        self.require_healthy()?;
        loop {
            match &mut self.receive_progress {
                ReceiveProgress::Header { bytes, offset } => {
                    let read = match self.stream.read(&mut bytes[*offset..]).await {
                        Ok(0) => return Err(self.poison_eof()),
                        Ok(read) => read,
                        Err(error) => return Err(self.poison_io(error)),
                    };
                    *offset += read;
                    if *offset == bytes.len() {
                        let size = u32::from_be_bytes(*bytes) as usize;
                        if !(1..=MAX_FRAME_BYTES).contains(&size) {
                            self.poisoned = true;
                            return Err(TransportError::InvalidFrame("frame size is invalid"));
                        }
                        self.receive_progress = ReceiveProgress::Body {
                            bytes: vec![0; size],
                            offset: 0,
                        };
                    }
                }
                ReceiveProgress::Body { bytes, offset } => {
                    let read = match self.stream.read(&mut bytes[*offset..]).await {
                        Ok(0) => return Err(self.poison_eof()),
                        Ok(read) => read,
                        Err(error) => return Err(self.poison_io(error)),
                    };
                    *offset += read;
                    if *offset == bytes.len() {
                        let body = match std::mem::replace(
                            &mut self.receive_progress,
                            ReceiveProgress::Header {
                                bytes: [0; 4],
                                offset: 0,
                            },
                        ) {
                            ReceiveProgress::Body { bytes, .. } => bytes,
                            ReceiveProgress::Header { .. } => unreachable!(),
                        };
                        return match serde_json::from_slice(&body) {
                            Ok(envelope) => Ok(envelope),
                            Err(error) => {
                                self.poisoned = true;
                                Err(TransportError::Json(error))
                            }
                        };
                    }
                }
            }
        }
    }

    async fn finish_pending_send(&mut self) -> Result<(), TransportError> {
        loop {
            let Some(pending) = &mut self.send_progress else {
                return Ok(());
            };
            if pending.offset == pending.frame.len() {
                self.send_progress = None;
                return Ok(());
            }
            let written = match self.stream.write(&pending.frame[pending.offset..]).await {
                Ok(0) => return Err(self.poison_eof()),
                Ok(written) => written,
                Err(error) => return Err(self.poison_io(error)),
            };
            pending.offset += written;
        }
    }

    fn require_healthy(&self) -> Result<(), TransportError> {
        if self.poisoned {
            Err(TransportError::Io(io::Error::new(
                io::ErrorKind::BrokenPipe,
                "pipe transport is poisoned",
            )))
        } else {
            Ok(())
        }
    }

    fn poison_eof(&mut self) -> TransportError {
        self.poison_io(io::Error::new(
            io::ErrorKind::UnexpectedEof,
            "pipe closed during frame",
        ))
    }

    fn poison_io(&mut self, error: io::Error) -> TransportError {
        self.poisoned = true;
        TransportError::Io(error)
    }
}

pub fn encode_frame_bytes(body: &[u8]) -> Result<Vec<u8>, TransportError> {
    if !(1..=MAX_FRAME_BYTES).contains(&body.len()) {
        return Err(TransportError::InvalidFrame("frame size is invalid"));
    }
    let size = u32::try_from(body.len())
        .map_err(|_| TransportError::InvalidFrame("frame size is invalid"))?;
    let mut frame = Vec::with_capacity(4 + body.len());
    frame.extend_from_slice(&size.to_be_bytes());
    frame.extend_from_slice(body);
    Ok(frame)
}

pub fn decode_frame_bytes(frame: &[u8]) -> Result<Option<&[u8]>, TransportError> {
    if frame.len() < 4 {
        return Ok(None);
    }
    let size = u32::from_be_bytes(frame[..4].try_into().expect("four-byte frame prefix")) as usize;
    if !(1..=MAX_FRAME_BYTES).contains(&size) {
        return Err(TransportError::InvalidFrame("frame size is invalid"));
    }
    let expected = 4 + size;
    if frame.len() < expected {
        return Ok(None);
    }
    if frame.len() != expected {
        return Err(TransportError::InvalidFrame("frame has trailing bytes"));
    }
    Ok(Some(&frame[4..]))
}
