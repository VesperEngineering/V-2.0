use std::collections::BTreeMap;
use std::ffi::OsStr;
use std::fs::{File, OpenOptions};
use std::io::{self, Read, Write};
use std::os::windows::ffi::OsStrExt;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use serde::{Deserialize, Serialize};
use windows_sys::Win32::Storage::FileSystem::{
    MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH, MoveFileExW,
};

use crate::layout::DisplayMode;
use crate::theme::Theme;

pub const PREFERENCES_VERSION: u16 = 1;
const MAX_PREFERENCES_BYTES: u64 = 64 * 1024;
const MAX_VISIBLE_COLUMNS: usize = 32;
const MAX_COLUMN_NAME_BYTES: usize = 64;
const MAX_PANEL_SIZES: usize = 16;
const MAX_PANEL_SIZE: u16 = 10_000;
static NEXT_TEMP_FILE: AtomicU64 = AtomicU64::new(1);

#[derive(Clone, Copy, Debug, Deserialize, Ord, PartialOrd, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum ScreenId {
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

#[derive(Clone, Debug, Default, Deserialize, PartialEq, Eq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ScreenPreferences {
    pub visible_columns: Vec<String>,
    pub panel_sizes: Vec<u16>,
}

#[derive(Clone, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct UiPreferences {
    pub version: u16,
    pub theme: Theme,
    pub display_mode: DisplayMode,
    pub screens: BTreeMap<ScreenId, ScreenPreferences>,
}

impl Default for UiPreferences {
    fn default() -> Self {
        Self {
            version: PREFERENCES_VERSION,
            theme: Theme::WarmWhite,
            display_mode: DisplayMode::Standard,
            screens: BTreeMap::new(),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LoadedPreferences {
    pub preferences: UiPreferences,
    pub unavailable_reason: Option<String>,
}

pub fn preferences_path_from(local_app_data: &Path) -> PathBuf {
    local_app_data
        .join("Vesper")
        .join("v20")
        .join("tui")
        .join("preferences.json")
}

pub fn preferences_path() -> io::Result<PathBuf> {
    crate::launcher::canonical_state_root()
        .map(|root| root.join("preferences.json"))
        .map_err(io::Error::other)
}

pub fn load_preferences() -> LoadedPreferences {
    match preferences_path() {
        Ok(path) => load_preferences_from(&path),
        Err(error) => LoadedPreferences {
            preferences: UiPreferences::default(),
            unavailable_reason: Some(error.to_string()),
        },
    }
}

pub fn load_preferences_from(path: &Path) -> LoadedPreferences {
    match load_valid_preferences(path) {
        Ok(preferences) => LoadedPreferences {
            preferences,
            unavailable_reason: None,
        },
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => LoadedPreferences {
            preferences: UiPreferences::default(),
            unavailable_reason: None,
        },
        Err(error) => LoadedPreferences {
            preferences: UiPreferences::default(),
            unavailable_reason: Some(error.to_string()),
        },
    }
}

fn load_valid_preferences(path: &Path) -> std::io::Result<UiPreferences> {
    let bytes = read_bounded_preferences(File::open(path)?)?;
    let preferences: UiPreferences = serde_json::from_slice(&bytes)
        .map_err(|error| std::io::Error::new(std::io::ErrorKind::InvalidData, error))?;
    validate_preferences(&preferences)?;
    Ok(preferences)
}

#[doc(hidden)]
pub fn read_bounded_preferences(reader: impl Read) -> io::Result<Vec<u8>> {
    let mut bytes = Vec::with_capacity(MAX_PREFERENCES_BYTES as usize);
    reader
        .take(MAX_PREFERENCES_BYTES + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() as u64 > MAX_PREFERENCES_BYTES {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "preferences exceed the 64 KiB limit",
        ));
    }
    Ok(bytes)
}

pub fn save_preferences(preferences: &UiPreferences) -> io::Result<()> {
    save_preferences_to(&preferences_path()?, preferences)
}

pub fn save_preferences_to(path: &Path, preferences: &UiPreferences) -> io::Result<()> {
    validate_preferences(preferences)?;
    let mut document = serde_json::to_vec_pretty(preferences)
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
    document.push(b'\n');
    if document.len() as u64 > MAX_PREFERENCES_BYTES {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "preferences exceed the 64 KiB limit",
        ));
    }

    let parent = path.parent().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidInput,
            "preferences path has no parent",
        )
    })?;
    std::fs::create_dir_all(parent)?;
    let (temporary, mut file) = OwnedTempFile::create(parent, path.file_name())?;
    file.write_all(&document)?;
    file.flush()?;
    file.sync_all()?;
    drop(file);
    temporary.replace(path)
}

fn validate_preferences(preferences: &UiPreferences) -> io::Result<()> {
    if preferences.version != PREFERENCES_VERSION {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "unsupported preferences version",
        ));
    }
    for screen in preferences.screens.values() {
        if screen.visible_columns.len() > MAX_VISIBLE_COLUMNS {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "too many visible columns",
            ));
        }
        if screen.panel_sizes.len() > MAX_PANEL_SIZES {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "too many panel sizes",
            ));
        }
        for column in &screen.visible_columns {
            if column.is_empty()
                || column.len() > MAX_COLUMN_NAME_BYTES
                || column.trim() != column
                || column.chars().any(char::is_control)
            {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    "visible column name is invalid",
                ));
            }
        }
        if screen
            .panel_sizes
            .iter()
            .any(|size| *size == 0 || *size > MAX_PANEL_SIZE)
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "panel size is outside the supported range",
            ));
        }
    }
    Ok(())
}

struct OwnedTempFile {
    path: PathBuf,
    replaced: bool,
}

impl OwnedTempFile {
    fn create(parent: &Path, target_name: Option<&OsStr>) -> io::Result<(Self, File)> {
        let target_name = target_name
            .and_then(OsStr::to_str)
            .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "invalid target name"))?;
        for _ in 0..100 {
            let sequence = NEXT_TEMP_FILE.fetch_add(1, Ordering::Relaxed);
            let path = parent.join(format!(
                ".{target_name}.tmp-{}-{sequence}",
                std::process::id()
            ));
            match OpenOptions::new().write(true).create_new(true).open(&path) {
                Ok(file) => {
                    return Ok((
                        Self {
                            path,
                            replaced: false,
                        },
                        file,
                    ));
                }
                Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
                Err(error) => return Err(error),
            }
        }
        Err(io::Error::new(
            io::ErrorKind::AlreadyExists,
            "could not allocate an owned preferences temp file",
        ))
    }

    fn replace(mut self, target: &Path) -> io::Result<()> {
        let source = wide_path(&self.path)?;
        let destination = wide_path(target)?;
        // SAFETY: both paths are valid, NUL-terminated UTF-16 buffers for this call.
        let replaced = unsafe {
            MoveFileExW(
                source.as_ptr(),
                destination.as_ptr(),
                MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
            )
        };
        if replaced == 0 {
            return Err(io::Error::last_os_error());
        }
        self.replaced = true;
        Ok(())
    }
}

impl Drop for OwnedTempFile {
    fn drop(&mut self) {
        if !self.replaced {
            let _ = std::fs::remove_file(&self.path);
        }
    }
}

fn wide_path(path: &Path) -> io::Result<Vec<u16>> {
    let mut path = path.as_os_str().encode_wide().collect::<Vec<_>>();
    if path.contains(&0) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "path contains a NUL character",
        ));
    }
    path.push(0);
    Ok(path)
}
