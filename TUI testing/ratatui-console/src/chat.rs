use std::collections::BTreeMap;

use sha2::{Digest, Sha256};

use crate::contract::{ChatEventPayload, ChatOperation, SafeId, WireChatRole};
use crate::controls::APPROVED_AGENT_ROLES;

const MAX_MESSAGE_BYTES: usize = 4 * 1024 * 1024;
/// Twelve controller pages keep a useful local window while durable history stays paged.
pub const MAX_VISIBLE_MESSAGES_PER_AGENT: usize = 240;
/// All eight chat threads share this cap so retained UTF-8 text stays within 4 MiB.
pub const MAX_RETAINED_CHAT_BYTES: usize = 4 * 1024 * 1024;
/// Fixed-size event fingerprints bound replay/conflict evidence retained by the client.
pub const MAX_REPLAY_EVENTS: usize = 8_192;

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct AgentId(&'static str);

impl AgentId {
    pub fn parse(value: &str) -> Option<Self> {
        APPROVED_AGENT_ROLES
            .iter()
            .copied()
            .find(|approved| *approved == value)
            .map(Self)
    }

    pub fn all() -> impl ExactSizeIterator<Item = Self> {
        APPROVED_AGENT_ROLES.into_iter().map(Self)
    }

    pub fn as_str(self) -> &'static str {
        self.0
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ChatRole {
    Human,
    Agent,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ChatMessageStatus {
    Draft,
    Complete,
    Interrupted,
}

#[derive(Clone, Debug, PartialEq, Eq)]
enum ChatEventKind {
    Chunk(String),
    Complete,
    Interrupted,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ChatEvent {
    event_id: String,
    agent_id: AgentId,
    message_id: String,
    role: ChatRole,
    message_created_at_utc: String,
    message_created_sort_key: String,
    kind: ChatEventKind,
    chunk_sequence: Option<u64>,
    validation_receipt_id: Option<String>,
    raw_text_sha256: Option<String>,
    fingerprint: [u8; 32],
}

impl TryFrom<ChatEventPayload> for ChatEvent {
    type Error = ChatApplyError;

    fn try_from(payload: ChatEventPayload) -> Result<Self, Self::Error> {
        let fingerprint = Sha256::digest(
            serde_json::to_vec(&payload).expect("strict chat payload always serializes"),
        )
        .into();
        let agent_id =
            AgentId::parse(payload.agent_id().as_str()).ok_or(ChatApplyError::UnapprovedAgent)?;
        let role = match payload.role() {
            WireChatRole::Human => ChatRole::Human,
            WireChatRole::Agent => ChatRole::Agent,
        };
        let kind = match payload.operation() {
            ChatOperation::Chunk => ChatEventKind::Chunk(
                payload
                    .text()
                    .expect("strict chunk payload has text")
                    .to_owned(),
            ),
            ChatOperation::Complete => ChatEventKind::Complete,
            ChatOperation::Interrupted => ChatEventKind::Interrupted,
        };
        let message_created_at_utc = payload.message_created_at_utc().as_str().to_owned();
        Ok(Self {
            event_id: payload.event_id().as_str().to_owned(),
            agent_id,
            message_id: payload.message_id().as_str().to_owned(),
            role,
            message_created_sort_key: utc_sort_key(&message_created_at_utc),
            message_created_at_utc,
            kind,
            chunk_sequence: payload.chunk_sequence(),
            validation_receipt_id: payload
                .validation_receipt_id()
                .map(|value| value.as_str().to_owned()),
            raw_text_sha256: payload
                .raw_text_sha256()
                .map(|value| value.as_str().to_owned()),
            fingerprint,
        })
    }
}

impl ChatEvent {
    pub fn agent_id(&self) -> AgentId {
        self.agent_id
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ChatMessage {
    message_id: String,
    role: ChatRole,
    content: String,
    status: ChatMessageStatus,
    message_created_at_utc: String,
    message_created_sort_key: String,
    next_chunk_sequence: u64,
    validation_receipt_id: Option<String>,
    raw_text_sha256: Option<String>,
}

impl ChatMessage {
    pub fn message_id(&self) -> &str {
        &self.message_id
    }

    pub fn role(&self) -> ChatRole {
        self.role
    }

    pub fn content(&self) -> &str {
        &self.content
    }

    pub fn status(&self) -> ChatMessageStatus {
        self.status
    }

    pub fn validation_receipt_id(&self) -> Option<&str> {
        self.validation_receipt_id.as_deref()
    }

    pub fn raw_text_sha256(&self) -> Option<&str> {
        self.raw_text_sha256.as_deref()
    }
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct ChatThread {
    messages: Vec<ChatMessage>,
}

impl ChatThread {
    pub fn messages(&self) -> &[ChatMessage] {
        &self.messages
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum ChatHistoryStatus {
    #[default]
    NotRequested,
    Loading,
    Available,
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
struct ChatHistoryState {
    status: ChatHistoryStatus,
    next_cursor: Option<SafeId>,
    insert_at: Option<usize>,
    merge_chronologically: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ChatApplyOutcome {
    Changed,
    Ignored,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ChatApplyError {
    UnapprovedAgent,
    ConflictingEvent,
    ConflictingMessage,
    InvalidChunkSequence,
    InvalidContentHash,
    MessageTooLarge,
    RetentionLimitExceeded,
    UnknownMessage,
    TerminalMessageImmutable,
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct ChatEventEvidence {
    agent_id: AgentId,
    message_id: String,
    fingerprint: [u8; 32],
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ChatStore {
    threads: BTreeMap<AgentId, ChatThread>,
    histories: BTreeMap<AgentId, ChatHistoryState>,
    event_evidence: BTreeMap<String, ChatEventEvidence>,
    retained_text_bytes: usize,
    agent_revisions: BTreeMap<AgentId, u64>,
}

impl Default for ChatStore {
    fn default() -> Self {
        Self {
            threads: AgentId::all()
                .map(|agent_id| (agent_id, ChatThread::default()))
                .collect(),
            histories: AgentId::all()
                .map(|agent_id| (agent_id, ChatHistoryState::default()))
                .collect(),
            event_evidence: BTreeMap::new(),
            retained_text_bytes: 0,
            agent_revisions: AgentId::all().map(|agent_id| (agent_id, 0)).collect(),
        }
    }
}

impl ChatStore {
    pub fn thread(&self, agent_id: AgentId) -> &ChatThread {
        self.threads
            .get(&agent_id)
            .expect("all approved agent threads are initialized")
    }

    pub fn history_status(&self, agent_id: AgentId) -> ChatHistoryStatus {
        self.histories
            .get(&agent_id)
            .expect("all approved agent histories are initialized")
            .status
    }

    pub fn next_cursor(&self, agent_id: AgentId) -> Option<&SafeId> {
        self.histories
            .get(&agent_id)
            .and_then(|history| history.next_cursor.as_ref())
    }

    pub fn mark_history_loading(&mut self, agent_id: AgentId, older_page: bool) {
        let history = self
            .histories
            .get_mut(&agent_id)
            .expect("all approved agent histories are initialized");
        history.status = ChatHistoryStatus::Loading;
        history.insert_at = older_page.then_some(0);
        history.merge_chronologically = !older_page;
    }

    pub fn finish_history(&mut self, agent_id: AgentId, next_cursor: Option<SafeId>) {
        let history = self
            .histories
            .get_mut(&agent_id)
            .expect("all approved agent histories are initialized");
        history.status = ChatHistoryStatus::Available;
        history.next_cursor = next_cursor;
        history.insert_at = None;
        history.merge_chronologically = false;
    }

    pub fn cancel_history_loads(&mut self) {
        for history in self.histories.values_mut() {
            if history.status == ChatHistoryStatus::Loading {
                history.status = ChatHistoryStatus::Available;
            }
            history.insert_at = None;
            history.merge_chronologically = false;
        }
    }

    pub fn event_evidence_len(&self) -> usize {
        self.event_evidence.len()
    }

    pub fn retained_text_bytes(&self) -> usize {
        self.retained_text_bytes
    }

    pub fn agent_revision(&self, agent_id: AgentId) -> u64 {
        *self
            .agent_revisions
            .get(&agent_id)
            .expect("all approved agent revisions are initialized")
    }

    pub fn can_request_older_page(&self, agent_id: AgentId) -> bool {
        self.thread(agent_id).messages.len().saturating_add(20) <= MAX_VISIBLE_MESSAGES_PER_AGENT
            && self.retained_text_bytes < MAX_RETAINED_CHAT_BYTES
            && self.event_evidence.len() < MAX_REPLAY_EVENTS
    }

    pub fn replay_outcome(
        &self,
        event: &ChatEvent,
    ) -> Result<Option<ChatApplyOutcome>, ChatApplyError> {
        let Some(previous) = self.event_evidence.get(&event.event_id) else {
            return Ok(None);
        };
        if previous.fingerprint == event.fingerprint {
            Ok(Some(ChatApplyOutcome::Ignored))
        } else {
            Err(ChatApplyError::ConflictingEvent)
        }
    }

    pub fn apply(&mut self, event: ChatEvent) -> Result<ChatApplyOutcome, ChatApplyError> {
        if let Some(outcome) = self.replay_outcome(&event)? {
            return Ok(outcome);
        }

        let existing = self
            .threads
            .get(&event.agent_id)
            .expect("ChatEvent carries a validated approved agent ID")
            .messages
            .iter()
            .position(|message| message.message_id == event.message_id);
        match &event.kind {
            ChatEventKind::Chunk(content) => match existing {
                Some(index) => {
                    {
                        let message = &self.thread(event.agent_id).messages[index];
                        if message.status != ChatMessageStatus::Draft {
                            return Err(ChatApplyError::TerminalMessageImmutable);
                        }
                        if message.role != event.role
                            || message.message_created_at_utc != event.message_created_at_utc
                        {
                            return Err(ChatApplyError::ConflictingMessage);
                        }
                        let sequence = event
                            .chunk_sequence
                            .expect("strict chunk payload has sequence");
                        if sequence != message.next_chunk_sequence {
                            return Err(ChatApplyError::InvalidChunkSequence);
                        }
                        if message.content.len().saturating_add(content.len()) > MAX_MESSAGE_BYTES {
                            return Err(ChatApplyError::MessageTooLarge);
                        }
                    }
                    self.ensure_capacity(event.agent_id, false, content.len())?;
                    let index = self
                        .thread(event.agent_id)
                        .messages
                        .iter()
                        .position(|message| message.message_id == event.message_id)
                        .expect("draft target is never retention-eligible");
                    let thread = self
                        .threads
                        .get_mut(&event.agent_id)
                        .expect("approved agent thread remains initialized");
                    let message = &mut thread.messages[index];
                    message.content.push_str(content);
                    self.retained_text_bytes =
                        self.retained_text_bytes.saturating_add(content.len());
                    message.next_chunk_sequence = message.next_chunk_sequence.saturating_add(1);
                }
                None => {
                    if self.threads.iter().any(|(agent_id, thread)| {
                        *agent_id != event.agent_id
                            && thread
                                .messages
                                .iter()
                                .any(|message| message.message_id == event.message_id)
                    }) {
                        return Err(ChatApplyError::ConflictingMessage);
                    }
                    if event.chunk_sequence != Some(1) {
                        return Err(ChatApplyError::InvalidChunkSequence);
                    }
                    if content.len() > MAX_MESSAGE_BYTES {
                        return Err(ChatApplyError::MessageTooLarge);
                    }
                    self.ensure_capacity(event.agent_id, true, content.len())?;
                    let message = ChatMessage {
                        message_id: event.message_id.clone(),
                        role: event.role,
                        content: content.clone(),
                        status: ChatMessageStatus::Draft,
                        message_created_at_utc: event.message_created_at_utc.clone(),
                        message_created_sort_key: event.message_created_sort_key.clone(),
                        next_chunk_sequence: 2,
                        validation_receipt_id: None,
                        raw_text_sha256: None,
                    };
                    let insert_at = self
                        .histories
                        .get(&event.agent_id)
                        .and_then(|history| history.insert_at);
                    let merge_chronologically = self
                        .histories
                        .get(&event.agent_id)
                        .is_some_and(|history| history.merge_chronologically);
                    if let Some(index) = insert_at {
                        let thread = self
                            .threads
                            .get_mut(&event.agent_id)
                            .expect("approved agent thread remains initialized");
                        let index = index.min(thread.messages.len());
                        thread.messages.insert(index, message);
                        self.histories
                            .get_mut(&event.agent_id)
                            .expect("all approved agent histories are initialized")
                            .insert_at = Some(index.saturating_add(1));
                    } else if merge_chronologically {
                        let thread = self
                            .threads
                            .get_mut(&event.agent_id)
                            .expect("approved agent thread remains initialized");
                        let index = thread.messages.partition_point(|existing| {
                            existing.message_created_sort_key.as_str()
                                <= message.message_created_sort_key.as_str()
                        });
                        thread.messages.insert(index, message);
                    } else {
                        self.threads
                            .get_mut(&event.agent_id)
                            .expect("approved agent thread remains initialized")
                            .messages
                            .push(message);
                    }
                    self.retained_text_bytes =
                        self.retained_text_bytes.saturating_add(content.len());
                }
            },
            ChatEventKind::Complete | ChatEventKind::Interrupted => {
                let Some(index) = existing else {
                    return Err(ChatApplyError::UnknownMessage);
                };
                {
                    let message = &self.thread(event.agent_id).messages[index];
                    if message.status != ChatMessageStatus::Draft {
                        return Err(ChatApplyError::TerminalMessageImmutable);
                    }
                    if message.role != event.role
                        || message.message_created_at_utc != event.message_created_at_utc
                    {
                        return Err(ChatApplyError::ConflictingMessage);
                    }
                    if matches!(event.kind, ChatEventKind::Complete) {
                        let expected = event
                            .raw_text_sha256
                            .as_deref()
                            .expect("strict complete payload has content hash");
                        let actual = format!("{:x}", Sha256::digest(message.content.as_bytes()));
                        if actual != expected {
                            return Err(ChatApplyError::InvalidContentHash);
                        }
                    }
                }
                self.ensure_capacity(event.agent_id, false, 0)?;
                let index = self
                    .thread(event.agent_id)
                    .messages
                    .iter()
                    .position(|message| message.message_id == event.message_id)
                    .expect("draft target is never retention-eligible");
                let thread = self
                    .threads
                    .get_mut(&event.agent_id)
                    .expect("approved agent thread remains initialized");
                let message = &mut thread.messages[index];
                message.status = match event.kind {
                    ChatEventKind::Complete => ChatMessageStatus::Complete,
                    ChatEventKind::Interrupted => ChatMessageStatus::Interrupted,
                    ChatEventKind::Chunk(_) => unreachable!("matched terminal event"),
                };
                if message.status == ChatMessageStatus::Complete {
                    message.validation_receipt_id = event.validation_receipt_id.clone();
                    message.raw_text_sha256 = event.raw_text_sha256.clone();
                }
            }
        }
        self.event_evidence.insert(
            event.event_id,
            ChatEventEvidence {
                agent_id: event.agent_id,
                message_id: event.message_id,
                fingerprint: event.fingerprint,
            },
        );
        self.bump_agent_revision(event.agent_id);
        Ok(ChatApplyOutcome::Changed)
    }

    fn ensure_capacity(
        &mut self,
        agent_id: AgentId,
        adds_message: bool,
        additional_text_bytes: usize,
    ) -> Result<(), ChatApplyError> {
        let mut projected_agent_messages =
            self.thread(agent_id).messages.len() + usize::from(adds_message);
        let mut projected_text_bytes = self
            .retained_text_bytes
            .saturating_add(additional_text_bytes);
        let mut projected_evidence = self.event_evidence.len().saturating_add(1);
        if projected_agent_messages <= MAX_VISIBLE_MESSAGES_PER_AGENT
            && projected_text_bytes <= MAX_RETAINED_CHAT_BYTES
            && projected_evidence <= MAX_REPLAY_EVENTS
        {
            return Ok(());
        }

        let mut evidence_counts = BTreeMap::<(AgentId, String), usize>::new();
        for evidence in self.event_evidence.values() {
            *evidence_counts
                .entry((evidence.agent_id, evidence.message_id.clone()))
                .or_default() += 1;
        }
        let mut candidates = self
            .threads
            .iter()
            .flat_map(|(candidate_agent, thread)| {
                thread.messages.iter().filter_map(|message| {
                    matches!(
                        message.status,
                        ChatMessageStatus::Complete | ChatMessageStatus::Interrupted
                    )
                    .then_some((
                        message.message_created_sort_key.clone(),
                        candidate_agent.as_str(),
                        *candidate_agent,
                        message.message_id.clone(),
                        message.content.len(),
                    ))
                })
            })
            .collect::<Vec<_>>();
        candidates.sort();

        let mut evictions = Vec::new();
        for (_, _, candidate_agent, message_id, content_bytes) in candidates {
            if candidate_agent == agent_id {
                projected_agent_messages = projected_agent_messages.saturating_sub(1);
            }
            projected_text_bytes = projected_text_bytes.saturating_sub(content_bytes);
            projected_evidence = projected_evidence.saturating_sub(
                evidence_counts
                    .get(&(candidate_agent, message_id.clone()))
                    .copied()
                    .unwrap_or_default(),
            );
            evictions.push((candidate_agent, message_id));
            if projected_agent_messages <= MAX_VISIBLE_MESSAGES_PER_AGENT
                && projected_text_bytes <= MAX_RETAINED_CHAT_BYTES
                && projected_evidence <= MAX_REPLAY_EVENTS
            {
                break;
            }
        }
        if projected_agent_messages > MAX_VISIBLE_MESSAGES_PER_AGENT
            || projected_text_bytes > MAX_RETAINED_CHAT_BYTES
            || projected_evidence > MAX_REPLAY_EVENTS
        {
            return Err(ChatApplyError::RetentionLimitExceeded);
        }
        if !evictions.is_empty()
            && self
                .histories
                .get(&agent_id)
                .is_some_and(|history| history.status == ChatHistoryStatus::Loading)
        {
            return Err(ChatApplyError::RetentionLimitExceeded);
        }
        for (candidate_agent, message_id) in evictions {
            self.remove_message_and_evidence(candidate_agent, &message_id);
        }
        Ok(())
    }

    fn remove_message_and_evidence(&mut self, agent_id: AgentId, message_id: &str) {
        let thread = self
            .threads
            .get_mut(&agent_id)
            .expect("approved agent thread remains initialized");
        let index = thread
            .messages
            .iter()
            .position(|message| message.message_id == message_id)
            .expect("retention candidate still exists");
        let removed = thread.messages.remove(index);
        self.retained_text_bytes = self
            .retained_text_bytes
            .saturating_sub(removed.content.len());
        self.event_evidence.retain(|_, evidence| {
            evidence.agent_id != agent_id || evidence.message_id != removed.message_id
        });
        self.bump_agent_revision(agent_id);
        let history = self
            .histories
            .get_mut(&agent_id)
            .expect("approved agent history remains initialized");
        if let Some(insert_at) = history.insert_at
            && index < insert_at
        {
            history.insert_at = Some(insert_at - 1);
        }
    }

    pub fn replace_agent_from(
        &mut self,
        candidate: &Self,
        agent_id: AgentId,
        expected_revision: u64,
    ) -> Result<(), ChatApplyError> {
        if self.agent_revision(agent_id) != expected_revision {
            return Err(ChatApplyError::ConflictingMessage);
        }
        let old_bytes = self
            .thread(agent_id)
            .messages
            .iter()
            .map(|message| message.content.len())
            .sum::<usize>();
        let new_thread = candidate.thread(agent_id).clone();
        let new_bytes = new_thread
            .messages
            .iter()
            .map(|message| message.content.len())
            .sum::<usize>();
        if self
            .retained_text_bytes
            .saturating_sub(old_bytes)
            .saturating_add(new_bytes)
            > MAX_RETAINED_CHAT_BYTES
        {
            return Err(ChatApplyError::RetentionLimitExceeded);
        }
        if new_thread.messages.iter().any(|message| {
            self.threads.iter().any(|(other_agent, thread)| {
                *other_agent != agent_id
                    && thread
                        .messages
                        .iter()
                        .any(|other| other.message_id == message.message_id)
            })
        }) {
            return Err(ChatApplyError::ConflictingMessage);
        }
        let candidate_evidence = candidate
            .event_evidence
            .iter()
            .filter(|(_, evidence)| evidence.agent_id == agent_id)
            .collect::<Vec<_>>();
        let other_evidence_count = self
            .event_evidence
            .values()
            .filter(|evidence| evidence.agent_id != agent_id)
            .count();
        if other_evidence_count.saturating_add(candidate_evidence.len()) > MAX_REPLAY_EVENTS {
            return Err(ChatApplyError::RetentionLimitExceeded);
        }
        if candidate_evidence.iter().any(|(event_id, _)| {
            self.event_evidence
                .get(*event_id)
                .is_some_and(|evidence| evidence.agent_id != agent_id)
        }) {
            return Err(ChatApplyError::ConflictingEvent);
        }
        self.threads.insert(agent_id, new_thread);
        self.histories.insert(
            agent_id,
            candidate
                .histories
                .get(&agent_id)
                .expect("approved agent history remains initialized")
                .clone(),
        );
        self.event_evidence
            .retain(|_, evidence| evidence.agent_id != agent_id);
        self.event_evidence.extend(
            candidate
                .event_evidence
                .iter()
                .filter(|(_, evidence)| evidence.agent_id == agent_id)
                .map(|(event_id, evidence)| (event_id.clone(), evidence.clone())),
        );
        self.retained_text_bytes = self
            .retained_text_bytes
            .saturating_sub(old_bytes)
            .saturating_add(new_bytes);
        self.bump_agent_revision(agent_id);
        Ok(())
    }

    fn bump_agent_revision(&mut self, agent_id: AgentId) {
        let revision = self
            .agent_revisions
            .get_mut(&agent_id)
            .expect("all approved agent revisions are initialized");
        *revision = revision.saturating_add(1);
    }
}

fn utc_sort_key(value: &str) -> String {
    if value.as_bytes().get(19) == Some(&b'.') {
        value.to_owned()
    } else {
        format!("{}.000000Z", &value[..19])
    }
}
