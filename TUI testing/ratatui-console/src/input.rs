use std::time::Duration;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum InputEvent {
    Char(char),
    Enter,
    Escape,
    Backspace,
    Up,
    Down,
    Left,
    Right,
    OpenSearchResult(usize),
    OpenBrowseRow { panel: usize, index: usize },
    FocusBrowsePanel { panel: usize },
    TakeControl,
    LockTui,
    Reconnect,
    CloseTui,
    Tick(Duration),
}
