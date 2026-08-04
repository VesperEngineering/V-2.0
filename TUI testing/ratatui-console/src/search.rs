use std::collections::BTreeSet;
use std::error::Error;
use std::fmt;
use std::time::{Duration, Instant};

use crate::contract::{
    AgentCard, AssetType, CandidateRow, ConsoleSnapshot, EvidenceRow, MemoryRow, ModelOpinionRow,
    NonEmptyString, OrderRow, PortfolioRow, RepositoryRow, SearchFiltersPayload, SearchLimit,
    SearchQuery, SearchRequestId, SearchRequestPayload, SearchResultPayload, SourceRow,
    TimelineRow, WireSearchKind, WireSearchRecordType, WireSearchScreen,
};
use crate::screens::DetailKind;
use crate::state::Screen;
use crate::widgets::sanitize_line;

pub const MAX_SEARCH_QUERY_CHARS: usize = 256;
pub const MAX_SEARCH_RESULTS: usize = 100;
pub const SEARCH_DEBOUNCE: Duration = Duration::from_millis(100);
const MAX_SEARCH_FILTER_CHARS: usize = 512;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SearchKind {
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

impl SearchKind {
    fn order(self) -> u8 {
        match self {
            Self::Stock => 0,
            Self::Agent => 1,
            Self::Model => 2,
            Self::Order => 3,
            Self::Approval => 4,
            Self::Event => 5,
            Self::Evidence => 6,
            Self::Memory => 7,
            Self::Source => 8,
            Self::Note => 9,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Stock => "stock",
            Self::Agent => "agent",
            Self::Model => "model",
            Self::Order => "order",
            Self::Approval => "approval",
            Self::Event => "event",
            Self::Evidence => "evidence",
            Self::Memory => "memory",
            Self::Source => "source",
            Self::Note => "note",
        }
    }

    fn from_filter(value: &str) -> Option<Self> {
        match value.to_ascii_lowercase().as_str() {
            "stock" => Some(Self::Stock),
            "agent" => Some(Self::Agent),
            "model" => Some(Self::Model),
            "order" => Some(Self::Order),
            "approval" => Some(Self::Approval),
            "event" => Some(Self::Event),
            "evidence" => Some(Self::Evidence),
            "memory" => Some(Self::Memory),
            "source" => Some(Self::Source),
            "note" => Some(Self::Note),
            _ => None,
        }
    }
}

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct SearchFilters {
    pub screen: Option<Screen>,
    pub kinds: Vec<SearchKind>,
    pub source: Option<String>,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum NoteVisibility {
    #[default]
    Private,
    Shared,
}

impl NoteVisibility {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Private => "Private",
            Self::Shared => "Shared",
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ContextNoteDraft {
    pub target_type: &'static str,
    pub target_id: String,
    pub body: String,
    pub visibility: NoteVisibility,
    pub context_only: bool,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SearchFilterError(String);

impl SearchFilterError {
    pub fn message(&self) -> &str {
        &self.0
    }
}

impl fmt::Display for SearchFilterError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.0)
    }
}

impl Error for SearchFilterError {}

fn filter_tokens(expression: &str) -> Result<Vec<String>, SearchFilterError> {
    if expression.chars().count() > MAX_SEARCH_FILTER_CHARS {
        return Err(SearchFilterError("Filter is too long.".to_owned()));
    }

    let mut tokens = Vec::new();
    let mut current = String::new();
    let mut quoted = false;
    let mut escaped = false;
    for character in expression.chars() {
        if quoted {
            if escaped {
                match character {
                    '\\' | '"' => current.push(character),
                    _ => {
                        return Err(SearchFilterError("Invalid escape in filter.".to_owned()));
                    }
                }
                escaped = false;
            } else {
                match character {
                    '\\' => escaped = true,
                    '"' => quoted = false,
                    _ => current.push(character),
                }
            }
        } else {
            match character {
                '"' => quoted = true,
                value if value.is_whitespace() => {
                    if !current.is_empty() {
                        tokens.push(std::mem::take(&mut current));
                    }
                }
                _ => current.push(character),
            }
        }
    }
    if escaped {
        return Err(SearchFilterError("Invalid escape in filter.".to_owned()));
    }
    if quoted {
        return Err(SearchFilterError("Unclosed quote in filter.".to_owned()));
    }
    if !current.is_empty() {
        tokens.push(current);
    }
    Ok(tokens)
}

fn format_filter_value(value: &str) -> String {
    if !value
        .chars()
        .any(|character| character.is_whitespace() || matches!(character, '"' | '\\'))
    {
        return value.to_owned();
    }

    let mut quoted = String::with_capacity(value.len().saturating_add(2));
    quoted.push('"');
    for character in value.chars() {
        if matches!(character, '"' | '\\') {
            quoted.push('\\');
        }
        quoted.push(character);
    }
    quoted.push('"');
    quoted
}

pub fn parse_filter_expression(
    current_screen: Screen,
    expression: &str,
) -> Result<SearchFilters, SearchFilterError> {
    let mut filters = SearchFilters::default();
    let mut saw_scope = false;
    let mut saw_kind = false;
    let mut saw_source = false;
    for token in filter_tokens(expression)? {
        let Some((name, raw_value)) = token.split_once(':') else {
            return Err(SearchFilterError(format!(
                "Invalid filter: {token}. Use name:value."
            )));
        };
        if raw_value.is_empty() {
            return Err(SearchFilterError(format!("Missing value for {name}.")));
        }
        match name.to_ascii_lowercase().as_str() {
            "scope" if !saw_scope => {
                saw_scope = true;
                filters.screen = match raw_value.to_ascii_lowercase().as_str() {
                    "all" => None,
                    "screen" => Some(current_screen),
                    _ => {
                        return Err(SearchFilterError(format!("Unknown scope: {raw_value}")));
                    }
                };
            }
            "kind" if !saw_kind => {
                saw_kind = true;
                for value in raw_value.split(',') {
                    let Some(kind) = SearchKind::from_filter(value) else {
                        return Err(SearchFilterError(format!("Unknown kind: {value}")));
                    };
                    if !filters.kinds.contains(&kind) {
                        filters.kinds.push(kind);
                    }
                }
            }
            "source" if !saw_source => {
                saw_source = true;
                if raw_value.contains(',') {
                    return Err(SearchFilterError(
                        "Use one source filter at a time.".to_owned(),
                    ));
                }
                let value = sanitize_line(raw_value);
                if value.is_empty() {
                    return Err(SearchFilterError("Missing source value.".to_owned()));
                }
                filters.source = Some(value);
            }
            "scope" | "kind" | "source" => {
                return Err(SearchFilterError(format!(
                    "Duplicate filter: {}",
                    name.to_ascii_lowercase()
                )));
            }
            _ => return Err(SearchFilterError(format!("Unknown filter: {name}"))),
        }
    }
    if !saw_scope {
        filters.screen = Some(current_screen);
    }
    Ok(filters)
}

pub fn format_filter_expression(filters: &SearchFilters) -> String {
    let mut tokens = vec![if filters.screen.is_some() {
        "scope:screen".to_owned()
    } else {
        "scope:all".to_owned()
    }];
    if !filters.kinds.is_empty() {
        tokens.push(format!(
            "kind:{}",
            filters
                .kinds
                .iter()
                .map(|kind| kind.as_str())
                .collect::<Vec<_>>()
                .join(",")
        ));
    }
    if let Some(source) = &filters.source {
        tokens.push(format!("source:{}", format_filter_value(source)));
    }
    tokens.join(" ")
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct NavigationTarget {
    pub screen: Screen,
    pub kind: SearchKind,
    pub detail_kind: DetailKind,
    pub entity_id: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SearchResult {
    pub kind: SearchKind,
    pub entity_id: String,
    pub title: String,
    pub text: String,
    pub timestamp_utc: Option<String>,
    pub source: String,
    pub context_only: bool,
    pub target: NavigationTarget,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SearchRequest {
    pub request_id: u64,
    pub query: String,
    pub filters: SearchFilters,
}

impl SearchRequest {
    pub fn to_wire(&self) -> Result<SearchRequestPayload, SearchWireError> {
        if self.filters.kinds.len() > 10 {
            return Err(SearchWireError::TooManyKinds);
        }
        let source = self
            .filters
            .source
            .as_ref()
            .cloned()
            .map(NonEmptyString::from_input)
            .transpose()
            .map_err(|_| SearchWireError::InvalidSource)?;
        Ok(SearchRequestPayload {
            request_id: SearchRequestId::from_sequence(self.request_id)
                .map_err(|_| SearchWireError::InvalidRequestId)?,
            query: SearchQuery::from_input(self.query.clone())
                .map_err(|_| SearchWireError::InvalidQuery)?,
            filters: SearchFiltersPayload {
                kinds: self
                    .filters
                    .kinds
                    .iter()
                    .copied()
                    .map(WireSearchKind::from)
                    .collect(),
                screens: self.filters.screen.map_or_else(Vec::new, wire_screens),
                source,
            },
            limit: SearchLimit::maximum(),
        })
    }
}

impl TryFrom<SearchResultPayload> for SearchResult {
    type Error = SearchWireError;

    fn try_from(value: SearchResultPayload) -> Result<Self, Self::Error> {
        let (expected_kind, detail_kind, expected_screen) = route_for(value.record_type);
        if value.kind != expected_kind {
            return Err(SearchWireError::IncompatibleRoute);
        }
        let screen = screen_from_wire(value.screen);
        if !screen_matches(value.record_type, screen, expected_screen) {
            return Err(SearchWireError::IncompatibleRoute);
        }
        let context_only = value.context_only.unwrap_or(false);
        if (value.record_type == WireSearchRecordType::Note) != context_only {
            return Err(SearchWireError::InvalidContextFlag);
        }
        let kind = SearchKind::from(value.kind);
        let entity_id = value.record_id.as_str().to_owned();
        Ok(Self {
            kind,
            entity_id: entity_id.clone(),
            title: value.label.as_str().to_owned(),
            text: value.summary.as_str().to_owned(),
            timestamp_utc: value
                .occurred_at_utc
                .as_ref()
                .map(|timestamp| timestamp.as_str().to_owned()),
            source: value.source.as_str().to_owned(),
            context_only,
            target: NavigationTarget {
                screen,
                kind,
                detail_kind,
                entity_id,
            },
        })
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SearchWireError {
    InvalidRequestId,
    InvalidQuery,
    InvalidSource,
    TooManyKinds,
    IncompatibleRoute,
    InvalidContextFlag,
}

impl fmt::Display for SearchWireError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        let message = match self {
            Self::InvalidRequestId => "search request ID is invalid",
            Self::InvalidQuery => "search query is invalid",
            Self::InvalidSource => "search source is invalid",
            Self::TooManyKinds => "search kind filter is too large",
            Self::IncompatibleRoute => "search result route is incompatible",
            Self::InvalidContextFlag => "search result context flag is invalid",
        };
        formatter.write_str(message)
    }
}

impl Error for SearchWireError {}

impl From<SearchKind> for WireSearchKind {
    fn from(value: SearchKind) -> Self {
        match value {
            SearchKind::Stock => Self::Stock,
            SearchKind::Agent => Self::Agent,
            SearchKind::Model => Self::Model,
            SearchKind::Order => Self::Order,
            SearchKind::Approval => Self::Approval,
            SearchKind::Event => Self::Event,
            SearchKind::Evidence => Self::Evidence,
            SearchKind::Memory => Self::Memory,
            SearchKind::Source => Self::Source,
            SearchKind::Note => Self::Note,
        }
    }
}

impl From<WireSearchKind> for SearchKind {
    fn from(value: WireSearchKind) -> Self {
        match value {
            WireSearchKind::Stock => Self::Stock,
            WireSearchKind::Agent => Self::Agent,
            WireSearchKind::Model => Self::Model,
            WireSearchKind::Order => Self::Order,
            WireSearchKind::Approval => Self::Approval,
            WireSearchKind::Event => Self::Event,
            WireSearchKind::Evidence => Self::Evidence,
            WireSearchKind::Memory => Self::Memory,
            WireSearchKind::Source => Self::Source,
            WireSearchKind::Note => Self::Note,
        }
    }
}

fn wire_screens(screen: Screen) -> Vec<WireSearchScreen> {
    match screen {
        Screen::Impact => vec![
            WireSearchScreen::Portfolio,
            WireSearchScreen::Agents,
            WireSearchScreen::Timeline,
        ],
        Screen::Portfolio => vec![WireSearchScreen::Portfolio],
        Screen::Orders => vec![WireSearchScreen::Orders],
        Screen::Agents => vec![WireSearchScreen::Agents],
        Screen::ModelsRegime => vec![WireSearchScreen::ModelsRegime],
        Screen::Timeline => vec![WireSearchScreen::Timeline],
        Screen::RiskApprovals => vec![WireSearchScreen::RiskApprovals],
        Screen::DataEvidence => vec![WireSearchScreen::DataEvidence],
        Screen::Memory => vec![WireSearchScreen::Memory],
        Screen::System => vec![WireSearchScreen::System],
    }
}

fn screen_from_wire(screen: WireSearchScreen) -> Screen {
    match screen {
        WireSearchScreen::Portfolio => Screen::Portfolio,
        WireSearchScreen::Agents => Screen::Agents,
        WireSearchScreen::ModelsRegime => Screen::ModelsRegime,
        WireSearchScreen::Orders => Screen::Orders,
        WireSearchScreen::RiskApprovals => Screen::RiskApprovals,
        WireSearchScreen::Timeline => Screen::Timeline,
        WireSearchScreen::DataEvidence => Screen::DataEvidence,
        WireSearchScreen::Memory => Screen::Memory,
        WireSearchScreen::System => Screen::System,
    }
}

fn route_for(record_type: WireSearchRecordType) -> (WireSearchKind, DetailKind, Screen) {
    match record_type {
        WireSearchRecordType::PortfolioRow => {
            (WireSearchKind::Stock, DetailKind::Stock, Screen::Portfolio)
        }
        WireSearchRecordType::AgentCard => {
            (WireSearchKind::Agent, DetailKind::Agent, Screen::Agents)
        }
        WireSearchRecordType::ModelOpinionRow => (
            WireSearchKind::Model,
            DetailKind::ModelOpinion,
            Screen::ModelsRegime,
        ),
        WireSearchRecordType::CandidateRow => (
            WireSearchKind::Model,
            DetailKind::ModelCandidate,
            Screen::ModelsRegime,
        ),
        WireSearchRecordType::OrderRow => {
            (WireSearchKind::Order, DetailKind::Order, Screen::Orders)
        }
        WireSearchRecordType::ApprovalRow => (
            WireSearchKind::Approval,
            DetailKind::Approval,
            Screen::RiskApprovals,
        ),
        WireSearchRecordType::TimelineRow => {
            (WireSearchKind::Event, DetailKind::Event, Screen::Timeline)
        }
        WireSearchRecordType::EvidenceRow => (
            WireSearchKind::Evidence,
            DetailKind::Evidence,
            Screen::DataEvidence,
        ),
        WireSearchRecordType::MemoryRow => {
            (WireSearchKind::Memory, DetailKind::Memory, Screen::Memory)
        }
        WireSearchRecordType::SourceRow => (
            WireSearchKind::Source,
            DetailKind::Source,
            Screen::DataEvidence,
        ),
        WireSearchRecordType::RepositoryRow => (
            WireSearchKind::Source,
            DetailKind::Repository,
            Screen::System,
        ),
        WireSearchRecordType::Note => (WireSearchKind::Note, DetailKind::Note, Screen::Portfolio),
    }
}

fn screen_matches(record_type: WireSearchRecordType, actual: Screen, expected: Screen) -> bool {
    if record_type == WireSearchRecordType::Note {
        matches!(
            actual,
            Screen::Portfolio | Screen::Orders | Screen::RiskApprovals | Screen::Timeline
        )
    } else {
        actual == expected
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum SearchStatus {
    #[default]
    Idle,
    Debouncing,
    Loading,
    Fresh,
    Incomplete,
    Unavailable,
    StaleRefreshing,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SearchResponseDisposition {
    Unknown,
    Superseded,
    Current,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SearchState {
    active_screen: Screen,
    query: String,
    query_error: Option<SearchError>,
    filters_by_screen: Vec<(Screen, SearchFilters)>,
    default_filters: SearchFilters,
    next_request_id: u64,
    latest_request_id: Option<u64>,
    last_issued_request_id: Option<u64>,
    completed_through_request_id: u64,
    pending: Option<(u64, Instant)>,
    rows: Vec<SearchResult>,
    selected_index: usize,
    server_error: Option<String>,
    status: SearchStatus,
}

impl Default for SearchState {
    fn default() -> Self {
        Self {
            active_screen: Screen::Impact,
            query: String::new(),
            query_error: None,
            filters_by_screen: Vec::new(),
            default_filters: SearchFilters::default(),
            next_request_id: 0,
            latest_request_id: None,
            last_issued_request_id: None,
            completed_through_request_id: 0,
            pending: None,
            rows: Vec::new(),
            selected_index: 0,
            server_error: None,
            status: SearchStatus::Idle,
        }
    }
}

impl SearchState {
    pub fn set_active_screen(&mut self, screen: Screen) {
        self.active_screen = screen;
    }

    pub fn set_filters(&mut self, screen: Screen, filters: SearchFilters) {
        if let Some((_, current)) = self
            .filters_by_screen
            .iter_mut()
            .find(|(candidate, _)| *candidate == screen)
        {
            *current = filters;
        } else {
            self.filters_by_screen.push((screen, filters));
        }
    }

    pub fn filters(&self, screen: Screen) -> &SearchFilters {
        self.filters_by_screen
            .iter()
            .find(|(candidate, _)| *candidate == screen)
            .map_or(&self.default_filters, |(_, filters)| filters)
    }

    pub fn update_query(&mut self, query: String, now: Instant) -> Option<SearchRequest> {
        self.query_error = None;
        self.server_error = None;
        if query.chars().count() > MAX_SEARCH_QUERY_CHARS {
            self.query = query.chars().take(MAX_SEARCH_QUERY_CHARS).collect();
            self.query_error = Some(SearchError::QueryTooLong);
            self.pending = None;
            self.rows.clear();
            self.selected_index = 0;
            self.status = SearchStatus::Unavailable;
            return None;
        }
        self.query = query;
        self.rows.clear();
        self.selected_index = 0;
        self.schedule(now, SearchStatus::Debouncing);
        None
    }

    pub fn invalidate_for_refresh(&mut self, now: Instant) {
        self.query_error = None;
        self.server_error = None;
        self.rows.clear();
        self.selected_index = 0;
        self.schedule(now, SearchStatus::StaleRefreshing);
    }

    fn schedule(&mut self, now: Instant, status: SearchStatus) {
        if self.query.trim().is_empty() {
            self.latest_request_id = None;
            self.pending = None;
            self.status = SearchStatus::Idle;
            return;
        }
        let Some(next_request_id) = self.next_request_id.checked_add(1) else {
            self.latest_request_id = None;
            self.pending = None;
            self.query_error = Some(SearchError::RequestIdExhausted);
            self.status = SearchStatus::Unavailable;
            return;
        };
        self.next_request_id = next_request_id;
        self.latest_request_id = Some(next_request_id);
        self.pending = Some((next_request_id, now + SEARCH_DEBOUNCE));
        self.status = status;
    }

    pub fn take_due_request(&mut self, now: Instant) -> Option<SearchRequest> {
        let (request_id, due_at) = self.pending?;
        if now < due_at {
            return None;
        }
        self.pending = None;
        self.last_issued_request_id = Some(request_id);
        self.status = SearchStatus::Loading;
        Some(SearchRequest {
            request_id,
            query: self.query.clone(),
            filters: self.filters(self.active_screen).clone(),
        })
    }

    pub fn apply_results(&mut self, request_id: u64, rows: Vec<SearchResult>) {
        self.apply_gateway_results(request_id, rows, None);
    }

    pub fn apply_gateway_results(
        &mut self,
        request_id: u64,
        mut rows: Vec<SearchResult>,
        error: Option<String>,
    ) -> bool {
        if self.response_disposition(request_id) != SearchResponseDisposition::Current {
            return false;
        }
        self.completed_through_request_id = self.completed_through_request_id.max(request_id);
        rows.truncate(MAX_SEARCH_RESULTS);
        self.rows = rows;
        self.selected_index = self.selected_index.min(self.rows.len().saturating_sub(1));
        self.server_error = error;
        self.status = if self.server_error.is_some() {
            if self.rows.is_empty() {
                SearchStatus::Unavailable
            } else {
                SearchStatus::Incomplete
            }
        } else {
            SearchStatus::Fresh
        };
        true
    }

    pub fn response_disposition(&self, request_id: u64) -> SearchResponseDisposition {
        let Some(last_issued) = self.last_issued_request_id else {
            return SearchResponseDisposition::Unknown;
        };
        if request_id == 0 || request_id > last_issued {
            return SearchResponseDisposition::Unknown;
        }
        if self.latest_request_id == Some(request_id)
            && request_id > self.completed_through_request_id
        {
            SearchResponseDisposition::Current
        } else {
            SearchResponseDisposition::Superseded
        }
    }

    pub fn complete_without_results(&mut self, request_id: u64) {
        self.completed_through_request_id = self.completed_through_request_id.max(request_id);
    }

    pub fn await_resnapshot(&mut self, request_id: u64) {
        self.complete_without_results(request_id);
        self.pending = None;
        self.latest_request_id = None;
        self.rows.clear();
        self.selected_index = 0;
        self.server_error = None;
        self.status = SearchStatus::StaleRefreshing;
    }

    pub fn results(&self) -> &[SearchResult] {
        &self.rows
    }

    pub fn move_selection(&mut self, forward: bool) {
        if self.rows.is_empty() {
            self.selected_index = 0;
        } else if forward {
            self.selected_index = self
                .selected_index
                .saturating_add(1)
                .min(self.rows.len() - 1);
        } else {
            self.selected_index = self.selected_index.saturating_sub(1);
        }
    }

    pub fn selected_index(&self) -> usize {
        self.selected_index
    }

    pub fn select_index(&mut self, index: usize) {
        if !self.rows.is_empty() {
            self.selected_index = index.min(self.rows.len() - 1);
        }
    }

    pub fn open_selected(&self) -> Option<NavigationTarget> {
        self.rows
            .get(self.selected_index)
            .map(|row| row.target.clone())
    }

    pub fn result_for(
        &self,
        screen: Screen,
        detail_kind: DetailKind,
        entity_id: &str,
    ) -> Option<&SearchResult> {
        self.rows.iter().find(|row| {
            row.target.screen == screen
                && row.target.detail_kind == detail_kind
                && row.target.entity_id.eq_ignore_ascii_case(entity_id)
        })
    }

    pub fn query(&self) -> &str {
        &self.query
    }

    pub fn query_error(&self) -> Option<SearchError> {
        self.query_error
    }

    pub fn server_error(&self) -> Option<&str> {
        self.server_error.as_deref()
    }

    pub fn status(&self) -> SearchStatus {
        self.status
    }

    pub fn latest_request_id(&self) -> Option<u64> {
        self.latest_request_id
    }

    pub fn clear_results(&mut self) {
        self.pending = None;
        self.latest_request_id = None;
        self.rows.clear();
        self.selected_index = 0;
        self.server_error = None;
        self.status = SearchStatus::Idle;
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SearchError {
    QueryTooLong,
    RequestIdExhausted,
}

impl fmt::Display for SearchError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::QueryTooLong => {
                formatter.write_str("search query exceeds 256 Unicode characters")
            }
            Self::RequestIdExhausted => formatter.write_str("search request IDs are exhausted"),
        }
    }
}

impl Error for SearchError {}

#[derive(Clone, Debug)]
struct IndexedRow {
    result: SearchResult,
    fields: Vec<String>,
}

#[derive(Clone, Debug, Default)]
pub struct SearchIndex {
    rows: Vec<IndexedRow>,
}

impl SearchIndex {
    pub fn from_snapshot(snapshot: &ConsoleSnapshot) -> Self {
        let mut index = Self::default();
        let mut seen = BTreeSet::new();

        for row in &snapshot.portfolio.rows {
            index.push_stock(
                row,
                snapshot
                    .portfolio
                    .as_of_utc
                    .as_ref()
                    .map(|value| value.as_str()),
                snapshot.portfolio.source.as_str(),
                &mut seen,
            );
        }
        for row in &snapshot.impact.holdings {
            index.push_stock(
                row,
                snapshot
                    .impact
                    .as_of_utc
                    .as_ref()
                    .map(|value| value.as_str()),
                snapshot.impact.source.as_str(),
                &mut seen,
            );
        }

        for row in &snapshot.agents.rows {
            index.push_agent(
                row,
                snapshot
                    .agents
                    .as_of_utc
                    .as_ref()
                    .map(|value| value.as_str()),
                snapshot.agents.source.as_str(),
                &mut seen,
            );
        }
        for row in &snapshot.impact.agents {
            index.push_agent(
                row,
                snapshot
                    .impact
                    .as_of_utc
                    .as_ref()
                    .map(|value| value.as_str()),
                snapshot.impact.source.as_str(),
                &mut seen,
            );
        }
        for row in &snapshot.orders.reconciliation_agents {
            index.push_agent(
                row,
                snapshot
                    .orders
                    .as_of_utc
                    .as_ref()
                    .map(|value| value.as_str()),
                snapshot.orders.source.as_str(),
                &mut seen,
            );
        }

        for row in &snapshot.models.opinions {
            index.push_model_opinion(row, snapshot.models.source.as_str(), &mut seen);
        }
        for row in &snapshot.models.candidates {
            index.push_model_candidate(row, snapshot.models.source.as_str(), &mut seen);
        }
        for row in &snapshot.orders.rows {
            index.push_order(row, snapshot.orders.source.as_str(), &mut seen);
        }
        for row in &snapshot.risk.approvals {
            let reason = row.reason.as_deref().unwrap_or("Reason unavailable");
            index.push(
                SearchKind::Approval,
                DetailKind::Approval,
                Screen::RiskApprovals,
                row.approval_id.as_str(),
                row.approval_id.as_str(),
                &format!("{:?} | {reason}", row.state),
                Some(row.requested_at_utc.as_str()),
                snapshot.risk.source.as_str(),
                row.evidence_ids.iter().map(|value| value.as_str()),
                &mut seen,
            );
        }

        for row in &snapshot.timeline.rows {
            index.push_event(row, snapshot.timeline.source.as_str(), &mut seen);
        }
        for (rows, source) in [
            (&snapshot.impact.events, snapshot.impact.source.as_str()),
            (
                &snapshot.portfolio.history,
                snapshot.portfolio.source.as_str(),
            ),
            (&snapshot.orders.history, snapshot.orders.source.as_str()),
            (&snapshot.agents.history, snapshot.agents.source.as_str()),
            (&snapshot.memory.history, snapshot.memory.source.as_str()),
        ] {
            for row in rows {
                index.push_event(row, source, &mut seen);
            }
        }

        for row in &snapshot.data.evidence {
            index.push_evidence(row, &mut seen);
        }
        for row in &snapshot.models.evidence {
            index.push_evidence(row, &mut seen);
        }
        for row in &snapshot.memory.rows {
            index.push_memory(row, snapshot.memory.source.as_str(), &mut seen);
        }
        for row in &snapshot.data.sources {
            index.push_source(row, snapshot.data.source.as_str(), &mut seen);
        }
        for row in &snapshot.system.repositories {
            index.push_repository(row, &mut seen);
        }

        index
    }

    pub fn search(
        &self,
        query: &str,
        filters: &SearchFilters,
        limit: usize,
    ) -> Result<Vec<SearchResult>, SearchError> {
        if query.chars().count() > MAX_SEARCH_QUERY_CHARS {
            return Err(SearchError::QueryTooLong);
        }
        let query = normalize(query.trim());
        if query.is_empty() || limit == 0 {
            return Ok(Vec::new());
        }
        let query_tokens = search_tokens(&query);
        if query_tokens.is_empty() {
            return Ok(Vec::new());
        }
        let normalized_source = filters.source.as_deref().map(normalize);
        let candidates = self
            .rows
            .iter()
            .filter(|row| {
                filters
                    .screen
                    .is_none_or(|screen| row.result.target.screen == screen)
                    && (filters.kinds.is_empty() || filters.kinds.contains(&row.result.kind))
                    && normalized_source
                        .as_ref()
                        .is_none_or(|source| *source == normalize(&row.result.source))
            })
            .filter_map(|row| {
                let entity_id = normalize(&row.result.entity_id);
                let document_tokens = row
                    .fields
                    .iter()
                    .flat_map(|field| search_tokens(field))
                    .collect::<Vec<_>>();
                let rank = if row.result.kind == SearchKind::Stock && entity_id == query {
                    0
                } else if entity_id == query {
                    1
                } else if row.fields.iter().any(|field| field.starts_with(&query)) {
                    2
                } else if query_tokens.iter().all(|query_token| {
                    document_tokens
                        .iter()
                        .any(|token| token.starts_with(query_token))
                }) {
                    3
                } else {
                    return None;
                };
                Some((row, rank, entity_id, document_tokens))
            })
            .collect::<Vec<_>>();
        let average_length = if candidates.is_empty() {
            1.0
        } else {
            candidates.iter().map(|row| row.3.len() as f64).sum::<f64>() / candidates.len() as f64
        };
        let document_frequencies = query_tokens
            .iter()
            .map(|query_token| {
                candidates
                    .iter()
                    .filter(|row| row.3.iter().any(|token| token.starts_with(query_token)))
                    .count()
            })
            .collect::<Vec<_>>();
        let candidate_count = candidates.len();
        let mut matches = candidates
            .into_iter()
            .map(|(row, rank, entity_id, document_tokens)| {
                let relevance = bm25_relevance(
                    &document_tokens,
                    &query_tokens,
                    &document_frequencies,
                    candidate_count,
                    average_length,
                );
                (
                    rank,
                    relevance,
                    row.result.kind.order(),
                    entity_id,
                    normalize(&row.result.title),
                    row.result.clone(),
                )
            })
            .collect::<Vec<_>>();
        matches.sort_by(|left, right| {
            left.0
                .cmp(&right.0)
                .then_with(|| right.1.total_cmp(&left.1))
                .then_with(|| left.2.cmp(&right.2))
                .then_with(|| left.3.cmp(&right.3))
                .then_with(|| left.4.cmp(&right.4))
        });
        Ok(matches
            .into_iter()
            .take(limit.min(MAX_SEARCH_RESULTS))
            .map(|row| row.5)
            .collect())
    }

    fn push_stock(
        &mut self,
        row: &PortfolioRow,
        timestamp: Option<&str>,
        source: &str,
        seen: &mut BTreeSet<(u8, DetailKind, String)>,
    ) {
        let description = row
            .description
            .as_deref()
            .unwrap_or("Description unavailable");
        self.push(
            SearchKind::Stock,
            DetailKind::Stock,
            Screen::Portfolio,
            row.symbol.as_str(),
            row.symbol.as_str(),
            &format!("{description} | {}", asset_type(row.asset_type)),
            timestamp,
            source,
            [description, asset_type(row.asset_type)],
            seen,
        );
    }

    fn push_agent(
        &mut self,
        row: &AgentCard,
        timestamp: Option<&str>,
        source: &str,
        seen: &mut BTreeSet<(u8, DetailKind, String)>,
    ) {
        let model = row.model.as_deref().unwrap_or("Model unavailable");
        let text = format!("{} | {:?} | {model}", row.title.as_str(), row.stage);
        let mut extra = row
            .affected_areas
            .iter()
            .map(String::as_str)
            .collect::<Vec<_>>();
        extra.extend([row.agent.as_str(), row.title.as_str(), model]);
        self.push(
            SearchKind::Agent,
            DetailKind::Agent,
            Screen::Agents,
            row.work_id.as_str(),
            row.agent.as_str(),
            &text,
            timestamp,
            source,
            extra,
            seen,
        );
    }

    fn push_model_opinion(
        &mut self,
        row: &ModelOpinionRow,
        source: &str,
        seen: &mut BTreeSet<(u8, DetailKind, String)>,
    ) {
        self.push(
            SearchKind::Model,
            DetailKind::ModelOpinion,
            Screen::ModelsRegime,
            row.model_id.as_str(),
            row.model_id.as_str(),
            &format!("{} | confidence {:.4}", row.regime.as_str(), row.confidence),
            Some(row.as_of_utc.as_str()),
            source,
            [row.regime.as_str()],
            seen,
        );
    }

    fn push_model_candidate(
        &mut self,
        row: &CandidateRow,
        source: &str,
        seen: &mut BTreeSet<(u8, DetailKind, String)>,
    ) {
        let text = format!(
            "{} | {:?} | {:?}",
            row.family.as_str(),
            row.strategy,
            row.status
        );
        let mut extra = row
            .evidence_ids
            .iter()
            .map(|value| value.as_str())
            .collect::<Vec<_>>();
        extra.push(row.family.as_str());
        self.push(
            SearchKind::Model,
            DetailKind::ModelCandidate,
            Screen::ModelsRegime,
            row.candidate_id.as_str(),
            row.candidate_id.as_str(),
            &text,
            Some(row.created_at_utc.as_str()),
            source,
            extra,
            seen,
        );
    }

    fn push_order(
        &mut self,
        row: &OrderRow,
        source: &str,
        seen: &mut BTreeSet<(u8, DetailKind, String)>,
    ) {
        let broker = row
            .broker_order_id
            .as_deref()
            .unwrap_or("Broker ID unavailable");
        self.push(
            SearchKind::Order,
            DetailKind::Order,
            Screen::Orders,
            row.order_id.as_str(),
            &format!("{:?} {}", row.side, row.symbol.as_str()),
            &format!("{:?} | {broker} | {:?}", row.status, row.reconciliation),
            row.submitted_at_utc.as_ref().map(|value| value.as_str()),
            source,
            [row.symbol.as_str(), broker],
            seen,
        );
    }

    fn push_event(
        &mut self,
        row: &TimelineRow,
        source: &str,
        seen: &mut BTreeSet<(u8, DetailKind, String)>,
    ) {
        let mut extra = row
            .evidence_ids
            .iter()
            .map(|value| value.as_str())
            .collect::<Vec<_>>();
        extra.extend(
            [
                row.agent_id.as_ref(),
                row.symbol.as_ref(),
                row.model_id.as_ref(),
                row.approval_id.as_ref(),
                row.order_id.as_ref(),
            ]
            .into_iter()
            .flatten()
            .map(|value| value.as_str()),
        );
        self.push(
            SearchKind::Event,
            DetailKind::Event,
            Screen::Timeline,
            row.event_id.as_str(),
            row.summary.as_str(),
            &format!("{:?} | impact {}", row.severity, row.impact),
            Some(row.occurred_at_utc.as_str()),
            source,
            extra,
            seen,
        );
    }

    fn push_evidence(&mut self, row: &EvidenceRow, seen: &mut BTreeSet<(u8, DetailKind, String)>) {
        self.push(
            SearchKind::Evidence,
            DetailKind::Evidence,
            Screen::DataEvidence,
            row.evidence_id.as_str(),
            row.evidence_id.as_str(),
            row.evidence_type.as_str(),
            Some(row.created_at_utc.as_str()),
            row.source.as_str(),
            [row.evidence_type.as_str()],
            seen,
        );
    }

    fn push_memory(
        &mut self,
        row: &MemoryRow,
        source: &str,
        seen: &mut BTreeSet<(u8, DetailKind, String)>,
    ) {
        self.push(
            SearchKind::Memory,
            DetailKind::Memory,
            Screen::Memory,
            row.memory_id.as_str(),
            row.summary.as_str(),
            &format!("{:?}", row.status),
            Some(row.updated_at_utc.as_str()),
            source,
            row.evidence_ids.iter().map(|value| value.as_str()),
            seen,
        );
    }

    fn push_source(
        &mut self,
        row: &SourceRow,
        source: &str,
        seen: &mut BTreeSet<(u8, DetailKind, String)>,
    ) {
        let coverage = row.coverage.as_deref().unwrap_or("Coverage unavailable");
        let mut extra = row
            .consumers
            .iter()
            .map(|value| value.as_str())
            .collect::<Vec<_>>();
        extra.push(coverage);
        self.push(
            SearchKind::Source,
            DetailKind::Source,
            Screen::DataEvidence,
            row.source_id.as_str(),
            row.source_id.as_str(),
            &format!("{:?} | {coverage}", row.freshness),
            row.as_of_utc.as_ref().map(|value| value.as_str()),
            source,
            extra,
            seen,
        );
    }

    fn push_repository(
        &mut self,
        row: &RepositoryRow,
        seen: &mut BTreeSet<(u8, DetailKind, String)>,
    ) {
        let branch = row
            .branch
            .as_ref()
            .map_or("Branch unavailable", |value| value.as_str());
        let revision = row
            .revision
            .as_ref()
            .map_or("Revision unavailable", |value| value.as_str());
        let mut extra = row
            .worktrees
            .iter()
            .map(|value| value.as_str())
            .collect::<Vec<_>>();
        extra.extend([branch, revision]);
        if let Some(error) = row.error.as_deref() {
            extra.push(error);
        }
        self.push(
            SearchKind::Source,
            DetailKind::Repository,
            Screen::System,
            row.repository_id.as_str(),
            row.repository_id.as_str(),
            &format!("{:?} | {branch} | {revision}", row.freshness),
            row.as_of_utc.as_ref().map(|value| value.as_str()),
            row.source.as_str(),
            extra,
            seen,
        );
    }

    #[allow(clippy::too_many_arguments)]
    fn push<'a>(
        &mut self,
        kind: SearchKind,
        detail_kind: DetailKind,
        screen: Screen,
        entity_id: &str,
        title: &str,
        text: &str,
        timestamp_utc: Option<&str>,
        source: &str,
        extra_fields: impl IntoIterator<Item = &'a str>,
        seen: &mut BTreeSet<(u8, DetailKind, String)>,
    ) {
        let entity_id = sanitize_line(entity_id);
        let key = (kind.order(), detail_kind, normalize(&entity_id));
        if !seen.insert(key) {
            return;
        }
        let title = sanitize_line(title);
        let text = sanitize_line(text);
        let source = sanitize_line(source);
        let timestamp_utc = timestamp_utc.map(sanitize_line);
        let mut fields = vec![
            normalize(&entity_id),
            normalize(&title),
            normalize(&text),
            normalize(&source),
        ];
        fields.extend(
            extra_fields
                .into_iter()
                .map(sanitize_line)
                .map(|field| normalize(&field)),
        );
        self.rows.push(IndexedRow {
            result: SearchResult {
                kind,
                entity_id: entity_id.clone(),
                title,
                text,
                timestamp_utc,
                source,
                context_only: false,
                target: NavigationTarget {
                    screen,
                    kind,
                    detail_kind,
                    entity_id,
                },
            },
            fields,
        });
    }
}

fn normalize(value: &str) -> String {
    sanitize_line(value).to_lowercase()
}

fn search_tokens(value: &str) -> Vec<String> {
    value
        .split(|character: char| !character.is_alphanumeric() && character != '_')
        .filter(|token| !token.is_empty())
        .map(str::to_owned)
        .collect()
}

fn bm25_relevance(
    document_tokens: &[String],
    query_tokens: &[String],
    document_frequencies: &[usize],
    document_count: usize,
    average_length: f64,
) -> f64 {
    const K1: f64 = 1.2;
    const B: f64 = 0.75;
    let document_length = document_tokens.len() as f64;
    query_tokens
        .iter()
        .zip(document_frequencies)
        .map(|(query_token, document_frequency)| {
            let term_frequency = document_tokens
                .iter()
                .filter(|token| token.starts_with(query_token))
                .count() as f64;
            let idf = ((document_count as f64 - *document_frequency as f64 + 0.5)
                / (*document_frequency as f64 + 0.5)
                + 1.0)
                .ln();
            let denominator =
                term_frequency + K1 * (1.0 - B + B * document_length / average_length.max(1.0));
            if denominator == 0.0 {
                0.0
            } else {
                idf * term_frequency * (K1 + 1.0) / denominator
            }
        })
        .sum()
}

fn asset_type(value: AssetType) -> &'static str {
    match value {
        AssetType::Stock => "stock",
        AssetType::Etf => "ETF",
        AssetType::Cash => "cash",
    }
}
