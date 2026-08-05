"""Read-only source adapters for the native V20 console."""

from .legacy_state import LegacyStateProjection
from .managed_memory import ManagedMemoryProjection
from .native_platform import NativePlatformProjection
from .operations_status import AttentionAlertProjection, NotificationHealthProjection
from .platform_runtime import PlatformRuntimeProjection
from .timeline import EventTimelineProjection

__all__ = [
    "EventTimelineProjection",
    "LegacyStateProjection",
    "ManagedMemoryProjection",
    "NativePlatformProjection",
    "AttentionAlertProjection",
    "NotificationHealthProjection",
    "PlatformRuntimeProjection",
]
