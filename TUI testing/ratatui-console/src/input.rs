use std::time::Duration;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum InputEvent {
    Char(char),
    Enter,
    Escape,
    Backspace,
    TakeControl,
    LockTui,
    Reconnect,
    CloseTui,
    Tick(Duration),
}
