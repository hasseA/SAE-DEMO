"""Opaque private-memory artifact loader for SAE-DEMO.

Loads a small, demo-specific envelope from a local, gitignored path
(intended: `.local/memory/<name>.json`, never committed) and returns
its `payload` as an OPAQUE string. This module has no knowledge of
any private SAE schema and must never gain any — it does not know
what an emotion node, anchor memory, link, or memory kernel is, and
it never parses, transforms, derives from, or otherwise interprets
the payload's content. It validates only the envelope itself: that
required fields are present, that `format_version` is one this
loader supports, that `representation` is a recognized label, and
that the payload's SHA-256 matches the declared `content_sha256`.

This loader is generic: it works with any artifact matching the
envelope shape below and is not specific to any one Emotional Memory
lineage or research theme. It carries no logic for producing,
generating, or freshening an artifact — only for reading one that
already exists on disk.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Union

SUPPORTED_FORMAT_VERSION = 1
REPRESENTATION_PROFILE = "profile"
REPRESENTATION_NETWORK = "network"
SUPPORTED_REPRESENTATIONS = frozenset({REPRESENTATION_PROFILE, REPRESENTATION_NETWORK})

REQUIRED_ENVELOPE_KEYS = frozenset(
    {"format_version", "representation", "content_sha256", "payload"}
)


class MemoryArtifactError(RuntimeError):
    """Base class for opaque-memory-artifact loading errors."""


class MemoryArtifactNotFoundError(MemoryArtifactError):
    """Raised when no artifact file exists at the given path."""


class MemoryArtifactMalformedError(MemoryArtifactError):
    """Raised when the envelope isn't valid JSON or is missing required fields."""


class MemoryArtifactUnsupportedVersionError(MemoryArtifactError):
    """Raised when format_version is not one this loader supports."""


class MemoryArtifactUnknownRepresentationError(MemoryArtifactError):
    """Raised when representation is not a recognized label."""


class MemoryArtifactIntegrityError(MemoryArtifactError):
    """Raised when the payload's recomputed SHA-256 doesn't match content_sha256."""


@dataclass(frozen=True)
class OpaqueMemoryArtifact:
    """An opaque, already-prepared memory context ready to hand to a provider.

    `payload` is treated as opaque text everywhere in this project: it
    is never parsed, transformed, or inspected beyond being passed
    along exactly as loaded.
    """

    representation: str
    content_sha256: str
    payload: str


def _sha256_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_opaque_memory_artifact(path: Union[str, Path]) -> OpaqueMemoryArtifact:
    """Load and validate one opaque memory-artifact envelope from disk.

    Validates only the envelope: presence of required keys, a
    supported `format_version`, a recognized `representation` label,
    and that the payload's SHA-256 matches the declared
    `content_sha256`. Never parses, interprets, or transforms the
    payload text itself.
    """

    file_path = Path(path)
    if not file_path.is_file():
        raise MemoryArtifactNotFoundError(f"No memory artifact at {file_path}.")

    try:
        raw = file_path.read_text(encoding="utf-8")
        envelope: Any = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MemoryArtifactMalformedError(
            f"Could not read/parse memory artifact envelope: {exc.__class__.__name__}"
        ) from None

    if not isinstance(envelope, dict):
        raise MemoryArtifactMalformedError("Memory artifact envelope is not a JSON object.")

    missing = REQUIRED_ENVELOPE_KEYS - envelope.keys()
    if missing:
        raise MemoryArtifactMalformedError(
            f"Memory artifact envelope is missing required field(s): {sorted(missing)}."
        )

    format_version = envelope["format_version"]
    if format_version != SUPPORTED_FORMAT_VERSION:
        raise MemoryArtifactUnsupportedVersionError(
            f"Unsupported memory artifact format_version {format_version!r}; "
            f"expected {SUPPORTED_FORMAT_VERSION!r}."
        )

    representation = envelope["representation"]
    if representation not in SUPPORTED_REPRESENTATIONS:
        raise MemoryArtifactUnknownRepresentationError(
            f"Unknown memory artifact representation {representation!r}; "
            f"expected one of {sorted(SUPPORTED_REPRESENTATIONS)}."
        )

    payload = envelope["payload"]
    if not isinstance(payload, str):
        raise MemoryArtifactMalformedError("Memory artifact 'payload' must be a string.")

    declared_hash = envelope["content_sha256"]
    actual_hash = _sha256_of(payload)
    if declared_hash != actual_hash:
        raise MemoryArtifactIntegrityError(
            "Memory artifact payload failed SHA-256 verification "
            "(declared content_sha256 does not match the recomputed hash)."
        )

    return OpaqueMemoryArtifact(
        representation=representation,
        content_sha256=declared_hash,
        payload=payload,
    )
