use std::fmt;

use serde::{Deserialize, Deserializer, Serialize};
use windows_sys::Win32::Foundation::SYSTEMTIME;
use windows_sys::Win32::System::SystemInformation::GetSystemTime;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SafeId(String);

impl SafeId {
    pub fn as_str(&self) -> &str {
        &self.0
    }

    pub(crate) fn client_message(sequence: u64) -> Self {
        Self(format!("client:{sequence}"))
    }
}

impl Serialize for SafeId {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        serializer.serialize_str(&self.0)
    }
}

impl<'de> Deserialize<'de> for SafeId {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let value = String::deserialize(deserializer)?;
        let bytes = value.as_bytes();
        let valid = (1..=128).contains(&bytes.len())
            && value != "."
            && value != ".."
            && bytes[0].is_ascii_alphanumeric()
            && bytes.iter().all(|byte| {
                byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b':' | b'-')
            });
        if valid {
            Ok(Self(value))
        } else {
            Err(serde::de::Error::custom("invalid safe ID"))
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct UtcTimestamp(String);

impl UtcTimestamp {
    pub fn as_str(&self) -> &str {
        &self.0
    }

    pub(crate) fn now_utc() -> Self {
        let mut current = SYSTEMTIME::default();
        // SAFETY: current is a valid writable SYSTEMTIME for this synchronous call.
        unsafe { GetSystemTime(&raw mut current) };
        Self(format!(
            "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}.{:03}Z",
            current.wYear,
            current.wMonth,
            current.wDay,
            current.wHour,
            current.wMinute,
            current.wSecond,
            current.wMilliseconds,
        ))
    }
}

impl Serialize for UtcTimestamp {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        serializer.serialize_str(&self.0)
    }
}

impl<'de> Deserialize<'de> for UtcTimestamp {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let value = String::deserialize(deserializer)?;
        if is_utc_timestamp(&value) {
            Ok(Self(
                value
                    .strip_suffix("+00:00")
                    .map_or(value.clone(), |body| format!("{body}Z")),
            ))
        } else {
            Err(serde::de::Error::custom(
                "timestamp must be zero-offset UTC",
            ))
        }
    }
}

fn is_utc_timestamp(value: &str) -> bool {
    let utc_body = value
        .strip_suffix('Z')
        .or_else(|| value.strip_suffix("+00:00"));
    let Some(body) = utc_body else {
        return false;
    };
    let bytes = body.as_bytes();
    let shape_is_valid = bytes.len() >= 19
        && bytes.get(4) == Some(&b'-')
        && bytes.get(7) == Some(&b'-')
        && bytes.get(10) == Some(&b'T')
        && bytes.get(13) == Some(&b':')
        && bytes.get(16) == Some(&b':')
        && bytes.iter().enumerate().all(|(index, byte)| {
            matches!(index, 4 | 7 | 10 | 13 | 16)
                || (index == 19 && *byte == b'.')
                || byte.is_ascii_digit()
        });
    if !shape_is_valid || (bytes.len() > 19 && (bytes[19] != b'.' || bytes.len() == 20)) {
        return false;
    }
    let number = |start: usize, end: usize| {
        body.get(start..end)
            .and_then(|part| part.parse::<u32>().ok())
    };
    let (Some(year), Some(month), Some(day), Some(hour), Some(minute), Some(second)) = (
        number(0, 4),
        number(5, 7),
        number(8, 10),
        number(11, 13),
        number(14, 16),
        number(17, 19),
    ) else {
        return false;
    };
    let leap = year.is_multiple_of(4) && (!year.is_multiple_of(100) || year.is_multiple_of(400));
    let days = match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 if leap => 29,
        2 => 28,
        _ => return false,
    };
    year > 0 && (1..=days).contains(&day) && hour < 24 && minute < 60 && second < 60
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct NonEmptyString(String);

impl NonEmptyString {
    pub fn as_str(&self) -> &str {
        &self.0
    }

    pub(crate) fn literal(value: &'static str) -> Self {
        Self(value.to_owned())
    }
}

impl Serialize for NonEmptyString {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        serializer.serialize_str(&self.0)
    }
}

impl<'de> Deserialize<'de> for NonEmptyString {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let value = String::deserialize(deserializer)?;
        let trimmed = value.trim();
        if (1..=512).contains(&trimmed.chars().count()) {
            Ok(Self(trimmed.to_owned()))
        } else {
            Err(serde::de::Error::custom(
                "string must contain 1 to 512 bytes",
            ))
        }
    }
}

