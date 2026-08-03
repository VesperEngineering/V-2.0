use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use vesper_ratatui_console::app::{PreferencePersistence, persist_pending_preferences_to};
use vesper_ratatui_console::layout::DisplayMode;
use vesper_ratatui_console::preferences::{
    LoadedPreferences, PREFERENCES_VERSION, ScreenId, ScreenPreferences, UiPreferences,
    load_preferences_from, preferences_path_from, read_bounded_preferences, save_preferences_to,
};
use vesper_ratatui_console::state::{AccessState, AppState};
use vesper_ratatui_console::theme::Theme;

static NEXT_TEST_DIRECTORY: AtomicU64 = AtomicU64::new(1);

#[test]
fn preferences_path_is_exactly_local_app_data_v20_tui() {
    let base = Path::new(r"C:\Users\operator\AppData\Local");
    assert_eq!(
        preferences_path_from(base),
        PathBuf::from(r"C:\Users\operator\AppData\Local\Vesper\v20\tui\preferences.json")
    );
}

#[test]
fn corrupt_preferences_fail_to_bounded_defaults_with_visible_unavailable_state() {
    let directory = unique_test_directory("corrupt");
    std::fs::create_dir_all(&directory).expect("create isolated test directory");
    let path = directory.join("preferences.json");
    std::fs::write(&path, br#"{"version":1,"theme":"WarmWhite","extra":true}"#)
        .expect("write corrupt preferences fixture");

    let loaded = load_preferences_from(&path);

    assert_eq!(loaded.preferences, UiPreferences::default());
    assert_eq!(loaded.preferences.version, PREFERENCES_VERSION);
    assert_eq!(loaded.preferences.theme, Theme::WarmWhite);
    assert_eq!(loaded.preferences.display_mode, DisplayMode::Standard);
    assert!(loaded.unavailable_reason.is_some());

    std::fs::remove_dir_all(directory).expect("remove owned test directory");
}

#[test]
fn missing_preferences_use_defaults_without_claiming_unavailable() {
    let directory = unique_test_directory("missing");
    let loaded = load_preferences_from(&directory.join("preferences.json"));

    assert_eq!(loaded.preferences, UiPreferences::default());
    assert_eq!(loaded.unavailable_reason, None);
}

#[test]
fn valid_preferences_round_trip_and_atomically_replace_the_previous_file() {
    let directory = unique_test_directory("roundtrip");
    let path = directory.join("preferences.json");
    let mut preferences = UiPreferences {
        theme: Theme::Charcoal,
        display_mode: DisplayMode::LargeText,
        ..UiPreferences::default()
    };
    preferences.screens.insert(
        ScreenId::Impact,
        ScreenPreferences {
            visible_columns: vec!["symbol".to_owned(), "impact".to_owned()],
            panel_sizes: vec![60, 40],
        },
    );

    save_preferences_to(&path, &UiPreferences::default()).expect("initial atomic save");
    save_preferences_to(&path, &preferences).expect("atomic replacement");

    let loaded = load_preferences_from(&path);
    assert_eq!(loaded.preferences, preferences);
    assert_eq!(loaded.unavailable_reason, None);
    assert_eq!(
        std::fs::read_to_string(&path).expect("read saved preferences"),
        serde_json::to_string_pretty(&preferences).expect("serialize expected preferences") + "\n"
    );
    assert!(
        std::fs::read_dir(&directory)
            .expect("read preference directory")
            .all(|entry| !entry
                .expect("directory entry")
                .file_name()
                .to_string_lossy()
                .contains(".tmp-"))
    );

    std::fs::remove_dir_all(directory).expect("remove owned test directory");
}

#[test]
fn preferences_reject_unknown_screens_and_out_of_bounds_layout_values() {
    let directory = unique_test_directory("bounds");
    std::fs::create_dir_all(&directory).expect("create isolated test directory");
    let path = directory.join("preferences.json");
    let invalid_documents = [
        json_document(r#"{"unknown":{"visible_columns":[],"panel_sizes":[]}}"#),
        json_document(&format!(
            r#"{{"impact":{{"visible_columns":[{}],"panel_sizes":[]}}}}"#,
            (0..33)
                .map(|index| format!(r#""column-{index}""#))
                .collect::<Vec<_>>()
                .join(",")
        )),
        json_document(r#"{"impact":{"visible_columns":["symbol"],"panel_sizes":[0]}}"#),
    ];

    for document in invalid_documents {
        std::fs::write(&path, document).expect("write invalid preferences fixture");
        let loaded = load_preferences_from(&path);
        assert_eq!(loaded.preferences, UiPreferences::default());
        assert!(loaded.unavailable_reason.is_some());
    }

    std::fs::remove_dir_all(directory).expect("remove owned test directory");
}

#[test]
fn failed_atomic_replace_preserves_the_original_and_cleans_only_its_temp() {
    let directory = unique_test_directory("replace-failure");
    let target_directory = directory.join("preferences.json");
    std::fs::create_dir_all(&target_directory).expect("create replacement blocker");
    let sentinel = target_directory.join("original-remains.txt");
    std::fs::write(&sentinel, "original").expect("write original sentinel");

    let error = save_preferences_to(&target_directory, &UiPreferences::default())
        .expect_err("replacing a directory must fail");

    assert!(!error.to_string().is_empty());
    assert_eq!(
        std::fs::read_to_string(sentinel).expect("original sentinel remains"),
        "original"
    );
    assert!(
        std::fs::read_dir(&directory)
            .expect("read preference directory")
            .all(|entry| !entry
                .expect("directory entry")
                .file_name()
                .to_string_lossy()
                .contains(".tmp-"))
    );

    std::fs::remove_dir_all(directory).expect("remove owned test directory");
}

#[test]
fn bounded_reader_rejects_more_than_64_kib_without_unbounded_allocation() {
    let oversized = std::io::Cursor::new(vec![b'x'; 64 * 1024 + 1]);
    let error = read_bounded_preferences(oversized).expect_err("oversized input must fail");
    assert_eq!(error.kind(), std::io::ErrorKind::InvalidData);
}

#[test]
fn changed_state_persists_through_the_production_helper_and_reloads() {
    let directory = unique_test_directory("state-persistence");
    let path = directory.join("preferences.json");
    let mut state = AppState::controller();
    state.apply_loaded_preferences(LoadedPreferences {
        preferences: UiPreferences::default(),
        unavailable_reason: Some("redacted test failure".to_owned()),
    });
    state.set_theme(Theme::Charcoal);
    state.set_display_mode(DisplayMode::LargeText);
    state.set_screen_preferences(
        ScreenId::Portfolio,
        ScreenPreferences {
            visible_columns: vec!["symbol".to_owned(), "weight".to_owned()],
            panel_sizes: vec![65, 35],
        },
    );

    assert_eq!(
        persist_pending_preferences_to(&mut state, &path),
        PreferencePersistence::Saved
    );

    let reloaded = load_preferences_from(&path);
    assert_eq!(reloaded.preferences, *state.preferences());
    assert_eq!(reloaded.unavailable_reason, None);
    assert!(!state.preferences_unavailable());

    std::fs::remove_dir_all(directory).expect("remove owned test directory");
}

#[test]
fn failed_state_persistence_keeps_running_warns_and_does_not_hammer() {
    let directory = unique_test_directory("state-persistence-failure");
    let blocked_path = directory.join("preferences.json");
    std::fs::create_dir_all(&blocked_path).expect("create replacement blocker");
    let mut state = AppState::controller();
    state.set_theme(Theme::Charcoal);

    assert_eq!(
        persist_pending_preferences_to(&mut state, &blocked_path),
        PreferencePersistence::Unavailable
    );
    assert_eq!(state.access, AccessState::Controller);
    assert_eq!(state.theme(), Theme::Charcoal);
    assert!(state.preferences_unavailable());
    assert_eq!(
        persist_pending_preferences_to(&mut state, &blocked_path),
        PreferencePersistence::Idle,
        "a failed save is not retried on every render"
    );

    std::fs::remove_dir_all(directory).expect("remove owned test directory");
}

#[test]
fn applying_loaded_preferences_does_not_rewrite_the_source_file() {
    let directory = unique_test_directory("state-load-only");
    let path = directory.join("preferences.json");
    let preferences = UiPreferences {
        theme: Theme::Charcoal,
        display_mode: DisplayMode::Compact,
        ..UiPreferences::default()
    };
    save_preferences_to(&path, &preferences).expect("write valid preferences fixture");
    let original = std::fs::read(&path).expect("read fixture before state load");
    let mut state = AppState::controller();
    state.apply_loaded_preferences(load_preferences_from(&path));

    assert_eq!(
        persist_pending_preferences_to(&mut state, &path),
        PreferencePersistence::Idle
    );
    assert_eq!(
        std::fs::read(&path).expect("read fixture after state load"),
        original
    );

    std::fs::remove_dir_all(directory).expect("remove owned test directory");
}

fn json_document(screens: &str) -> String {
    format!(r#"{{"version":1,"theme":"warm-white","display_mode":"standard","screens":{screens}}}"#)
}

fn unique_test_directory(label: &str) -> PathBuf {
    let sequence = NEXT_TEST_DIRECTORY.fetch_add(1, Ordering::Relaxed);
    std::env::temp_dir().join(format!(
        "v20-ratatui-task9-{label}-{}-{sequence}",
        std::process::id()
    ))
}
