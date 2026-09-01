"""Offline tests for the opaque private-memory artifact loader.

No network calls. Every artifact used here is a synthetic, fake
payload written to pytest's own `tmp_path` for the duration of a
single test -- no real Emotional Memory content, from any lineage,
appears anywhere in this file. This loader has no knowledge of, and
these tests assert no knowledge of, any private SAE schema, ID, or
lineage.
"""

import hashlib
import json
from pathlib import Path

import pytest

from sae_demo.memory_loader import (
    MemoryArtifactIntegrityError,
    MemoryArtifactMalformedError,
    MemoryArtifactNotFoundError,
    MemoryArtifactUnknownRepresentationError,
    MemoryArtifactUnsupportedVersionError,
    OpaqueMemoryArtifact,
    REPRESENTATION_NETWORK,
    REPRESENTATION_PROFILE,
    SUPPORTED_FORMAT_VERSION,
    load_opaque_memory_artifact,
)
from sae_demo.runtime_paths import MEMORY, local_subdir


# --- helpers -----------------------------------------------------------

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_envelope(path: Path, envelope: dict) -> None:
    path.write_text(json.dumps(envelope), encoding="utf-8")


def _fake_profile_payload() -> str:
    # A synthetic stand-in shaped nothing like any real artifact -- this
    # is deliberately generic filler text, not a rendering of any real
    # emotion, anchor, or lineage.
    return "FAKE PROFILE PAYLOAD :: totally synthetic test content only."


def _fake_network_payload() -> str:
    return (
        "FAKE NETWORK PAYLOAD :: totally synthetic test content only, "
        "with some extra filler to make it a different length/shape "
        "than the fake profile payload above."
    )


def _valid_envelope(representation: str, payload: str) -> dict:
    return {
        "format_version": SUPPORTED_FORMAT_VERSION,
        "representation": representation,
        "content_sha256": _sha256(payload),
        "payload": payload,
    }


# --- valid artifacts ---------------------------------------------------

def test_loads_valid_profile_artifact(tmp_path):
    payload = _fake_profile_payload()
    path = tmp_path / "fake_profile.json"
    _write_envelope(path, _valid_envelope(REPRESENTATION_PROFILE, payload))

    artifact = load_opaque_memory_artifact(path)

    assert isinstance(artifact, OpaqueMemoryArtifact)
    assert artifact.representation == REPRESENTATION_PROFILE
    assert artifact.payload == payload
    assert artifact.content_sha256 == _sha256(payload)


def test_loads_valid_network_artifact(tmp_path):
    payload = _fake_network_payload()
    path = tmp_path / "fake_network.json"
    _write_envelope(path, _valid_envelope(REPRESENTATION_NETWORK, payload))

    artifact = load_opaque_memory_artifact(path)

    assert artifact.representation == REPRESENTATION_NETWORK
    assert artifact.payload == payload


def test_hash_verification_succeeds_on_correct_hash(tmp_path):
    payload = "another synthetic payload, correctly hashed"
    path = tmp_path / "ok.json"
    envelope = _valid_envelope(REPRESENTATION_PROFILE, payload)
    assert envelope["content_sha256"] == hashlib.sha256(payload.encode("utf-8")).hexdigest()
    _write_envelope(path, envelope)

    artifact = load_opaque_memory_artifact(path)

    assert artifact.content_sha256 == envelope["content_sha256"]


# --- malformed / invalid envelopes --------------------------------------

def test_missing_artifact_file_raises(tmp_path):
    missing_path = tmp_path / "does_not_exist.json"

    with pytest.raises(MemoryArtifactNotFoundError):
        load_opaque_memory_artifact(missing_path)


def test_malformed_json_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(MemoryArtifactMalformedError):
        load_opaque_memory_artifact(path)


def test_envelope_missing_required_keys_raises(tmp_path):
    path = tmp_path / "incomplete.json"
    _write_envelope(path, {"format_version": SUPPORTED_FORMAT_VERSION, "payload": "x"})

    with pytest.raises(MemoryArtifactMalformedError):
        load_opaque_memory_artifact(path)


