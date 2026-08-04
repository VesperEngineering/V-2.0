"""Read-only source adapters for the native V20 console."""

from .legacy_state import LegacyStateProjection
from .native_platform import NativePlatformProjection

__all__ = ["LegacyStateProjection", "NativePlatformProjection"]
