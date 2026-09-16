"""Safe reading and tag handling for .ass/.srt subtitle files (copied from src/ass; the writer is not needed here)."""
from .models import (
    DEFAULT_EVENT_FORMAT,
    AssFile,
    Event,
    Section,
    seconds_to_timestamp,
    timestamp_to_seconds,
)
from .parser import EVENT_PLACEHOLDER, parse_bytes, parse_file, parse_string, parse_styles
from .tags import (
    ProtectedText,
    has_tags,
    is_translatable,
    protect,
    restore,
    strip_tags,
    validate_tags,
)
from .validator import cyrillic_ratio, latin_ratio, validate_structure, validate_translation

__all__ = [
    "DEFAULT_EVENT_FORMAT", "AssFile", "Event", "Section",
    "seconds_to_timestamp", "timestamp_to_seconds",
    "EVENT_PLACEHOLDER", "parse_bytes", "parse_file", "parse_string", "parse_styles",
    "ProtectedText", "has_tags", "is_translatable", "protect", "restore",
    "strip_tags", "validate_tags",
    "cyrillic_ratio", "latin_ratio", "validate_structure", "validate_translation",
]
