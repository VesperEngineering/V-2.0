use std::time::Duration;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum InputEvent {
    Char(char),
    Enter,
    Escape,
    Backspace,
    Up,
    Down,
    PageUp,
    PageDown,
    Left,
    Right,
    OpenSearchResult(usize),
    OpenBrowseRow { panel: usize, index: usize },
    SelectChatAgent(usize),
    FocusChatInput,
    FocusBrowsePanel { panel: usize },
    ActivateControl(usize),
    ConfirmControl,
    CancelControl,
    TakeControl,
    LockTui,
    Reconnect,
    CloseTui,
    Tick(Duration),
}
