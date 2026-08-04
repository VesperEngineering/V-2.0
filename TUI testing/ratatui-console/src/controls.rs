use crate::confirm::ConfirmationState;
use crate::contract::{
    CapabilityState, CapabilityView, CommandSpecView, CommandType, ConfirmationLevel,
    ConsoleSnapshot, Sha256Hex,
};
use crate::screens::DetailKind;
use crate::state::{AccessState, Screen};

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ButtonState {
    Enabled,
    Disabled { reason: String },
    Hidden,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ControlButton {
    pub label: String,
    pub command_type: CommandType,
    pub state: ButtonState,
    pub confirmation_level: Option<ConfirmationLevel>,
    pub reviewed_control_version: u64,
    pub reviewed_control_hash: Sha256Hex,
    pub context: Option<ControlContext>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ControlContext {
    Note {
        target_type: &'static str,
        target_id: String,
    },
    Approval {
        approval_id: String,
        run_id: String,
        checkpoint_id: String,
    },
    AgentWork {
        work_id: String,
    },
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ControlRelevance {
    Global,
    Selection(DetailKind),
    NoteTarget,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ControlDefinition {
    pub command_type: CommandType,
    pub label: &'static str,
    pub relevance: ControlRelevance,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LocalControl {
    TakeControl,
    LockTui,
    ToggleAccountPrivacy,
    OpenCandidateDetail,
}

pub fn local_controls(access: AccessState, screen: Screen) -> Vec<LocalControl> {
    let mut controls = Vec::with_capacity(3);
    if access == AccessState::Viewer {
        controls.push(LocalControl::TakeControl);
    }
    controls.push(LocalControl::LockTui);
    if screen == Screen::System {
        controls.push(LocalControl::ToggleAccountPrivacy);
    }
    if screen == Screen::ModelsRegime {
        controls.push(LocalControl::OpenCandidateDetail);
    }
    controls
}

const APPROVED_AGENT_ROLES: [&str; 8] = [
    "v20-product",
    "v20-development",
    "v20-risk-review",
    "v20-quant-research-lead",
    "v20-model-researcher",
    "v20-independent-quant-validator",
    "v20-portfolio-researcher",
    "v20-execution-performance-analyst",
];

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct AgentRouteDraft {
    selected_agent: &'static str,
    reason: &'static str,
}

#[derive(Clone, Debug, PartialEq)]
pub enum ControlMenuEntry {
    Command(ControlButton),
    Local {
        label: &'static str,
        control: LocalControl,
    },
}

#[derive(Clone, Debug, PartialEq)]
pub struct ControlMenu {
    entries: Vec<ControlMenuEntry>,
    selected: usize,
    reviewed_control_version: u64,
    reviewed_control_hash: Sha256Hex,
}

impl ControlMenu {
    pub fn entries(&self) -> &[ControlMenuEntry] {
        &self.entries
    }

    pub fn selected(&self) -> usize {
        self.selected
    }

    pub fn reviewed_control_pair(&self) -> (u64, &Sha256Hex) {
        (self.reviewed_control_version, &self.reviewed_control_hash)
    }

    pub fn select(&mut self, index: usize) {
        if index < self.entries.len() {
            self.selected = index;
        }
    }

    pub fn move_selection(&mut self, forward: bool) {
        if self.entries.is_empty() {
            return;
        }
        self.selected = if forward {
            (self.selected + 1).min(self.entries.len() - 1)
        } else {
            self.selected.saturating_sub(1)
        };
    }

    pub fn selected_entry(&self) -> Option<&ControlMenuEntry> {
        self.entries.get(self.selected)
    }

    pub fn command_index(&self, command_type: CommandType) -> Option<usize> {
        self.entries.iter().position(|entry| {
            matches!(entry, ControlMenuEntry::Command(button) if button.command_type == command_type)
        })
    }

    pub fn local_index(&self, control: LocalControl) -> Option<usize> {
        self.entries.iter().position(|entry| {
            matches!(entry, ControlMenuEntry::Local { control: value, .. } if *value == control)
        })
    }
}

#[derive(Clone, Debug, PartialEq)]
pub enum ControlOverlay {
    Menu(ControlMenu),
    Confirmation {
        label: String,
        state: Box<ConfirmationState>,
    },
    DisabledReason {
        label: String,
        reason: String,
    },
    ReasonForm(ReasonForm),
    AgentEnqueueForm(AgentEnqueueForm),
}

#[derive(Clone, Debug, PartialEq)]
pub struct ReasonForm {
    pub button: ControlButton,
    pub run_id: String,
    pub checkpoint_id: String,
    pub quick_reasons: [&'static str; 3],
    pub selected: usize,
    pub note: String,
}

impl ReasonForm {
    pub fn reason(&self) -> String {
        let quick = self.quick_reasons[self.selected];
        let note = self.note.trim();
        if note.is_empty() {
            quick.to_owned()
        } else {
            format!("{quick} - {note}")
        }
    }

    pub fn move_selection(&mut self, forward: bool) {
        self.selected = if forward {
            (self.selected + 1) % self.quick_reasons.len()
        } else {
            (self.selected + self.quick_reasons.len() - 1) % self.quick_reasons.len()
        };
    }

    pub fn push(&mut self, character: char) {
        if self.note.chars().count() < 2_000 {
            self.note.push(character);
        }
    }

    pub fn pop(&mut self) {
        self.note.pop();
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct AgentEnqueueForm {
    pub button: ControlButton,
    pub route: AgentRouteDraft,
    pub objective: String,
    pub priority: u8,
}

impl AgentEnqueueForm {
    pub fn title(&self) -> String {
        let first_line = self.objective.lines().next().unwrap_or_default().trim();
        first_line.chars().take(80).collect()
    }

    pub fn reason(&self) -> String {
        format!("Operator enqueue request: {}", self.title())
    }

    pub fn change_priority(&mut self, increase: bool) {
        self.priority = if increase {
            self.priority.saturating_add(5).min(100)
        } else {
            self.priority.saturating_sub(5)
        };
    }

    pub fn push(&mut self, character: char) {
        if self.objective.chars().count() < 8_000 {
            self.objective.push(character);
        }
    }

    pub fn pop(&mut self) {
        self.objective.pop();
    }
}

pub fn build_control_menu(
    snapshot: &ConsoleSnapshot,
    access: AccessState,
    screen: Screen,
    selected_kind: Option<DetailKind>,
    selected_id: Option<&str>,
) -> ControlMenu {
    let mut entries = control_definitions_for_screen(screen)
        .filter_map(|definition| {
            let relevant = match definition.relevance {
                ControlRelevance::Global => true,
                ControlRelevance::Selection(kind) => selected_kind == Some(kind),
                ControlRelevance::NoteTarget => selected_kind.is_some_and(note_target_kind),
            };
            let mut button = server_button(
                snapshot,
                definition.command_type,
                definition.label,
                relevant,
            );
            button.context = control_context(
                snapshot,
                definition.command_type,
                selected_kind,
                selected_id,
            );
            if definition.command_type == CommandType::AgentStop
                && button.state == ButtonState::Enabled
            {
                button.state = ButtonState::Disabled {
                    reason: "Workflow run ID is unavailable for the selected work item.".to_owned(),
                };
            }
            if button.state == ButtonState::Hidden {
                return None;
            }
            if access == AccessState::Viewer && button.state == ButtonState::Enabled {
                button.state = ButtonState::Disabled {
                    reason: "Take Control is required.".to_owned(),
                };
            }
            Some(ControlMenuEntry::Command(button))
        })
        .collect::<Vec<_>>();
    entries.extend(
        local_controls(access, screen)
            .into_iter()
            .filter_map(|control| {
                if control == LocalControl::OpenCandidateDetail
                    && selected_kind != Some(DetailKind::ModelCandidate)
                {
                    return None;
                }
                Some(ControlMenuEntry::Local {
                    label: local_control_label(control),
                    control,
                })
            }),
    );
    ControlMenu {
        entries,
        selected: 0,
        reviewed_control_version: snapshot.control_version,
        reviewed_control_hash: snapshot.control_hash.clone(),
    }
}

fn control_context(
    snapshot: &ConsoleSnapshot,
    command_type: CommandType,
    selected_kind: Option<DetailKind>,
    selected_id: Option<&str>,
) -> Option<ControlContext> {
    let selected_id = selected_id?;
    if command_type == CommandType::NoteAdd {
        let target_type = match selected_kind? {
            DetailKind::Stock => "stock",
            DetailKind::Order => "order",
            DetailKind::Approval => "approval",
            DetailKind::Event => "agent-event",
            _ => return None,
        };
        return Some(ControlContext::Note {
            target_type,
            target_id: selected_id.to_owned(),
        });
    }
    if matches!(
        command_type,
        CommandType::ApprovalApprove
            | CommandType::ApprovalHold
            | CommandType::ApprovalReject
            | CommandType::ApprovalRework
    ) {
        let row = snapshot
            .risk
            .approvals
            .iter()
            .find(|row| row.approval_id.as_str() == selected_id)?;
        return Some(ControlContext::Approval {
            approval_id: row.approval_id.as_str().to_owned(),
            run_id: row.run_id.as_str().to_owned(),
            checkpoint_id: row.checkpoint_id.as_str().to_owned(),
        });
    }
    if matches!(
        command_type,
        CommandType::AgentPause
            | CommandType::AgentStop
            | CommandType::AgentRetry
            | CommandType::AgentSetPriority
    ) && selected_kind == Some(DetailKind::Agent)
    {
        return Some(ControlContext::AgentWork {
            work_id: selected_id.to_owned(),
        });
    }
    None
}

fn note_target_kind(kind: DetailKind) -> bool {
    matches!(
        kind,
        DetailKind::Stock | DetailKind::Order | DetailKind::Approval | DetailKind::Event
    )
}

fn local_control_label(control: LocalControl) -> &'static str {
    match control {
        LocalControl::TakeControl => "Take Control",
        LocalControl::LockTui => "Lock TUI",
        LocalControl::ToggleAccountPrivacy => "Account Privacy",
        LocalControl::OpenCandidateDetail => "Candidate Detail",
    }
}

impl AgentRouteDraft {
    pub fn for_screen(screen: Screen) -> Self {
        let (selected_agent, reason) = match screen {
            Screen::Impact => ("v20-product", "Impact context routes to Product."),
            Screen::Portfolio => (
                "v20-portfolio-researcher",
                "Portfolio context routes to Portfolio Research.",
            ),
            Screen::Orders => (
                "v20-product",
                "Orders context routes to Product unless an audited correction is selected.",
            ),
            Screen::Agents => ("v20-product", "Agent coordination routes to Product."),
            Screen::ModelsRegime => (
                "v20-model-researcher",
                "Model and regime context routes to Model Research.",
            ),
            Screen::Timeline => ("v20-product", "Timeline context routes to Product."),
            Screen::RiskApprovals => (
                "v20-risk-review",
                "Risk and approval context routes to Risk Review.",
            ),
            Screen::DataEvidence => (
                "v20-quant-research-lead",
                "Data and evidence context routes to Quant Research.",
            ),
            Screen::Memory => ("v20-product", "Memory context routes to Product."),
            Screen::System => ("v20-development", "System context routes to Development."),
        };
        Self {
            selected_agent,
            reason,
        }
    }

    pub fn selected_agent(&self) -> &str {
        self.selected_agent
    }

    pub fn reason(&self) -> &str {
        self.reason
    }

    pub fn override_agent(&mut self, agent: &str) -> Result<(), &'static str> {
        let selected = APPROVED_AGENT_ROLES
            .iter()
            .copied()
            .find(|approved| *approved == agent)
            .ok_or("agent role is not approved")?;
        self.selected_agent = selected;
        self.reason = "Operator override selected before send.";
        Ok(())
    }

    pub fn cycle_override(&mut self, forward: bool) {
        let current = APPROVED_AGENT_ROLES
            .iter()
            .position(|agent| *agent == self.selected_agent)
            .unwrap_or(0);
        let next = if forward {
            (current + 1) % APPROVED_AGENT_ROLES.len()
        } else {
            (current + APPROVED_AGENT_ROLES.len() - 1) % APPROVED_AGENT_ROLES.len()
        };
        self.selected_agent = APPROVED_AGENT_ROLES[next];
        self.reason = "Operator override selected before send.";
    }
}

pub fn button_state(
    spec: &CommandSpecView,
    capability: &CapabilityView,
    relevant: bool,
) -> ButtonState {
    if !relevant {
        return ButtonState::Hidden;
    }
    if capability.capability_id.as_str() != spec.capability_id.as_str() {
        return ButtonState::Disabled {
            reason: "Server capability does not match this control.".to_owned(),
        };
    }
    match capability.state {
        CapabilityState::Enabled => ButtonState::Enabled,
        CapabilityState::ReadOnly => ButtonState::Disabled {
            reason: capability.reason.as_ref().map_or_else(
                || "Take Control is required.".to_owned(),
                |reason| reason.as_str().to_owned(),
            ),
        },
        CapabilityState::Disabled => ButtonState::Disabled {
            reason: capability.reason.as_ref().map_or_else(
                || "Server did not provide a disabled reason.".to_owned(),
                |reason| reason.as_str().to_owned(),
            ),
        },
    }
}

pub fn server_button(
    snapshot: &ConsoleSnapshot,
    command_type: CommandType,
    label: impl Into<String>,
    relevant: bool,
) -> ControlButton {
    let label = label.into();
    let specs = snapshot
        .command_specs
        .iter()
        .filter(|spec| spec.command_type.as_str() == command_type.as_str())
        .collect::<Vec<_>>();
    let Some(spec) = specs.first().copied().filter(|_| specs.len() == 1) else {
        return ControlButton {
            label,
            command_type,
            state: ButtonState::Disabled {
                reason: "Server did not publish one exact command spec.".to_owned(),
            },
            confirmation_level: None,
            reviewed_control_version: snapshot.control_version,
            reviewed_control_hash: snapshot.control_hash.clone(),
            context: None,
        };
    };
    let capabilities = snapshot
        .shell
        .capabilities
        .iter()
        .filter(|capability| capability.capability_id.as_str() == spec.capability_id.as_str())
        .collect::<Vec<_>>();
    let state = capabilities
        .first()
        .copied()
        .filter(|_| capabilities.len() == 1)
        .map_or_else(
            || ButtonState::Disabled {
                reason: "Server did not publish one exact capability state.".to_owned(),
            },
            |capability| button_state(spec, capability, relevant),
        );
    ControlButton {
        label,
        command_type,
        state,
        confirmation_level: Some(spec.confirmation_level),
        reviewed_control_version: snapshot.control_version,
        reviewed_control_hash: snapshot.control_hash.clone(),
        context: None,
    }
}

pub fn control_definitions_for_screen(screen: Screen) -> impl Iterator<Item = ControlDefinition> {
    let definitions = match screen {
        Screen::Impact => vec![
            definition(
                CommandType::NoteAdd,
                "Add Note",
                ControlRelevance::NoteTarget,
            ),
            definition(
                CommandType::AlertDismiss,
                "Dismiss Alert",
                ControlRelevance::Global,
            ),
            definition(
                CommandType::LayoutReset,
                "Reset Layout",
                ControlRelevance::Global,
            ),
        ],
        Screen::Portfolio | Screen::Orders | Screen::Timeline => vec![definition(
            CommandType::NoteAdd,
            "Add Note",
            ControlRelevance::NoteTarget,
        )],
        Screen::DataEvidence => vec![],
        Screen::Agents => vec![
            definition(
                CommandType::AgentSendMessage,
                "Send",
                ControlRelevance::Global,
            ),
            definition(
                CommandType::AgentEnqueue,
                "Enqueue",
                ControlRelevance::Global,
            ),
            definition(
                CommandType::AgentPause,
                "Pause",
                ControlRelevance::Selection(DetailKind::Agent),
            ),
            definition(
                CommandType::AgentStop,
                "Stop",
                ControlRelevance::Selection(DetailKind::Agent),
            ),
            definition(
                CommandType::AgentRetry,
                "Retry",
                ControlRelevance::Selection(DetailKind::Agent),
            ),
            definition(
                CommandType::AgentSetPriority,
                "Priority",
                ControlRelevance::Selection(DetailKind::Agent),
            ),
        ],
        Screen::ModelsRegime => vec![
            definition(
                CommandType::ModelRequestPromotion,
                "Request Approval",
                ControlRelevance::Selection(DetailKind::ModelCandidate),
            ),
            definition(
                CommandType::ModelRequestRollback,
                "Request Rollback",
                ControlRelevance::Selection(DetailKind::ModelCandidate),
            ),
        ],
        Screen::RiskApprovals => vec![
            definition(
                CommandType::NoteAdd,
                "Add Note",
                ControlRelevance::NoteTarget,
            ),
            definition(
                CommandType::RiskProposeLimit,
                "Edit Proposed Limit",
                ControlRelevance::Selection(DetailKind::RiskLimit),
            ),
            definition(
                CommandType::TradingPause,
                "Pause Trading",
                ControlRelevance::Global,
            ),
            definition(
                CommandType::TradingEmergencyStop,
                "Emergency Stop",
                ControlRelevance::Global,
            ),
            definition(
                CommandType::ApprovalApprove,
                "Approve",
                ControlRelevance::Selection(DetailKind::Approval),
            ),
            definition(
                CommandType::ApprovalHold,
                "Hold",
                ControlRelevance::Selection(DetailKind::Approval),
            ),
            definition(
                CommandType::ApprovalReject,
                "Reject",
                ControlRelevance::Selection(DetailKind::Approval),
            ),
            definition(
                CommandType::ApprovalRework,
                "Rework",
                ControlRelevance::Selection(DetailKind::Approval),
            ),
        ],
        Screen::Memory => vec![definition(
            CommandType::MemoryCompressNow,
            "Compress Now",
            ControlRelevance::Global,
        )],
        Screen::System => vec![
            definition(
                CommandType::ServicePause,
                "Pause Service",
                ControlRelevance::Selection(DetailKind::Service),
            ),
            definition(
                CommandType::ServiceRestart,
                "Restart Service",
                ControlRelevance::Selection(DetailKind::Service),
            ),
            definition(
                CommandType::RuntimeStart,
                "Start V20",
                ControlRelevance::Global,
            ),
            definition(
                CommandType::RuntimeStopSafe,
                "Stop Safely",
                ControlRelevance::Global,
            ),
            definition(
                CommandType::RuntimeStopForce,
                "Force Stop",
                ControlRelevance::Global,
            ),
            definition(
                CommandType::RuntimePrepareShutdown,
                "Prepare PC Shutdown",
                ControlRelevance::Global,
            ),
            definition(
                CommandType::ModeSwitch,
                "Switch Mode",
                ControlRelevance::Global,
            ),
            definition(
                CommandType::ModeLeaveLive,
                "Leave Live",
                ControlRelevance::Global,
            ),
            definition(
                CommandType::ModeEnableLive,
                "Enable Live",
                ControlRelevance::Global,
            ),
            definition(
                CommandType::BackupCreate,
                "Backup Now",
                ControlRelevance::Global,
            ),
            definition(
                CommandType::BackupRestore,
                "Restore",
                ControlRelevance::Global,
            ),
            definition(
                CommandType::SourceControlPush,
                "Push",
                ControlRelevance::Global,
            ),
        ],
    };
    definitions.into_iter()
}

const fn definition(
    command_type: CommandType,
    label: &'static str,
    relevance: ControlRelevance,
) -> ControlDefinition {
    ControlDefinition {
        command_type,
        label,
        relevance,
    }
}
