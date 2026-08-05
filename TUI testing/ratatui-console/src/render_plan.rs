use std::collections::BTreeSet;

use crate::contract::EventTarget;

/// Full-width vertical shell strips that can be rendered independently.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum ShellRegion {
    Header,
    Navigation,
    Alerts,
    Body,
    Input,
    Footer,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum RenderPlan {
    Full,
    Partial(BTreeSet<ShellRegion>),
}

impl RenderPlan {
    pub fn partial<I>(regions: I) -> Self
    where
        I: IntoIterator<Item = ShellRegion>,
    {
        Self::Partial(regions.into_iter().collect())
    }

    pub fn for_event_targets<I>(targets: I) -> Self
    where
        I: IntoIterator<Item = EventTarget>,
    {
        Self::partial(targets.into_iter().map(region_for_target))
    }

    pub fn with_region(self, region: ShellRegion) -> Self {
        match self {
            Self::Full => Self::Full,
            Self::Partial(mut regions) => {
                regions.insert(region);
                Self::Partial(regions)
            }
        }
    }

    pub fn merge(self, other: Self) -> Self {
        match (self, other) {
            (Self::Full, _) | (_, Self::Full) => Self::Full,
            (Self::Partial(mut left), Self::Partial(right)) => {
                left.extend(right);
                Self::Partial(left)
            }
        }
    }

    pub fn regions(&self) -> Option<&BTreeSet<ShellRegion>> {
        match self {
            Self::Full => None,
            Self::Partial(regions) => Some(regions),
        }
    }
}

/// Exhaustive wire-target mapping. Adding a target requires choosing its shell strip here.
pub const fn region_for_target(target: EventTarget) -> ShellRegion {
    match target {
        EventTarget::ShellAlerts => ShellRegion::Alerts,
        EventTarget::ImpactHoldings
        | EventTarget::ImpactEvents
        | EventTarget::ImpactAgents
        | EventTarget::PortfolioRows
        | EventTarget::PortfolioReturnsToday
        | EventTarget::PortfolioReturnsSinceRebalance
        | EventTarget::PortfolioReturnsSinceStart
        | EventTarget::PortfolioMetrics
        | EventTarget::PortfolioHistory
        | EventTarget::OrdersRows
        | EventTarget::OrdersReconciliationAgents
        | EventTarget::OrdersHistory
        | EventTarget::AgentsRows
        | EventTarget::AgentsHistory
        | EventTarget::ModelsOpinions
        | EventTarget::ModelsCandidates
        | EventTarget::ModelsMetrics
        | EventTarget::ModelsEvidence
        | EventTarget::TimelineRows
        | EventTarget::RiskLimits
        | EventTarget::RiskApprovals
        | EventTarget::RiskAlerts
        | EventTarget::RiskMetrics
        | EventTarget::DataSources
        | EventTarget::DataEvidence
        | EventTarget::MemoryRows
        | EventTarget::MemoryHistory
        | EventTarget::SystemServices
        | EventTarget::SystemMetrics
        | EventTarget::SystemRepositories => ShellRegion::Body,
    }
}