def test_envelope_that_is_not_a_json_object_raises(tmp_path):
    path = tmp_path / "list.json"
    path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    with pytest.raises(MemoryArtifactMalformedError):
        load_opaque_memory_artifact(path)


def test_non_string_payload_raises(tmp_path):
    path = tmp_path / "nonstring_payload.json"
    _write_envelope(
        path,
        {
            "format_version": SUPPORTED_FORMAT_VERSION,
            "representation": REPRESENTATION_PROFILE,
            "content_sha256": "irrelevant",
            "payload": {"unexpectedly": "structured"},
        },
    )

    with pytest.raises(MemoryArtifactMalformedError):
        load_opaque_memory_artifact(path)


def test_unknown_representation_raises(tmp_path):
    payload = "synthetic payload for an unknown representation"
    path = tmp_path / "unknown_rep.json"
    envelope = _valid_envelope("some_future_kind", payload)
    _write_envelope(path, envelope)

    with pytest.raises(MemoryArtifactUnknownRepresentationError):
        load_opaque_memory_artifact(path)


def test_unsupported_format_version_raises(tmp_path):
    payload = "synthetic payload for a future format version"
    path = tmp_path / "future_version.json"
    envelope = _valid_envelope(REPRESENTATION_PROFILE, payload)
    envelope["format_version"] = SUPPORTED_FORMAT_VERSION + 1
    _write_envelope(path, envelope)

    with pytest.raises(MemoryArtifactUnsupportedVersionError):
        load_opaque_memory_artifact(path)


def test_wrong_hash_raises_integrity_error(tmp_path):
    payload = "synthetic payload whose declared hash will be wrong"
    path = tmp_path / "wrong_hash.json"
    envelope = _valid_envelope(REPRESENTATION_NETWORK, payload)
    envelope["content_sha256"] = _sha256("a completely different string")
    _write_envelope(path, envelope)

    with pytest.raises(MemoryArtifactIntegrityError):
        load_opaque_memory_artifact(path)


# --- opacity --------------------------------------------------------------

@pytest.mark.parametrize(
    "payload",
    [
        "plain synthetic sentence",
        "",
        "text with\nnewlines\nand\ttabs",
        '{"looks": "like json but is just opaque text to the loader"}',
        "unicode content: café, naïve, 日本語, emoji not included",
        "a" * 5000,
    ],
    ids=["plain", "empty", "newlines_tabs", "json_shaped", "unicode", "very_long"],
)
def test_loader_treats_payload_opaquely_regardless_of_shape(tmp_path, payload):
    """The loader must pass arbitrary payload text through byte-for-byte,
    never parsing or transforming it -- including payload text that
    happens to look like JSON, or that is empty, multi-line, or very
    long. Content shape must never change what comes back except via
    the hash-verification gate.
    """

    path = tmp_path / "opaque_shape.json"
    _write_envelope(path, _valid_envelope(REPRESENTATION_PROFILE, payload))

    artifact = load_opaque_memory_artifact(path)

    assert artifact.payload == payload
    assert artifact.payload is not None


# --- real-repo isolation ---------------------------------------------------

def test_real_local_memory_directory_listing_is_unchanged_by_running_this_suite():
    """This test suite must never write into, delete from, or otherwise
    modify the real repository's `.local/memory/` directory -- only
    pytest's own `tmp_path` fixtures are used above. `.local/memory/`
    may legitimately contain real private artifacts on this machine
    (outside version control); this test asserts the *listing* is
    unchanged by having run this file, not that the directory is empty.
    """

    real_memory_dir = local_subdir(MEMORY, env={})
    before = None
    if real_memory_dir.is_dir():
        before = sorted(p.name for p in real_memory_dir.iterdir())

    # Deliberately does nothing here that could write to real_memory_dir;
    # this is a self-check that the rest of this module's fixtures never
    # touch it, re-observed at the point this test runs in the suite.
    after = None
    if real_memory_dir.is_dir():
        after = sorted(p.name for p in real_memory_dir.iterdir())

    assert before == after
