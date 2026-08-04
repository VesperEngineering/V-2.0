use std::fmt;

use serde::de::DeserializeOwned;
use serde::ser::SerializeStruct;
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
        let seconds = format!(
            "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}",
            current.wYear,
            current.wMonth,
            current.wDay,
            current.wHour,
            current.wMinute,
            current.wSecond,
        );
        if current.wMilliseconds == 0 {
            Self(format!("{seconds}Z"))
        } else {
            Self(format!("{seconds}.{:03}000Z", current.wMilliseconds))
        }
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
            let body = value
                .strip_suffix('Z')
                .or_else(|| value.strip_suffix("+00:00"))
                .expect("validated UTC suffix");
            let normalized = if let Some((seconds, fraction)) = body.split_once('.') {
                if fraction.bytes().all(|digit| digit == b'0') {
                    format!("{seconds}Z")
                } else {
                    format!("{seconds}.{fraction:0<6}Z")
                }
            } else {
                format!("{body}Z")
            };
            Ok(Self(normalized))
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
    let fractional_length_is_valid = bytes.len() == 19 || (21..=26).contains(&bytes.len());
    let shape_is_valid = fractional_length_is_valid
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

    pub(crate) fn from_input(value: String) -> Result<Self, &'static str> {
        let trimmed = value.trim();
        if (1..=512).contains(&trimmed.chars().count()) {
            Ok(Self(trimmed.to_owned()))
        } else {
            Err("string must contain 1 to 512 characters")
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Sha256Hex(String);

impl Serialize for Sha256Hex {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        serializer.serialize_str(&self.0)
    }
}

impl<'de> Deserialize<'de> for Sha256Hex {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let value = String::deserialize(deserializer)?;
        if value.len() == 64
            && value
                .as_bytes()
                .iter()
                .all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f'))
        {
            Ok(Self(value))
        } else {
            Err(serde::de::Error::custom(
                "SHA-256 must be 64 lowercase hexadecimal characters",
            ))
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DecimalString(String);

impl DecimalString {
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

impl Serialize for DecimalString {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        serializer.serialize_str(&self.0)
    }
}

impl<'de> Deserialize<'de> for DecimalString {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let value = String::deserialize(deserializer)?;
        if is_decimal_string(&value) {
            Ok(Self(value))
        } else {
            Err(serde::de::Error::custom(
                "decimal must be bounded canonical base-10 without exponent",
            ))
        }
    }
}

fn is_decimal_string(value: &str) -> bool {
    if !(1..=128).contains(&value.len()) {
        return false;
    }
    let unsigned = value.strip_prefix('-').unwrap_or(value);
    if unsigned.is_empty() {
        return false;
    }
    let mut parts = unsigned.split('.');
    let whole = parts.next().unwrap_or_default();
    let fraction = parts.next();
    if parts.next().is_some()
        || whole.is_empty()
        || !whole.bytes().all(|byte| byte.is_ascii_digit())
        || (whole.len() > 1 && whole.starts_with('0'))
    {
        return false;
    }
    fraction
        .is_none_or(|digits| !digits.is_empty() && digits.bytes().all(|byte| byte.is_ascii_digit()))
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub struct Priority(u8);

impl Priority {
    pub fn get(self) -> u8 {
        self.0
    }
}

impl<'de> Deserialize<'de> for Priority {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let value = u8::deserialize(deserializer)?;
        if value <= 100 {
            Ok(Self(value))
        } else {
            Err(serde::de::Error::custom(
                "priority must be between 0 and 100",
            ))
        }
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
        Self::from_input(value).map_err(serde::de::Error::custom)
    }
}

macro_rules! bounded_string {
    ($name:ident, $minimum:expr, $maximum:expr, $error:literal, $trim:expr) => {
        #[derive(Clone, Debug, PartialEq, Eq)]
        pub struct $name(String);

        impl $name {
            pub fn as_str(&self) -> &str {
                &self.0
            }
        }

        impl Serialize for $name {
            fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
            where
                S: serde::Serializer,
            {
                serializer.serialize_str(&self.0)
            }
        }

        impl<'de> Deserialize<'de> for $name {
            fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
            where
                D: Deserializer<'de>,
            {
                let value = String::deserialize(deserializer)?;
                let checked = if $trim { value.trim() } else { value.as_str() };
                if ($minimum..=$maximum).contains(&checked.chars().count()) {
                    Ok(Self(checked.to_owned()))
                } else {
                    Err(serde::de::Error::custom($error))
                }
            }
        }
    };
}

bounded_string!(
    LongText,
    1,
    8_000,
    "text must contain 1 to 8000 characters",
    false
);
bounded_string!(
    WindowsPathText,
    1,
    32_767,
    "path must contain 1 to 32767 characters",
    false
);
bounded_string!(
    ReasonText,
    1,
    2_000,
    "reason must contain 1 to 2000 characters",
    true
);
bounded_string!(
    RawConfirmationText,
    0,
    512,
    "confirmation text cannot exceed 512 characters",
    false
);

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct GitRevision(String);

impl Serialize for GitRevision {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        serializer.serialize_str(&self.0)
    }
}

impl<'de> Deserialize<'de> for GitRevision {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let value = String::deserialize(deserializer)?;
        if matches!(value.len(), 40 | 64)
            && value
                .bytes()
                .all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f'))
        {
            Ok(Self(value))
        } else {
            Err(serde::de::Error::custom(
                "Git revision must be 40 or 64 lowercase hexadecimal characters",
            ))
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SearchQuery(String);

impl SearchQuery {
    pub fn as_str(&self) -> &str {
        &self.0
    }

    pub(crate) fn from_input(value: String) -> Result<Self, &'static str> {
        let trimmed = value.trim();
        if (1..=256).contains(&trimmed.chars().count()) {
            Ok(Self(trimmed.to_owned()))
        } else {
            Err("search query must contain 1 to 256 characters")
        }
    }
}

impl Serialize for SearchQuery {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        serializer.serialize_str(&self.0)
    }
}

impl<'de> Deserialize<'de> for SearchQuery {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let value = String::deserialize(deserializer)?;
        Self::from_input(value).map_err(serde::de::Error::custom)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub struct SearchLimit(u8);

impl SearchLimit {
    pub fn get(self) -> u8 {
        self.0
    }