#[derive(Clone, PartialEq, Eq)]
pub struct PasswordString(String);

impl PasswordString {
    pub(crate) fn from_input(value: String) -> Result<Self, &'static str> {
        if (1..=1024).contains(&value.len()) {
            Ok(Self(value))
        } else {
            Err("password length is invalid")
        }
    }
}

impl fmt::Debug for PasswordString {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("<redacted>")
    }
}

impl Serialize for PasswordString {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        serializer.serialize_str(&self.0)
    }
}

impl<'de> Deserialize<'de> for PasswordString {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let value = String::deserialize(deserializer)?;
        if (1..=1024).contains(&value.chars().count()) {
            Ok(Self(value))
        } else {
            Err(serde::de::Error::custom("password length is invalid"))
        }
    }
}

fn deserialize_schema_versions<'de, D>(deserializer: D) -> Result<Vec<u8>, D::Error>
where
    D: Deserializer<'de>,
{
    let versions = Vec::<u8>::deserialize(deserializer)?;
    if versions.iter().all(|version| *version == 1) {
        Ok(versions)
    } else {
        Err(serde::de::Error::custom("unsupported schema version"))
    }
}

fn deserialize_true<'de, D>(deserializer: D) -> Result<bool, D::Error>
where
    D: Deserializer<'de>,
{
    let value = bool::deserialize(deserializer)?;
    if value {
        Ok(value)
    } else {
        Err(serde::de::Error::custom("value must be true"))
    }
}

fn deserialize_schema_one<'de, D>(deserializer: D) -> Result<u8, D::Error>
where
    D: Deserializer<'de>,
{
    let version = u8::deserialize(deserializer)?;
    if version == 1 {
        Ok(version)
    } else {
        Err(serde::de::Error::custom("unsupported schema version"))
    }
}

fn deserialize_optional_finite<'de, D>(deserializer: D) -> Result<Option<f64>, D::Error>
where
    D: Deserializer<'de>,
{
    let value = Option::<f64>::deserialize(deserializer)?;
    if value.is_none_or(f64::is_finite) {
        Ok(value)
    } else {
        Err(serde::de::Error::custom(
            "floating-point value must be finite",
        ))
    }
}

