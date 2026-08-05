use std::collections::BTreeSet;

use ratatui::Terminal;
use ratatui::backend::Backend;
use ratatui::buffer::Buffer;

use crate::render_plan::{RenderPlan, ShellRegion};
use crate::state::AppState;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RenderKind {
    Full,
    Partial,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RenderReceipt {
    pub kind: RenderKind,
    pub regions: BTreeSet<ShellRegion>,
}

#[derive(Debug, Default)]
pub struct Renderer {
    committed: Option<Buffer>,
    recovery_required: bool,
}

impl Renderer {
    pub const fn new() -> Self {
        Self {
            committed: None,
            recovery_required: false,
        }
    }

    pub fn committed_buffer(&self) -> Option<&Buffer> {
        self.committed.as_ref()
    }

    pub const fn needs_recovery(&self) -> bool {
        self.recovery_required
    }

    pub fn invalidate(&mut self) {
        self.committed = None;
        self.recovery_required = true;
    }

    pub fn draw<B: Backend>(
        &mut self,
        terminal: &mut Terminal<B>,
        state: &AppState,
        requested: RenderPlan,
    ) -> Result<RenderReceipt, B::Error> {
        if let Err(error) = terminal.autoresize() {
            self.invalidate();
            return Err(error);
        }

        if self.recovery_required
            && let Err(error) = terminal.clear()
        {
            self.invalidate();
            return Err(error);
        }

        let area = {
            let frame = terminal.get_frame();
            frame.area()
        };
        let cache_matches = self
            .committed
            .as_ref()
            .is_some_and(|buffer| buffer.area == area);
        let (kind, regions) = match requested {
            RenderPlan::Partial(regions) if cache_matches && state.access.is_unlocked() => {
                (RenderKind::Partial, regions)
            }
            RenderPlan::Full | RenderPlan::Partial(_) => (RenderKind::Full, BTreeSet::new()),
        };

        match kind {
            RenderKind::Full => terminal.current_buffer_mut().reset(),
            RenderKind::Partial => {
                *terminal.current_buffer_mut() = self
                    .committed
                    .as_ref()
                    .expect("partial rendering requires a matching committed buffer")
                    .clone();
            }
        }

        {
            let mut frame = terminal.get_frame();
            match kind {
                RenderKind::Full => crate::ui::render(&mut frame, state),
                RenderKind::Partial => crate::ui::render_regions(&mut frame, state, &regions),
            }
        }
        let candidate = terminal.current_buffer_mut().clone();

        if let Err(error) = terminal.apply_buffer_with_cursor(None) {
            // Ratatui may already have swapped its buffers before Backend::flush reports failure.
            // Never trust either the terminal buffer pair or our candidate after any apply error.
            self.invalidate();
            return Err(error);
        }

        self.committed = Some(candidate);
        self.recovery_required = false;
        Ok(RenderReceipt { kind, regions })
    }
}