    pub(crate) fn maximum() -> Self {
        Self(100)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub struct SearchRequestId(u64);

impl SearchRequestId {
    pub fn get(self) -> u64 {
        self.0
    }

    pub(crate) fn from_sequence(value: u64) -> Result<Self, &'static str> {
        if value == 0 {
            Err("search request ID must be positive")
        } else {
            Ok(Self(value))
        }
    }
}

impl<'de> Deserialize<'de> for SearchRequestId {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let value = u64::deserialize(deserializer)?;
        Self::from_sequence(value).map_err(serde::de::Error::custom)
    }
}

impl<'de> Deserialize<'de> for SearchLimit {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let value = u8::deserialize(deserializer)?;
        if (1..=100).contains(&value) {
            Ok(Self(value))
        } else {
            Err(serde::de::Error::custom(
                "search limit must be between 1 and 100",
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

fn deserialize_finite<'de, D>(deserializer: D) -> Result<f64, D::Error>
where
    D: Deserializer<'de>,
{
    let value = f64::deserialize(deserializer)?;
    if value.is_finite() {
        Ok(value)
    } else {
        Err(serde::de::Error::custom(
            "floating-point value must be finite",
        ))
    }
}

fn deserialize_optional_nonnegative_finite<'de, D>(deserializer: D) -> Result<Option<f64>, D::Error>
where
    D: Deserializer<'de>,
{
    let value = deserialize_optional_finite(deserializer)?;
    if value.is_none_or(|item| item >= 0.0) {
        Ok(value)
    } else {
        Err(serde::de::Error::custom(
            "floating-point value must be nonnegative",
        ))
    }
}

fn deserialize_confidence<'de, D>(deserializer: D) -> Result<f64, D::Error>
where
    D: Deserializer<'de>,
{
    let value = deserialize_finite(deserializer)?;
    if (0.0..=1.0).contains(&value) {
        Ok(value)
    } else {
        Err(serde::de::Error::custom(
            "confidence must be between zero and one",
        ))
    }
}

fn deserialize_optional_confidence<'de, D>(deserializer: D) -> Result<Option<f64>, D::Error>
where
    D: Deserializer<'de>,
{
    let value = deserialize_optional_finite(deserializer)?;
    if value.is_none_or(|item| (0.0..=1.0).contains(&item)) {
        Ok(value)
    } else {
        Err(serde::de::Error::custom(
            "confidence must be between zero and one",
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

fn deserialize_optional_true<'de, D>(deserializer: D) -> Result<Option<bool>, D::Error>
where
    D: Deserializer<'de>,
{
    match Option::<bool>::deserialize(deserializer)? {
        None => Ok(None),
        Some(true) => Ok(Some(true)),
        Some(false) => Err(serde::de::Error::custom(
            "context_only must be true or null",
        )),
    }
}

fn deserialize_bounded_search_kinds<'de, D>(
    deserializer: D,
) -> Result<Vec<WireSearchKind>, D::Error>
where
    D: Deserializer<'de>,
{
    let values = Vec::<WireSearchKind>::deserialize(deserializer)?;
    if values.len() <= 10 {
        Ok(values)
    } else {
        Err(serde::de::Error::custom(
            "search kinds cannot exceed 10 entries",
        ))
    }
}

fn deserialize_bounded_search_screens<'de, D>(
    deserializer: D,
) -> Result<Vec<WireSearchScreen>, D::Error>
where
    D: Deserializer<'de>,
{
    let values = Vec::<WireSearchScreen>::deserialize(deserializer)?;
    if values.len() <= 9 {
        Ok(values)
    } else {
        Err(serde::de::Error::custom(
            "search screens cannot exceed 9 entries",
        ))
    }
}

fn deserialize_bounded_search_results<'de, D>(
    deserializer: D,
) -> Result<Vec<SearchResultPayload>, D::Error>
where
    D: Deserializer<'de>,
{
    let values = Vec::<SearchResultPayload>::deserialize(deserializer)?;
    if values.len() <= 100 {
        Ok(values)
    } else {
        Err(serde::de::Error::custom(
            "search results cannot exceed 100 entries",
        ))
    }
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
    SearchRequest,
    SearchResults,
    Command,
    CommandReceipt,
    Event,
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
    SearchRequest(SearchRequestPayload),
    SearchResults(SearchResultsPayload),
    Command(CommandMessagePayload),
    CommandReceipt(CommandReceiptPayload),
    Event(Box<EventPayload>),
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
            Self::SearchRequest(_) => MessageType::SearchRequest,
            Self::SearchResults(_) => MessageType::SearchResults,
            Self::Command(_) => MessageType::Command,
            Self::CommandReceipt(_) => MessageType::CommandReceipt,
            Self::Event(_) => MessageType::Event,
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
    snapshot: ConsoleSnapshot
});

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum WireSearchKind {
    Stock,
    Agent,
    Model,
    Order,
    Approval,
    Event,
    Evidence,
    Memory,
    Source,
    Note,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum WireSearchScreen {
    Portfolio,
    Agents,
    ModelsRegime,
    Orders,
    RiskApprovals,
    Timeline,
    DataEvidence,
    Memory,
    System,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum WireSearchRecordType {
    PortfolioRow,
    AgentCard,
    ModelOpinionRow,
    CandidateRow,
    OrderRow,
    ApprovalRow,
    TimelineRow,
    EvidenceRow,
    MemoryRow,
    SourceRow,
    RepositoryRow,
    Note,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq, Eq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SearchFiltersPayload {
    #[serde(default, deserialize_with = "deserialize_bounded_search_kinds")]
    pub kinds: Vec<WireSearchKind>,
    #[serde(default, deserialize_with = "deserialize_bounded_search_screens")]
    pub screens: Vec<WireSearchScreen>,
    #[serde(default)]
    pub source: Option<NonEmptyString>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SearchResultPayload {
    pub kind: WireSearchKind,
    pub record_type: WireSearchRecordType,
    pub record_id: SafeId,
    pub label: NonEmptyString,
    pub summary: NonEmptyString,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub occurred_at_utc: Option<UtcTimestamp>,
    pub source: NonEmptyString,
    pub screen: WireSearchScreen,
    #[serde(default, deserialize_with = "deserialize_optional_true")]
    pub context_only: Option<bool>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SearchRequestPayload {
    pub request_id: SearchRequestId,
    pub query: SearchQuery,
    pub filters: SearchFiltersPayload,
    pub limit: SearchLimit,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SearchResultsPayload {
    pub request_id: SearchRequestId,
    pub indexed_state_version: u64,
    #[serde(deserialize_with = "deserialize_bounded_search_results")]
    pub results: Vec<SearchResultPayload>,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub error: Option<NonEmptyString>,
}

const MAX_COMMAND_PAYLOAD_BYTES: usize = 64 * 1024;
const MAX_EVIDENCE_IDS: usize = 32;

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
pub enum CommandType {
    #[serde(rename = "note.add")]
    NoteAdd,
    #[serde(rename = "alert.dismiss")]
    AlertDismiss,
    #[serde(rename = "layout.reset")]
    LayoutReset,
    #[serde(rename = "approval.approve")]
    ApprovalApprove,
    #[serde(rename = "approval.hold")]
    ApprovalHold,
    #[serde(rename = "approval.reject")]
    ApprovalReject,
    #[serde(rename = "approval.rework")]
    ApprovalRework,
    #[serde(rename = "agent.send-message")]
    AgentSendMessage,
    #[serde(rename = "agent.enqueue")]
    AgentEnqueue,
    #[serde(rename = "agent.pause")]
    AgentPause,
    #[serde(rename = "agent.stop")]
    AgentStop,
    #[serde(rename = "agent.retry")]
    AgentRetry,
    #[serde(rename = "agent.set-priority")]
    AgentSetPriority,
    #[serde(rename = "risk.propose-limit")]
    RiskProposeLimit,
    #[serde(rename = "trading.pause")]
    TradingPause,
    #[serde(rename = "trading.emergency-stop")]
    TradingEmergencyStop,
    #[serde(rename = "service.pause")]
    ServicePause,
    #[serde(rename = "service.restart")]
    ServiceRestart,
    #[serde(rename = "runtime.start")]
    RuntimeStart,
    #[serde(rename = "runtime.stop-safe")]
    RuntimeStopSafe,
    #[serde(rename = "runtime.stop-force")]
    RuntimeStopForce,
    #[serde(rename = "runtime.prepare-shutdown")]
    RuntimePrepareShutdown,
    #[serde(rename = "mode.switch")]
    ModeSwitch,
    #[serde(rename = "mode.leave-live")]
    ModeLeaveLive,
    #[serde(rename = "mode.enable-live")]
    ModeEnableLive,
    #[serde(rename = "model.request-promotion")]
    ModelRequestPromotion,
    #[serde(rename = "model.request-rollback")]
    ModelRequestRollback,
    #[serde(rename = "memory.compress-now")]
    MemoryCompressNow,
    #[serde(rename = "backup.create")]
    BackupCreate,
    #[serde(rename = "backup.restore")]
    BackupRestore,
    #[serde(rename = "source-control.push")]
    SourceControlPush,
}

impl CommandType {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::NoteAdd => "note.add",
            Self::AlertDismiss => "alert.dismiss",
            Self::LayoutReset => "layout.reset",
            Self::ApprovalApprove => "approval.approve",
            Self::ApprovalHold => "approval.hold",
            Self::ApprovalReject => "approval.reject",
            Self::ApprovalRework => "approval.rework",
            Self::AgentSendMessage => "agent.send-message",
            Self::AgentEnqueue => "agent.enqueue",
            Self::AgentPause => "agent.pause",
            Self::AgentStop => "agent.stop",
            Self::AgentRetry => "agent.retry",
            Self::AgentSetPriority => "agent.set-priority",
            Self::RiskProposeLimit => "risk.propose-limit",
            Self::TradingPause => "trading.pause",
            Self::TradingEmergencyStop => "trading.emergency-stop",
            Self::ServicePause => "service.pause",
            Self::ServiceRestart => "service.restart",
            Self::RuntimeStart => "runtime.start",
            Self::RuntimeStopSafe => "runtime.stop-safe",
            Self::RuntimeStopForce => "runtime.stop-force",
            Self::RuntimePrepareShutdown => "runtime.prepare-shutdown",
            Self::ModeSwitch => "mode.switch",
            Self::ModeLeaveLive => "mode.leave-live",
            Self::ModeEnableLive => "mode.enable-live",
            Self::ModelRequestPromotion => "model.request-promotion",
            Self::ModelRequestRollback => "model.request-rollback",
            Self::MemoryCompressNow => "memory.compress-now",
            Self::BackupCreate => "backup.create",
            Self::BackupRestore => "backup.restore",
            Self::SourceControlPush => "source-control.push",
        }
    }

    fn forbids_reason(self) -> bool {
        matches!(
            self,
            Self::NoteAdd
                | Self::AlertDismiss
                | Self::LayoutReset
                | Self::AgentSendMessage
                | Self::MemoryCompressNow
        )
    }
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum ScreenName {
    Impact,
    Portfolio,
    Orders,
    Agents,
    ModelsRegime,
    Timeline,
    RiskApprovals,
    DataEvidence,
    Memory,
    System,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum NoteTargetType {
    Stock,
    Order,
    Approval,
    AgentEvent,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum NoteVisibility {
    Private,
    Shared,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum NonLiveMode {
    Shadow,
    Paper,
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EmptyPayload {}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct NoteAddPayload {
    pub target_type: NoteTargetType,
    pub target_id: SafeId,
    pub body: LongText,
    pub visibility: NoteVisibility,
}

strict_struct!(AlertDismissPayload { alert_id: SafeId });

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LayoutResetPayload {
    #[serde(default)]
    pub screen: Option<ScreenName>,
}

strict_struct!(ApprovalPayload {
    run_id: SafeId,
    checkpoint_id: SafeId,
});

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ApprovalReworkPayload {
    pub run_id: SafeId,
    pub checkpoint_id: SafeId,
    #[serde(deserialize_with = "deserialize_evidence_ids")]
    pub evidence_ids: Vec<SafeId>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AgentMessagePayload {
    pub agent_id: SafeId,
    pub text: LongText,
    #[serde(default)]
    pub selected_entity_type: Option<NonEmptyString>,
    #[serde(default)]
    pub selected_entity_id: Option<SafeId>,
}

strict_struct!(AgentEnqueuePayload {
    agent_id: SafeId,
    title: NonEmptyString,
    objective: LongText,
    priority: Priority,
});
strict_struct!(AgentWorkPayload { work_id: SafeId });

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AgentStopPayload {
    pub work_id: SafeId,
    #[serde(default)]
    pub workflow_run_id: Option<SafeId>,
}

strict_struct!(AgentPriorityPayload {
    work_id: SafeId,
    priority: Priority,
});

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RiskLimitPayload {
    pub limit_id: SafeId,
    pub proposed_value: DecimalString,
    #[serde(deserialize_with = "deserialize_evidence_ids")]
    pub evidence_ids: Vec<SafeId>,
}

strict_struct!(ServicePayload { service_id: SafeId });
strict_struct!(RuntimeStartPayload {
    mode: NonLiveMode,
    activation_receipt_id: SafeId,
});
strict_struct!(ModeSwitchPayload {
    target_mode: NonLiveMode,
});
strict_struct!(EnableLivePayload {
    desired_portfolio_id: SafeId,
});

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelDecisionPayload {
    pub candidate_id: SafeId,
    #[serde(deserialize_with = "deserialize_evidence_ids")]
    pub evidence_ids: Vec<SafeId>,
}

strict_struct!(CompressMemoryPayload { agent_id: SafeId });
strict_struct!(BackupCreatePayload {
    destination: WindowsPathText,
});
strict_struct!(BackupRestorePayload {
    archive: WindowsPathText,
    preview_hash: Sha256Hex,
    safety_backup_receipt_id: SafeId,
});
strict_struct!(SourceControlPushPayload {
    expected_revision: GitRevision,
});

fn deserialize_evidence_ids<'de, D>(deserializer: D) -> Result<Vec<SafeId>, D::Error>
where
    D: Deserializer<'de>,
{
    let values = Vec::<SafeId>::deserialize(deserializer)?;
    if values.len() <= MAX_EVIDENCE_IDS {
        Ok(values)
    } else {
        Err(serde::de::Error::custom(
            "evidence IDs cannot exceed 32 entries",
        ))
    }
}

#[derive(Clone, Debug, PartialEq)]
pub enum CommandPayload {
    NoteAdd(NoteAddPayload),
    AlertDismiss(AlertDismissPayload),
    LayoutReset(LayoutResetPayload),
    Approval(ApprovalPayload),
    ApprovalRework(ApprovalReworkPayload),
    AgentMessage(AgentMessagePayload),
    AgentEnqueue(AgentEnqueuePayload),
    AgentWork(AgentWorkPayload),
    AgentStop(AgentStopPayload),
    AgentPriority(AgentPriorityPayload),
    RiskLimit(RiskLimitPayload),
    Empty(EmptyPayload),
    Service(ServicePayload),
    RuntimeStart(RuntimeStartPayload),
    ModeSwitch(ModeSwitchPayload),
    EnableLive(EnableLivePayload),
    ModelDecision(ModelDecisionPayload),
    CompressMemory(CompressMemoryPayload),
    BackupCreate(BackupCreatePayload),
    BackupRestore(BackupRestorePayload),
    SourceControlPush(SourceControlPushPayload),
}

impl CommandPayload {
    pub fn model_name(&self) -> &'static str {
        match self {
            Self::NoteAdd(_) => "NoteAddPayload",
            Self::AlertDismiss(_) => "AlertDismissPayload",
            Self::LayoutReset(_) => "LayoutResetPayload",
            Self::Approval(_) => "ApprovalPayload",
            Self::ApprovalRework(_) => "ApprovalReworkPayload",
            Self::AgentMessage(_) => "AgentMessagePayload",
            Self::AgentEnqueue(_) => "AgentEnqueuePayload",
            Self::AgentWork(_) => "AgentWorkPayload",
            Self::AgentStop(_) => "AgentStopPayload",
            Self::AgentPriority(_) => "AgentPriorityPayload",
            Self::RiskLimit(_) => "RiskLimitPayload",
            Self::Empty(_) => "EmptyPayload",
            Self::Service(_) => "ServicePayload",
            Self::RuntimeStart(_) => "RuntimeStartPayload",
            Self::ModeSwitch(_) => "ModeSwitchPayload",
            Self::EnableLive(_) => "EnableLivePayload",
            Self::ModelDecision(_) => "ModelDecisionPayload",
            Self::CompressMemory(_) => "CompressMemoryPayload",
            Self::BackupCreate(_) => "BackupCreatePayload",
            Self::BackupRestore(_) => "BackupRestorePayload",
            Self::SourceControlPush(_) => "SourceControlPushPayload",
        }
    }

    fn from_value(command_type: CommandType, value: serde_json::Value) -> Result<Self, String> {
        macro_rules! parse {
            ($variant:ident, $kind:ty) => {
                serde_json::from_value::<$kind>(value)
                    .map(Self::$variant)
                    .map_err(|error| error.to_string())
            };
        }
        match command_type {
            CommandType::NoteAdd => parse!(NoteAdd, NoteAddPayload),
            CommandType::AlertDismiss => parse!(AlertDismiss, AlertDismissPayload),
            CommandType::LayoutReset => parse!(LayoutReset, LayoutResetPayload),
            CommandType::ApprovalApprove
            | CommandType::ApprovalHold
            | CommandType::ApprovalReject => parse!(Approval, ApprovalPayload),
            CommandType::ApprovalRework => parse!(ApprovalRework, ApprovalReworkPayload),
            CommandType::AgentSendMessage => parse!(AgentMessage, AgentMessagePayload),
            CommandType::AgentEnqueue => parse!(AgentEnqueue, AgentEnqueuePayload),
            CommandType::AgentPause | CommandType::AgentRetry => {
                parse!(AgentWork, AgentWorkPayload)
            }
            CommandType::AgentStop => parse!(AgentStop, AgentStopPayload),
            CommandType::AgentSetPriority => parse!(AgentPriority, AgentPriorityPayload),
            CommandType::RiskProposeLimit => parse!(RiskLimit, RiskLimitPayload),
            CommandType::TradingPause
            | CommandType::TradingEmergencyStop
            | CommandType::RuntimeStopSafe
            | CommandType::RuntimeStopForce
            | CommandType::RuntimePrepareShutdown => parse!(Empty, EmptyPayload),
            CommandType::ServicePause | CommandType::ServiceRestart => {
                parse!(Service, ServicePayload)
            }
            CommandType::RuntimeStart => parse!(RuntimeStart, RuntimeStartPayload),
            CommandType::ModeSwitch | CommandType::ModeLeaveLive => {
                parse!(ModeSwitch, ModeSwitchPayload)
            }
            CommandType::ModeEnableLive => parse!(EnableLive, EnableLivePayload),
            CommandType::ModelRequestPromotion | CommandType::ModelRequestRollback => {
                parse!(ModelDecision, ModelDecisionPayload)
            }
            CommandType::MemoryCompressNow => parse!(CompressMemory, CompressMemoryPayload),
            CommandType::BackupCreate => parse!(BackupCreate, BackupCreatePayload),
            CommandType::BackupRestore => parse!(BackupRestore, BackupRestorePayload),
            CommandType::SourceControlPush => {
                parse!(SourceControlPush, SourceControlPushPayload)
            }
        }
    }
}

impl Serialize for CommandPayload {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        match self {
            Self::NoteAdd(value) => value.serialize(serializer),
            Self::AlertDismiss(value) => value.serialize(serializer),
            Self::LayoutReset(value) => value.serialize(serializer),
            Self::Approval(value) => value.serialize(serializer),
            Self::ApprovalRework(value) => value.serialize(serializer),
            Self::AgentMessage(value) => value.serialize(serializer),
            Self::AgentEnqueue(value) => value.serialize(serializer),
            Self::AgentWork(value) => value.serialize(serializer),
            Self::AgentStop(value) => value.serialize(serializer),
            Self::AgentPriority(value) => value.serialize(serializer),
            Self::RiskLimit(value) => value.serialize(serializer),
            Self::Empty(value) => value.serialize(serializer),
            Self::Service(value) => value.serialize(serializer),
            Self::RuntimeStart(value) => value.serialize(serializer),
            Self::ModeSwitch(value) => value.serialize(serializer),
            Self::EnableLive(value) => value.serialize(serializer),
            Self::ModelDecision(value) => value.serialize(serializer),
            Self::CompressMemory(value) => value.serialize(serializer),
            Self::BackupCreate(value) => value.serialize(serializer),
            Self::BackupRestore(value) => value.serialize(serializer),
            Self::SourceControlPush(value) => value.serialize(serializer),
        }
    }
}

#[derive(Clone, Debug, Default, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ConfirmationProof {
    #[serde(default)]
    pub first_confirmed: bool,
    #[serde(default)]
    pub second_confirmed: bool,
    #[serde(default)]
    pub typed_text: Option<RawConfirmationText>,
    #[serde(default)]
    pub bound_preview_hash: Option<Sha256Hex>,
}

#[derive(Clone, Debug, PartialEq)]
pub struct CommandRequest {
    pub command_id: SafeId,
    pub command_type: CommandType,
    pub reviewed_control_version: u64,
    pub reviewed_control_hash: Sha256Hex,
    pub reason: Option<ReasonText>,
    pub confirmation: Option<ConfirmationProof>,
    pub payload: CommandPayload,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RawCommandRequest {
    command_id: SafeId,
    command_type: CommandType,
    reviewed_control_version: u64,
    reviewed_control_hash: Sha256Hex,
    #[serde(deserialize_with = "deserialize_required_option")]
    reason: Option<ReasonText>,
    #[serde(default)]
    confirmation: Option<ConfirmationProof>,
    payload: serde_json::Value,
}

impl<'de> Deserialize<'de> for CommandRequest {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let raw = RawCommandRequest::deserialize(deserializer)?;
        if serde_json::to_vec(&raw.payload)
            .map_err(serde::de::Error::custom)?
            .len()
            > MAX_COMMAND_PAYLOAD_BYTES
        {
            return Err(serde::de::Error::custom("payload-too-large"));
        }
        if raw.command_type.forbids_reason() && raw.reason.is_some() {
            return Err(serde::de::Error::custom("reason-forbidden"));
        }
        let payload = CommandPayload::from_value(raw.command_type, raw.payload)
            .map_err(serde::de::Error::custom)?;
        Ok(Self {
            command_id: raw.command_id,
            command_type: raw.command_type,
            reviewed_control_version: raw.reviewed_control_version,
            reviewed_control_hash: raw.reviewed_control_hash,
            reason: raw.reason,
            confirmation: raw.confirmation,
            payload,
        })
    }
}

impl Serialize for CommandRequest {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        let mut state = serializer.serialize_struct("CommandRequest", 7)?;
        state.serialize_field("command_id", &self.command_id)?;
        state.serialize_field("command_type", &self.command_type)?;
        state.serialize_field("reviewed_control_version", &self.reviewed_control_version)?;
        state.serialize_field("reviewed_control_hash", &self.reviewed_control_hash)?;
        state.serialize_field("reason", &self.reason)?;
        state.serialize_field("confirmation", &self.confirmation)?;
        state.serialize_field("payload", &self.payload)?;
        state.end()
    }
}

strict_struct!(CommandMessagePayload {
    request: CommandRequest,
});

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum ReceiptStatus {
    Accepted,
    Rejected,
    Running,
    Completed,
    Failed,
    Cancelled,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CommandReceipt {
    pub command_id: SafeId,
    pub status: ReceiptStatus,
    pub code: SafeId,
    pub safe_message: NonEmptyString,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub accepted_at_utc: Option<UtcTimestamp>,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub finished_at_utc: Option<UtcTimestamp>,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub result: Option<serde_json::Map<String, serde_json::Value>>,
}

strict_struct!(CommandReceiptPayload {
    receipt: CommandReceipt,
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
    pub alert_id: SafeId,
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
    pub operating_mode_reason: Option<NonEmptyString>,
    pub data_freshness: Freshness,
    #[serde(deserialize_with = "deserialize_optional_nonnegative_finite")]
    pub data_age_seconds: Option<f64>,
    pub regime_label: String,
    #[serde(deserialize_with = "deserialize_optional_confidence")]
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

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum AssetType {
    Stock,
    Etf,
    Cash,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum PortfolioChangeState {
    Unchanged,
    Proposed,
    Approved,
    Executing,
    Reconciling,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum PortfolioReconciliation {
    NotRequired,
    Pending,
    Matched,
    Mismatch,
    Unavailable,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PortfolioRow {
    pub symbol: SafeId,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub description: Option<String>,
    pub asset_type: AssetType,
    pub quantity: DecimalString,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub price: Option<DecimalString>,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub market_value: Option<DecimalString>,
    #[serde(deserialize_with = "deserialize_finite")]
    pub current_weight: f64,
    #[serde(deserialize_with = "deserialize_optional_finite")]
    pub proposed_weight: Option<f64>,
    #[serde(deserialize_with = "deserialize_optional_finite")]
    pub approved_weight: Option<f64>,
    pub change_state: PortfolioChangeState,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub confirmed_rank: Option<u64>,
    pub reconciliation: PortfolioReconciliation,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum AgentStage {
    Backlog,
    Queued,
    Running,
    Waiting,
    Done,
    Failed,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AgentCard {
    pub work_id: SafeId,
    pub agent: NonEmptyString,
    pub title: NonEmptyString,
    pub stage: AgentStage,
    pub priority: Priority,
    pub urgent: bool,
    #[serde(deserialize_with = "deserialize_optional_nonnegative_finite")]
    pub elapsed_seconds: Option<f64>,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub model: Option<String>,
    pub affected_areas: Vec<String>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TimelineRow {
    pub event_id: SafeId,
    pub occurred_at_utc: UtcTimestamp,
    pub impact: bool,
    pub severity: AlertSeverity,
    pub summary: NonEmptyString,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub agent_id: Option<SafeId>,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub symbol: Option<SafeId>,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub model_id: Option<SafeId>,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub approval_id: Option<SafeId>,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub order_id: Option<SafeId>,
    pub evidence_ids: Vec<SafeId>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct FillRow {
    pub fill_id: SafeId,
    pub quantity: DecimalString,
    pub price: DecimalString,
    pub fee: DecimalString,
    pub filled_at_utc: UtcTimestamp,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum OrderSide {
    Buy,
    Sell,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum OrderStatus {
    Proposed,
    Approved,
    Submitted,
    Partial,
    Filled,
    Rejected,
    Cancelled,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum OrderReconciliation {
    Pending,
    Matched,
    Mismatch,
    Unavailable,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct OrderRow {
    pub order_id: SafeId,
    pub symbol: SafeId,
    pub side: OrderSide,
    pub quantity: DecimalString,
    pub status: OrderStatus,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub submitted_at_utc: Option<UtcTimestamp>,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub broker_order_id: Option<String>,
    pub fills: Vec<FillRow>,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub expected_price: Option<DecimalString>,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub actual_price: Option<DecimalString>,
    pub reconciliation: OrderReconciliation,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelOpinionRow {
    pub model_id: SafeId,
    pub regime: NonEmptyString,
    #[serde(deserialize_with = "deserialize_confidence")]
    pub confidence: f64,
    pub as_of_utc: UtcTimestamp,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
pub enum StrategyName {
    #[serde(rename = "ml_model")]
    MlModel,
    #[serde(rename = "momentum")]
    Momentum,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum CandidateStatus {
    Training,
    Evaluating,
    Passed,
    Failed,
    Rejected,
    Active,
    Rollback,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CandidateRow {
    pub candidate_id: SafeId,
    pub family: NonEmptyString,
    pub strategy: StrategyName,
    pub status: CandidateStatus,
    pub evidence_ids: Vec<SafeId>,
    pub created_at_utc: UtcTimestamp,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum RiskLimitStatus {
    Within,
    Violated,
    Pending,
    Unavailable,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RiskLimitRow {
    pub limit_id: SafeId,
    pub current_value: DecimalString,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub proposed_value: Option<DecimalString>,
    pub status: RiskLimitStatus,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum ApprovalState {
    Pending,
    Approved,
    Held,
    Rejected,
    Rework,
    Stale,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ApprovalRow {
    pub approval_id: SafeId,
    pub state: ApprovalState,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub reason: Option<String>,
    pub evidence_ids: Vec<SafeId>,
    pub requested_at_utc: UtcTimestamp,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SourceRow {
    pub source_id: SafeId,
    pub freshness: Freshness,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub as_of_utc: Option<UtcTimestamp>,
    #[serde(deserialize_with = "deserialize_optional_nonnegative_finite")]
    pub age_seconds: Option<f64>,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub coverage: Option<String>,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub error: Option<String>,
    pub consumers: Vec<NonEmptyString>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct EvidenceRow {
    pub evidence_id: SafeId,
    pub evidence_type: NonEmptyString,
    pub source: NonEmptyString,
    pub created_at_utc: UtcTimestamp,
    pub sha256: Sha256Hex,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum MemoryStatus {
    Core,
    Archived,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MemoryRow {
    pub memory_id: SafeId,
    pub status: MemoryStatus,
    pub summary: NonEmptyString,
    pub evidence_ids: Vec<SafeId>,
    pub updated_at_utc: UtcTimestamp,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum ServiceState {
    Running,
    Paused,
    Stopped,
    Failed,
    Unavailable,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ServiceRow {
    pub service_id: SafeId,
    pub state: ServiceState,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub health_reason: Option<String>,
    pub observed_at_utc: UtcTimestamp,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RepositoryRow {
    pub repository_id: SafeId,
    pub freshness: Freshness,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub as_of_utc: Option<UtcTimestamp>,
    pub source: NonEmptyString,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub error: Option<String>,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub branch: Option<NonEmptyString>,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub revision: Option<NonEmptyString>,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub clean: Option<bool>,
    pub worktrees: Vec<NonEmptyString>,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub unpushed_commit_count: Option<u64>,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct MetricRow {
    pub metric_id: SafeId,
    #[serde(deserialize_with = "deserialize_optional_finite")]
    pub value: Option<f64>,
    pub unit: NonEmptyString,
    pub freshness: Freshness,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub observed_at_utc: Option<UtcTimestamp>,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub error: Option<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RawMetricRow {
    metric_id: SafeId,
    #[serde(deserialize_with = "deserialize_optional_finite")]
    value: Option<f64>,
    unit: NonEmptyString,
    freshness: Freshness,
    #[serde(deserialize_with = "deserialize_required_option")]
    observed_at_utc: Option<UtcTimestamp>,
    #[serde(deserialize_with = "deserialize_required_option")]
    error: Option<String>,
}

impl<'de> Deserialize<'de> for MetricRow {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let raw = RawMetricRow::deserialize(deserializer)?;
        let has_reason = raw
            .error
            .as_deref()
            .is_some_and(|value| !value.trim().is_empty());
        let valid = match raw.freshness {
            Freshness::Fresh => {
                raw.value.is_some() && raw.observed_at_utc.is_some() && raw.error.is_none()
            }
            Freshness::Stale => raw.value.is_some() && raw.observed_at_utc.is_some() && has_reason,
            Freshness::Unavailable => raw.value.is_none() && has_reason,
            Freshness::Loading => {
                raw.value.is_none() && raw.observed_at_utc.is_none() && raw.error.is_none()
            }
        };
        if !valid {
            return Err(serde::de::Error::custom(
                "metric freshness does not match value, time, and error",
            ));
        }
        Ok(Self {
            metric_id: raw.metric_id,
            value: raw.value,
            unit: raw.unit,
            freshness: raw.freshness,
            observed_at_utc: raw.observed_at_utc,
            error: raw.error,
        })
    }
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum ReturnComponent {
    Price,
    Dividends,
    CashInterest,
    Fees,
    Sp500TotalReturn,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ReturnComponentRow {
    pub component: ReturnComponent,
    pub value: DecimalString,
}

pub type AlertRow = AlertView;

#[derive(Clone, Copy, Debug, Deserialize, Hash, PartialEq, Eq, PartialOrd, Ord, Serialize)]
pub enum EventTarget {
    #[serde(rename = "shell.alerts")]
    ShellAlerts,
    #[serde(rename = "impact.holdings")]
    ImpactHoldings,
    #[serde(rename = "impact.events")]
    ImpactEvents,
    #[serde(rename = "impact.agents")]
    ImpactAgents,
    #[serde(rename = "portfolio.rows")]
    PortfolioRows,
    #[serde(rename = "portfolio.returns-today")]
    PortfolioReturnsToday,
    #[serde(rename = "portfolio.returns-since-rebalance")]
    PortfolioReturnsSinceRebalance,
    #[serde(rename = "portfolio.returns-since-start")]
    PortfolioReturnsSinceStart,
    #[serde(rename = "portfolio.metrics")]
    PortfolioMetrics,
    #[serde(rename = "portfolio.history")]
    PortfolioHistory,
    #[serde(rename = "orders.rows")]
    OrdersRows,
    #[serde(rename = "orders.reconciliation-agents")]
    OrdersReconciliationAgents,
    #[serde(rename = "orders.history")]
    OrdersHistory,
    #[serde(rename = "agents.rows")]
    AgentsRows,
    #[serde(rename = "agents.history")]
    AgentsHistory,
    #[serde(rename = "models.opinions")]
    ModelsOpinions,
    #[serde(rename = "models.candidates")]
    ModelsCandidates,
    #[serde(rename = "models.metrics")]
    ModelsMetrics,
    #[serde(rename = "models.evidence")]
    ModelsEvidence,
    #[serde(rename = "timeline.rows")]
    TimelineRows,
    #[serde(rename = "risk.limits")]
    RiskLimits,
    #[serde(rename = "risk.approvals")]
    RiskApprovals,
    #[serde(rename = "risk.alerts")]
    RiskAlerts,
    #[serde(rename = "risk.metrics")]
    RiskMetrics,
    #[serde(rename = "data.sources")]
    DataSources,
    #[serde(rename = "data.evidence")]
    DataEvidence,
    #[serde(rename = "memory.rows")]
    MemoryRows,
    #[serde(rename = "memory.history")]
    MemoryHistory,
    #[serde(rename = "system.services")]
    SystemServices,
    #[serde(rename = "system.metrics")]
    SystemMetrics,
    #[serde(rename = "system.repositories")]
    SystemRepositories,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct WindowOmission {
    pub target: EventTarget,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub omitted_count: Option<u64>,
}

fn validate_window_omissions(omissions: &[WindowOmission]) -> Result<(), &'static str> {
    if omissions
        .iter()
        .any(|omission| omission.omitted_count == Some(0))
    {
        return Err("window omission counts must be positive or null");
    }
    if omissions
        .windows(2)
        .any(|items| items[0].target >= items[1].target)
    {
        return Err("window omission targets must be unique and canonical");
    }
    Ok(())
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct ScreenMeta {
    pub freshness: Freshness,
    pub as_of_utc: Option<UtcTimestamp>,
    pub source: NonEmptyString,
    pub error: Option<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RawScreenMeta {
    freshness: Freshness,
    #[serde(deserialize_with = "deserialize_required_option")]
    as_of_utc: Option<UtcTimestamp>,
    source: NonEmptyString,
    #[serde(deserialize_with = "deserialize_required_option")]
    error: Option<String>,
}

impl<'de> Deserialize<'de> for ScreenMeta {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let raw = RawScreenMeta::deserialize(deserializer)?;
        validate_freshness(raw.freshness, raw.as_of_utc.as_ref(), raw.error.as_deref())
            .map_err(serde::de::Error::custom)?;
        Ok(Self {
            freshness: raw.freshness,
            as_of_utc: raw.as_of_utc,
            source: raw.source,
            error: raw.error,
        })
    }
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct EventPresentation {
    pub generated_at_utc: UtcTimestamp,
    pub header: HeaderView,
    pub control_version: u64,
    pub control_hash: Sha256Hex,
    pub window_omissions: Vec<WindowOmission>,
    pub impact: ScreenMeta,
    pub portfolio: ScreenMeta,
    pub orders: ScreenMeta,
    pub agents: ScreenMeta,
    pub models: ScreenMeta,
    pub timeline: ScreenMeta,
    pub risk: ScreenMeta,
    pub data: ScreenMeta,
    pub memory: ScreenMeta,
    pub system: ScreenMeta,
    pub portfolio_rank_source: Option<NonEmptyString>,
    pub timeline_hidden_event_count: u64,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RawEventPresentation {
    generated_at_utc: UtcTimestamp,
    header: HeaderView,
    control_version: u64,
    control_hash: Sha256Hex,
    window_omissions: Vec<WindowOmission>,
    impact: ScreenMeta,
    portfolio: ScreenMeta,
    orders: ScreenMeta,
    agents: ScreenMeta,
    models: ScreenMeta,
    timeline: ScreenMeta,
    risk: ScreenMeta,
    data: ScreenMeta,
    memory: ScreenMeta,
    system: ScreenMeta,
    #[serde(deserialize_with = "deserialize_required_option")]
    portfolio_rank_source: Option<NonEmptyString>,
    timeline_hidden_event_count: u64,
}

impl<'de> Deserialize<'de> for EventPresentation {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let raw = RawEventPresentation::deserialize(deserializer)?;
        validate_window_omissions(&raw.window_omissions).map_err(serde::de::Error::custom)?;
        Ok(Self {
            generated_at_utc: raw.generated_at_utc,
            header: raw.header,
            control_version: raw.control_version,
            control_hash: raw.control_hash,
            window_omissions: raw.window_omissions,
            impact: raw.impact,
            portfolio: raw.portfolio,
            orders: raw.orders,
            agents: raw.agents,
            models: raw.models,
            timeline: raw.timeline,
            risk: raw.risk,
            data: raw.data,
            memory: raw.memory,
            system: raw.system,
            portfolio_rank_source: raw.portfolio_rank_source,
            timeline_hidden_event_count: raw.timeline_hidden_event_count,
        })
    }
}

macro_rules! screen_view {
    ($name:ident { $($field:ident : $kind:ty),* $(,)? }) => {
        #[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
        #[serde(deny_unknown_fields)]
        pub struct $name {
            pub freshness: Freshness,
            #[serde(deserialize_with = "deserialize_required_option")]
            pub as_of_utc: Option<UtcTimestamp>,
            pub source: NonEmptyString,
            #[serde(deserialize_with = "deserialize_required_option")]
            pub error: Option<String>,
            $(pub $field: $kind),*
        }
    };
}

screen_view!(ImpactView {
    holdings: Vec<PortfolioRow>,
    events: Vec<TimelineRow>,
    agents: Vec<AgentCard>,
});
#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PortfolioView {
    pub freshness: Freshness,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub as_of_utc: Option<UtcTimestamp>,
    pub source: NonEmptyString,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub error: Option<String>,
    pub rows: Vec<PortfolioRow>,
    pub returns_today: Vec<ReturnComponentRow>,
    pub returns_since_rebalance: Vec<ReturnComponentRow>,
    pub returns_since_start: Vec<ReturnComponentRow>,
    pub metrics: Vec<MetricRow>,
    pub history: Vec<TimelineRow>,
    #[serde(deserialize_with = "deserialize_required_option")]
    pub rank_source: Option<NonEmptyString>,
}
screen_view!(OrdersView {
    rows: Vec<OrderRow>,
    reconciliation_agents: Vec<AgentCard>,
    history: Vec<TimelineRow>,
});
screen_view!(AgentsView {
    rows: Vec<AgentCard>,
    history: Vec<TimelineRow>,
});
screen_view!(ModelsView {
    opinions: Vec<ModelOpinionRow>,
    candidates: Vec<CandidateRow>,
    metrics: Vec<MetricRow>,
    evidence: Vec<EvidenceRow>,
});
screen_view!(TimelineView {
    rows: Vec<TimelineRow>,
    hidden_event_count: u64,
});
screen_view!(RiskView {
    limits: Vec<RiskLimitRow>,
    approvals: Vec<ApprovalRow>,
    alerts: Vec<AlertRow>,
    metrics: Vec<MetricRow>,
});
screen_view!(DataView {
    sources: Vec<SourceRow>,
    evidence: Vec<EvidenceRow>,
});
screen_view!(MemoryView {
    rows: Vec<MemoryRow>,
    history: Vec<TimelineRow>,
});
screen_view!(SystemView {
    services: Vec<ServiceRow>,
    metrics: Vec<MetricRow>,
    repositories: Vec<RepositoryRow>,
});

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum ReasonRule {
    Forbidden,
    Optional,
    Required,
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum ConfirmationLevel {
    None,
    Confirm,
    DoubleConfirm,
    TypedLive,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CommandSpecView {
    pub command_type: NonEmptyString,
    pub payload_model: NonEmptyString,
    pub capability_id: SafeId,
    pub reason_rule: ReasonRule,
    pub confirmation_level: ConfirmationLevel,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct ConsoleSnapshot {
    pub shell: ShellSnapshot,
    pub control_version: u64,
    pub control_hash: Sha256Hex,
    pub command_specs: Vec<CommandSpecView>,
    pub window_omissions: Vec<WindowOmission>,
    pub impact: ImpactView,
    pub portfolio: PortfolioView,
    pub orders: OrdersView,
    pub agents: AgentsView,
    pub models: ModelsView,
    pub timeline: TimelineView,
    pub risk: RiskView,
    pub data: DataView,
    pub memory: MemoryView,
    pub system: SystemView,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RawConsoleSnapshot {
    shell: ShellSnapshot,
    control_version: u64,
    control_hash: Sha256Hex,
    command_specs: Vec<CommandSpecView>,
    window_omissions: Vec<WindowOmission>,
    impact: ImpactView,
    portfolio: PortfolioView,
    orders: OrdersView,
    agents: AgentsView,
    models: ModelsView,
    timeline: TimelineView,
    risk: RiskView,
    data: DataView,
    memory: MemoryView,
    system: SystemView,
}

impl<'de> Deserialize<'de> for ConsoleSnapshot {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let raw = RawConsoleSnapshot::deserialize(deserializer)?;
        validate_window_omissions(&raw.window_omissions).map_err(serde::de::Error::custom)?;
        for (freshness, as_of_utc, error) in [
            (
                raw.impact.freshness,
                raw.impact.as_of_utc.as_ref(),
                raw.impact.error.as_deref(),
            ),
            (
                raw.portfolio.freshness,
                raw.portfolio.as_of_utc.as_ref(),
                raw.portfolio.error.as_deref(),
            ),
            (
                raw.orders.freshness,
                raw.orders.as_of_utc.as_ref(),
                raw.orders.error.as_deref(),
            ),
            (
                raw.agents.freshness,
                raw.agents.as_of_utc.as_ref(),
                raw.agents.error.as_deref(),
            ),
            (
                raw.models.freshness,
                raw.models.as_of_utc.as_ref(),
                raw.models.error.as_deref(),
            ),
            (
                raw.timeline.freshness,
                raw.timeline.as_of_utc.as_ref(),
                raw.timeline.error.as_deref(),
            ),
            (
                raw.risk.freshness,
                raw.risk.as_of_utc.as_ref(),
                raw.risk.error.as_deref(),
            ),
            (
                raw.data.freshness,
                raw.data.as_of_utc.as_ref(),
                raw.data.error.as_deref(),
            ),
            (
                raw.memory.freshness,
                raw.memory.as_of_utc.as_ref(),
                raw.memory.error.as_deref(),
            ),
            (
                raw.system.freshness,
                raw.system.as_of_utc.as_ref(),
                raw.system.error.as_deref(),
            ),
        ] {
            validate_freshness(freshness, as_of_utc, error).map_err(serde::de::Error::custom)?;
        }
        for source in &raw.data.sources {
            validate_freshness(
                source.freshness,
                source.as_of_utc.as_ref(),
                source.error.as_deref(),
            )
            .map_err(serde::de::Error::custom)?;
        }
        for repository in &raw.system.repositories {
            validate_freshness(
                repository.freshness,
                repository.as_of_utc.as_ref(),
                repository.error.as_deref(),
            )
            .map_err(serde::de::Error::custom)?;
        }
        Ok(Self {
            shell: raw.shell,
            control_version: raw.control_version,
            control_hash: raw.control_hash,
            command_specs: raw.command_specs,
            window_omissions: raw.window_omissions,
            impact: raw.impact,
            portfolio: raw.portfolio,
            orders: raw.orders,
            agents: raw.agents,
            models: raw.models,
            timeline: raw.timeline,
            risk: raw.risk,
            data: raw.data,
            memory: raw.memory,
            system: raw.system,
        })
    }
}

fn validate_freshness(
    freshness: Freshness,
    as_of_utc: Option<&UtcTimestamp>,
    error: Option<&str>,
) -> Result<(), &'static str> {
    if matches!(freshness, Freshness::Fresh | Freshness::Stale) && as_of_utc.is_none() {
        return Err("fresh and stale values require as_of_utc");
    }
    if matches!(freshness, Freshness::Stale | Freshness::Unavailable)
        && error.is_none_or(|value| value.trim().is_empty())
    {
        return Err("stale and unavailable values require an error reason");
    }
    if freshness == Freshness::Fresh && error.is_some() {
        return Err("fresh values cannot report an error");
    }
    Ok(())
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum EntityType {
    PortfolioRow,
    AgentCard,
    TimelineRow,
    OrderRow,
    ModelOpinionRow,
    CandidateRow,
    RiskLimitRow,
    ApprovalRow,
    SourceRow,
    EvidenceRow,
    MemoryRow,
    ServiceRow,
    RepositoryRow,
    MetricRow,
    ReturnComponentRow,
    AlertRow,
}

impl EventTarget {
    fn is_compatible(self, entity_type: EntityType) -> bool {
        matches!(
            (entity_type, self),
            (
                EntityType::PortfolioRow,
                Self::ImpactHoldings | Self::PortfolioRows
            ) | (
                EntityType::AgentCard,
                Self::ImpactAgents | Self::OrdersReconciliationAgents | Self::AgentsRows
            ) | (
                EntityType::TimelineRow,
                Self::ImpactEvents
                    | Self::PortfolioHistory
                    | Self::OrdersHistory
                    | Self::AgentsHistory
                    | Self::TimelineRows
                    | Self::MemoryHistory
            ) | (EntityType::OrderRow, Self::OrdersRows)
                | (EntityType::ModelOpinionRow, Self::ModelsOpinions)
                | (EntityType::CandidateRow, Self::ModelsCandidates)
                | (EntityType::RiskLimitRow, Self::RiskLimits)
                | (EntityType::ApprovalRow, Self::RiskApprovals)
                | (EntityType::SourceRow, Self::DataSources)
                | (
                    EntityType::EvidenceRow,
                    Self::ModelsEvidence | Self::DataEvidence
                )
                | (EntityType::MemoryRow, Self::MemoryRows)
                | (EntityType::ServiceRow, Self::SystemServices)
                | (EntityType::RepositoryRow, Self::SystemRepositories)
                | (
                    EntityType::MetricRow,
                    Self::PortfolioMetrics
                        | Self::ModelsMetrics
                        | Self::RiskMetrics
                        | Self::SystemMetrics
                )
                | (
                    EntityType::ReturnComponentRow,
                    Self::PortfolioReturnsToday
                        | Self::PortfolioReturnsSinceRebalance
                        | Self::PortfolioReturnsSinceStart
                )
                | (EntityType::AlertRow, Self::ShellAlerts | Self::RiskAlerts)
        )
    }
}

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum EventOperation {
    Upsert,
    Remove,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
#[serde(untagged)]
pub enum EventEntity {
    PortfolioRow(PortfolioRow),
    AgentCard(AgentCard),
    TimelineRow(TimelineRow),
    OrderRow(OrderRow),
    ModelOpinionRow(ModelOpinionRow),
    CandidateRow(CandidateRow),
    RiskLimitRow(RiskLimitRow),
    ApprovalRow(ApprovalRow),
    SourceRow(SourceRow),
    EvidenceRow(EvidenceRow),
    MemoryRow(MemoryRow),
    ServiceRow(ServiceRow),
    RepositoryRow(RepositoryRow),
    MetricRow(MetricRow),
    ReturnComponentRow(ReturnComponentRow),
    AlertRow(AlertRow),
}

impl EventEntity {
    fn primary_id(&self) -> &str {
        match self {
            Self::PortfolioRow(row) => row.symbol.as_str(),
            Self::AgentCard(row) => row.work_id.as_str(),
            Self::TimelineRow(row) => row.event_id.as_str(),
            Self::OrderRow(row) => row.order_id.as_str(),
            Self::ModelOpinionRow(row) => row.model_id.as_str(),
            Self::CandidateRow(row) => row.candidate_id.as_str(),
            Self::RiskLimitRow(row) => row.limit_id.as_str(),
            Self::ApprovalRow(row) => row.approval_id.as_str(),
            Self::SourceRow(row) => row.source_id.as_str(),
            Self::EvidenceRow(row) => row.evidence_id.as_str(),
            Self::MemoryRow(row) => row.memory_id.as_str(),
            Self::ServiceRow(row) => row.service_id.as_str(),
            Self::RepositoryRow(row) => row.repository_id.as_str(),
            Self::MetricRow(row) => row.metric_id.as_str(),
            Self::ReturnComponentRow(row) => match row.component {
                ReturnComponent::Price => "price",
                ReturnComponent::Dividends => "dividends",
                ReturnComponent::CashInterest => "cash-interest",
                ReturnComponent::Fees => "fees",
                ReturnComponent::Sp500TotalReturn => "sp500-total-return",
            },
            Self::AlertRow(row) => row.alert_id.as_str(),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct EventPayload {
    pub entity_type: EntityType,
    pub entity_id: SafeId,
    pub operation: EventOperation,
    pub entity: Option<EventEntity>,
    pub targets: Vec<EventTarget>,
    pub presentation: EventPresentation,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RawEventPayload {
    entity_type: EntityType,
    entity_id: SafeId,
    operation: EventOperation,
    #[serde(deserialize_with = "deserialize_required_option")]
    entity: Option<serde_json::Value>,
    targets: Vec<EventTarget>,
    presentation: EventPresentation,
}

impl<'de> Deserialize<'de> for EventPayload {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let RawEventPayload {
            entity_type,
            entity_id,
            operation,
            entity,
            targets,
            presentation,
        } = RawEventPayload::deserialize(deserializer)?;
        if !(1..=8).contains(&targets.len()) {
            return Err(serde::de::Error::custom(
                "event targets must contain one to eight entries",
            ));
        }
        if targets.windows(2).any(|items| items[0] >= items[1]) {
            return Err(serde::de::Error::custom(
                "event targets must be unique and canonical",
            ));
        }
        if targets
            .iter()
            .any(|target| !target.is_compatible(entity_type))
        {
            return Err(serde::de::Error::custom(
                "event target is incompatible with entity_type",
            ));
        }
        let entity = match (operation, entity) {
            (EventOperation::Remove, None) => None,
            (EventOperation::Remove, Some(_)) => {
                return Err(serde::de::Error::custom(
                    "remove events require a null entity",
                ));
            }
            (EventOperation::Upsert, None) => {
                return Err(serde::de::Error::custom(
                    "upsert events require a complete entity",
                ));
            }
            (EventOperation::Upsert, Some(value)) => {
                Some(parse_event_entity(entity_type, value).map_err(serde::de::Error::custom)?)
            }
        };
        if entity
            .as_ref()
            .is_some_and(|value| value.primary_id() != entity_id.as_str())
        {
            return Err(serde::de::Error::custom(
                "event entity_id does not match entity",
            ));
        }
        Ok(Self {
            entity_type,
            entity_id,
            operation,
            entity,
            targets,
            presentation,
        })
    }
}

fn parse_event_entity(
    entity_type: EntityType,
    value: serde_json::Value,
) -> Result<EventEntity, String> {
    fn parse<T: DeserializeOwned>(value: serde_json::Value) -> Result<T, String> {
        serde_json::from_value(value).map_err(|error| error.to_string())
    }
    let entity = match entity_type {
        EntityType::PortfolioRow => EventEntity::PortfolioRow(parse(value)?),
        EntityType::AgentCard => EventEntity::AgentCard(parse(value)?),
        EntityType::TimelineRow => EventEntity::TimelineRow(parse(value)?),
        EntityType::OrderRow => EventEntity::OrderRow(parse(value)?),
        EntityType::ModelOpinionRow => EventEntity::ModelOpinionRow(parse(value)?),
        EntityType::CandidateRow => EventEntity::CandidateRow(parse(value)?),
        EntityType::RiskLimitRow => EventEntity::RiskLimitRow(parse(value)?),
        EntityType::ApprovalRow => EventEntity::ApprovalRow(parse(value)?),
        EntityType::SourceRow => {
            let row: SourceRow = parse(value)?;
            validate_freshness(row.freshness, row.as_of_utc.as_ref(), row.error.as_deref())
                .map_err(|error| error.to_owned())?;
            EventEntity::SourceRow(row)
        }
        EntityType::EvidenceRow => EventEntity::EvidenceRow(parse(value)?),
        EntityType::MemoryRow => EventEntity::MemoryRow(parse(value)?),
        EntityType::ServiceRow => EventEntity::ServiceRow(parse(value)?),
        EntityType::RepositoryRow => {
            let row: RepositoryRow = parse(value)?;
            validate_freshness(row.freshness, row.as_of_utc.as_ref(), row.error.as_deref())
                .map_err(|error| error.to_owned())?;
            EventEntity::RepositoryRow(row)
        }
        EntityType::MetricRow => EventEntity::MetricRow(parse(value)?),
        EntityType::ReturnComponentRow => EventEntity::ReturnComponentRow(parse(value)?),
        EntityType::AlertRow => EventEntity::AlertRow(parse(value)?),
    };
    Ok(entity)
}

impl fmt::Display for MessageType {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        let value = serde_json::to_value(self).map_err(|_| fmt::Error)?;
        formatter.write_str(value.as_str().ok_or(fmt::Error)?)
    }
}