fn deserialize_required_option<'de, D, T>(deserializer: D) -> Result<Option<T>, D::Error>
where
    D: Deserializer<'de>,
    T: Deserialize<'de>,
{
    Option::<T>::deserialize(deserializer)
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum MessageType {
    ClientHello,
    ServerHello,
    AuthSetup,
    AuthUnlock,
    AuthResult,
    LeaseRequest,
    LeaseResult,
    LockRequest,
    LockResult,
    SnapshotRequest,
    Snapshot,
    ProtocolError,
    Ping,
    Pong,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Envelope {
    #[serde(deserialize_with = "deserialize_schema_one")]
    pub schema_version: u8,
    pub message_id: SafeId,
    pub sequence: u64,
    pub state_version: u64,
    pub timestamp_utc: UtcTimestamp,
    #[serde(flatten)]
    pub message: Message,
}

impl Envelope {
    pub fn message_type(&self) -> MessageType {
        self.message.message_type()
    }
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(tag = "message_type", content = "payload", rename_all = "kebab-case")]
pub enum Message {
    ClientHello(ClientHelloPayload),
    ServerHello(ServerHelloPayload),
    AuthSetup(AuthSetupPayload),
    AuthUnlock(AuthUnlockPayload),
    AuthResult(AuthResultPayload),
    LeaseRequest(LeaseRequestPayload),
    LeaseResult(LeaseResultPayload),
    LockRequest(LockRequestPayload),
    LockResult(LockResultPayload),
    SnapshotRequest(SnapshotRequestPayload),
    Snapshot(Box<SnapshotPayload>),
    ProtocolError(ProtocolErrorPayload),
    Ping(PingPayload),
    Pong(PongPayload),
}

impl Message {
    pub fn message_type(&self) -> MessageType {
        match self {
            Self::ClientHello(_) => MessageType::ClientHello,
            Self::ServerHello(_) => MessageType::ServerHello,
            Self::AuthSetup(_) => MessageType::AuthSetup,
            Self::AuthUnlock(_) => MessageType::AuthUnlock,
            Self::AuthResult(_) => MessageType::AuthResult,
            Self::LeaseRequest(_) => MessageType::LeaseRequest,
            Self::LeaseResult(_) => MessageType::LeaseResult,
            Self::LockRequest(_) => MessageType::LockRequest,
            Self::LockResult(_) => MessageType::LockResult,
            Self::SnapshotRequest(_) => MessageType::SnapshotRequest,
            Self::Snapshot(_) => MessageType::Snapshot,
            Self::ProtocolError(_) => MessageType::ProtocolError,
            Self::Ping(_) => MessageType::Ping,
            Self::Pong(_) => MessageType::Pong,
        }
    }
}

macro_rules! strict_struct {
    ($name:ident { $($field:ident : $kind:ty),* $(,)? }) => {
        #[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
        #[serde(deny_unknown_fields)]
        pub struct $name { $(pub $field: $kind),* }
    };
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ClientHelloPayload {
    pub client_version: NonEmptyString,
    #[serde(deserialize_with = "deserialize_schema_versions")]
    pub supported_schema_versions: Vec<u8>,
}
strict_struct!(ServerHelloPayload {
    server_version: NonEmptyString,
    requires_setup: bool,
});
strict_struct!(AuthSetupPayload {
    password: PasswordString,
    confirmation: PasswordString,
});
strict_struct!(AuthUnlockPayload {
    password: PasswordString
});

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum AccessState {
    Locked,
    Controller,
    Viewer,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AuthResultPayload {
    pub success: bool,
    pub access_state: AccessState,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub reason: Option<String>,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
pub enum TakeControlAction {
    #[serde(rename = "take-control")]
    TakeControl,
}
strict_struct!(LeaseRequestPayload {
    action: TakeControlAction
});

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum LeaseStatus {
    Controller,
    Viewer,
    Transferred,
    LeaseHeld,
}
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LeaseResultPayload {
    pub status: LeaseStatus,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub reason: Option<String>,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
pub enum LockAction {
    #[serde(rename = "lock")]
    Lock,
}
strict_struct!(LockRequestPayload { action: LockAction });
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LockResultPayload {
    #[serde(deserialize_with = "deserialize_true")]
    pub locked: bool,
}
strict_struct!(SnapshotRequestPayload {});
strict_struct!(SnapshotPayload {
    snapshot: ShellSnapshot
});
strict_struct!(ProtocolErrorPayload {
    code: SafeId,
    safe_message: NonEmptyString,
});
strict_struct!(PingPayload { nonce: SafeId });
strict_struct!(PongPayload { nonce: SafeId });

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum Freshness {
    Loading,
    Fresh,
    Stale,
    Unavailable,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum OperatingMode {
    Unknown,
    Stopped,
    Shadow,
    Paper,
    Live,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum CapabilityState {
    Enabled,
    ReadOnly,
    Disabled,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CapabilityView {
    pub capability_id: NonEmptyString,
    pub state: CapabilityState,
    pub reason: Option<NonEmptyString>,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum AlertSeverity {
    Info,
    Active,
    Waiting,
    Urgent,
    Resolved,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AlertView {
    pub alert_id: NonEmptyString,
    pub severity: AlertSeverity,
    pub summary: NonEmptyString,
    pub created_at_utc: UtcTimestamp,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub resolved_at_utc: Option<UtcTimestamp>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct HeaderView {
    pub operating_mode: OperatingMode,
    pub operating_mode_freshness: Freshness,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub operating_mode_reason: Option<String>,
    pub data_freshness: Freshness,
    #[serde(deserialize_with = "deserialize_optional_finite")]
    pub data_age_seconds: Option<f64>,
    pub regime_label: String,
    #[serde(deserialize_with = "deserialize_optional_finite")]
    pub regime_confidence: Option<f64>,
    #[serde(deserialize_with = "deserialize_optional_finite")]
    pub portfolio_value: Option<f64>,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub next_rebalance_at_utc: Option<UtcTimestamp>,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub rebalance_blockers: Option<Vec<String>>,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub active_agent: Option<String>,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub agent_queue_length: Option<u64>,
    pub qwen_state: String,
    #[serde(deserialize_with = "deserialize_optional_finite")]
    pub qwen_context_percent: Option<f64>,
    pub current_time_utc: UtcTimestamp,
    pub market_session: String,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ShellSnapshot {
    pub state_version: u64,
    pub generated_at_utc: UtcTimestamp,
    pub header: HeaderView,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub alerts: Option<Vec<AlertView>>,
    pub capabilities: Vec<CapabilityView>,
}

impl fmt::Display for MessageType {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        let value = serde_json::to_value(self).map_err(|_| fmt::Error)?;
        formatter.write_str(value.as_str().ok_or(fmt::Error)?)
    }
}
