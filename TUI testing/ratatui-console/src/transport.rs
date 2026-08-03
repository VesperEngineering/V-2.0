use std::fmt;
use std::io;
use std::time::{Duration, Instant};

use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::windows::named_pipe::{ClientOptions, NamedPipeClient};
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
    client: NamedPipeClient,
    _gateway_child: Option<Child>,
}

impl PipeTransport {
    pub async fn connect(name: &str, timeout: Duration) -> io::Result<Self> {
        let deadline = Instant::now() + timeout;
        loop {
            match ClientOptions::new().open(name) {
                Ok(client) => {
                    return Ok(Self {
                        client,
                        _gateway_child: None,
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

    pub(crate) fn retain_gateway_child(&mut self, child: Child) {
        self._gateway_child = Some(child);
    }

    pub async fn send(&mut self, envelope: &Envelope) -> Result<(), TransportError> {
        let body = serde_json::to_vec(envelope)?;
        let frame = encode_frame_bytes(&body)?;
        self.client.write_all(&frame).await?;
        self.client.flush().await?;
        Ok(())
    }

    pub async fn recv(&mut self) -> Result<Envelope, TransportError> {
        let mut header = [0_u8; 4];
        self.client.read_exact(&mut header).await?;
        let size = u32::from_be_bytes(header) as usize;
        if !(1..=MAX_FRAME_BYTES).contains(&size) {
            return Err(TransportError::InvalidFrame("frame size is invalid"));
        }
        let mut body = vec![0_u8; size];
        self.client.read_exact(&mut body).await?;
        Ok(serde_json::from_slice(&body)?)
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
