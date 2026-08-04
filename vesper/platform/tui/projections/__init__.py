"""Read-only source adapters for the native V20 console."""

from .legacy_state import LegacyStateProjection
from .native_platform import NativePlatformProjection
from .platform_runtime import PlatformRuntimeProjection
from .timeline import EventTimelineProjection

__all__ = [
    "EventTimelineProjection",
    "LegacyStateProjection",
    "NativePlatformProjection",
    "PlatformRuntimeProjection",
]
