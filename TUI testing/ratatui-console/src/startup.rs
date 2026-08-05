use std::ffi::{OsStr, OsString};
use std::fmt;

use crate::contract::SafeId;

#[derive(Clone, PartialEq, Eq)]
pub enum StartupIntent {
    Dashboard,
    Alert(SafeId),
}

impl fmt::Debug for StartupIntent {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Dashboard => formatter.write_str("Dashboard"),
            Self::Alert(_) => formatter.write_str("Alert(<redacted>)"),
        }
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub struct StartupArgumentError;

impl fmt::Debug for StartupArgumentError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("StartupArgumentError")
    }
}

impl fmt::Display for StartupArgumentError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("invalid startup request")
    }
}

impl std::error::Error for StartupArgumentError {}

pub fn parse_startup_args(
    arguments: impl IntoIterator<Item = OsString>,
) -> Result<StartupIntent, StartupArgumentError> {
    let mut arguments = arguments.into_iter();
    let Some(flag) = arguments.next() else {
        return Ok(StartupIntent::Dashboard);
    };
    if flag != OsStr::new("--alert-id") {
        return Err(StartupArgumentError);
    }
    let value = arguments.next().ok_or(StartupArgumentError)?;
    if arguments.next().is_some() {
        return Err(StartupArgumentError);
    }
    let value = value.into_string().map_err(|_| StartupArgumentError)?;
    SafeId::parse(value)
        .map(StartupIntent::Alert)
        .map_err(|()| StartupArgumentError)
}
