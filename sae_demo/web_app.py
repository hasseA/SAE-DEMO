"""Minimal FastAPI web shell for SAE-DEMO (M5A, extended M5B, M5C).

This module serves the static frontend and exposes a small, typed
API. M5A added a health/status API only. M5B wired the existing,
unchanged ``ScenarioEngine`` into a Memory-OFF, provider-free
scenario-run flow. M5C connects that same flow to the existing,
unchanged ``NebiusProvider``, opaque memory loader, and M4B
behavioral-use policy, so each "advance" now sends the next segment
through a real provider call and returns a real assistant response,
under either Memory OFF or Memory ON.

M5C deliberately does not implement a second copy of memory-placement
or behavioral-policy semantics: it drives
``compatibility_runner.CompatibilityRunner.build_history()`` /
``.send_turn()`` (the exact same implementation ``CompatibilityRunner
.run()`` itself uses internally, factored out for step-by-step use --
see that module's docstring) instead of reimplementing message
ordering here. This module never parses, transforms, or inspects an
Emotional Memory payload -- it only loads it opaquely (once, at run
start, via ``sae_demo/memory_loader.py``) and hands it to the runner
exactly as loaded.

Memory ON uses exactly one operator-configured artifact, resolved from
the ``SAE_DEMO_MEMORY_FILE`` environment variable -- never a hardcoded
path or filename in source, and never a profile/network choice exposed
to the UI. Run state (including conversation history and any loaded
memory payload) lives only in a process-local, in-memory registry;
nothing is written to disk, and a server restart clears every run.

No response from this module ever includes: the API key, ``.env``
contents, the memory payload, its hash, its file path or
representation label, the system message, the behavioral-use policy
text, or any other private/internal detail -- see ``StatusResponse``,
``RunState``, and the safe, generic error messages used throughout.
"""

from __future__ import annotations

import os
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .compatibility_runner import (
    DEFAULT_BEHAVIORAL_USE_POLICY,
    DEFAULT_MAX_TOKENS,
    CompatibilityRunner,
    MemoryPayloadIntegrityError,
    TurnMetadata,
)
from .config import DEFAULT_NEBIUS_MODEL, MissingNebiusAPIKeyError, load_nebius_config
from .memory_loader import MemoryArtifactError, load_opaque_memory_artifact
from .nebius_provider import NebiusProvider
from .scenario import MODE_FROZEN, Scenario
from .scenario_engine import NoMoreSegmentsError, ScenarioEngine, SentSegmentRecord

# Reuses the same clean-room synthetic fixture builders already used by
# scripts/run_compatibility.py and the offline scenario-engine tests --
# not duplicated here. Both fixtures are entirely synthetic; see
# tests/fixtures/synthetic_scenarios.py for their content and
# provenance note.
from tests.fixtures.synthetic_scenarios import (
    build_benign_transition_fixture,
    build_irreversible_loss_fixture,
)

APP_NAME = "SAE-DEMO"
STAGE_LABEL = "M5C"
MEMORY_FEATURE_STATUS = "active in M5C (one configured artifact, Memory ON/OFF)"
SCENARIO_FEATURE_STATUS = "active in M5C (real provider responses)"

# Never a hardcoded path or filename -- an operator points this at a
# local, gitignored artifact under .local/memory/ themselves, exactly
# as scripts/run_compatibility.py's --memory-file already requires.
MEMORY_FILE_ENV_VAR = "SAE_DEMO_MEMORY_FILE"

# Safe, generic messages only -- never a file path, hash, representation
# label, or raw exception text.
MEMORY_NOT_CONFIGURED_MESSAGE = "Memory artifact is not configured for this demo."
MEMORY_LOAD_FAILED_MESSAGE = "Memory artifact could not be loaded."
MEMORY_INTEGRITY_FAILED_MESSAGE = "Memory artifact failed integrity verification."
PROVIDER_NOT_CONFIGURED_MESSAGE = "Provider is not configured for this demo."
PROVIDER_REQUEST_FAILED_MESSAGE = "The model provider request failed. Please try again."

MEMORY_OFF = "off"
MEMORY_ON = "on"

STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_HTML_PATH = STATIC_DIR / "index.html"

# The only built-in, public-safe synthetic scenarios exposed by this
# app. Keys are the same short, public identifiers already used by
# scripts/run_compatibility.py's --fixture flag -- not the internal
# Scenario.scenario_id values, and not any private Experiment 8
# identifier.
BUILTIN_SCENARIOS: Dict[str, Callable[..., Scenario]] = {
    "greenhouse": build_irreversible_loss_fixture,
    "new_studio": build_benign_transition_fixture,
}

# Generic, public-safe human-readable labels for the existing semantic
# role keys (sae_demo.scenario.VALID_SEMANTIC_ROLES). Describes story
# function only -- not private SAE memory structure.
ROLE_LABELS: Dict[str, str] = {
    "background_attachment": "Background & attachment",
    "residual_possibility": "Remaining possibility",
    "irreversibility": "Irreversible change",
    "neutral_event": "Neutral event",
    "meaning": "Meaning",
    "relational_pressure": "Relational pressure",
    "closure": "Closure",
}


def _role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role)


class HealthResponse(BaseModel):
    """Minimal liveness response. No environment or private data."""

    status: str


class StatusResponse(BaseModel):
    """Public-safe demo status for the frontend.

    ``provider_configured`` is a boolean only -- derived from whether
    ``NEBIUS_API_KEY`` is present in the environment, never from its
    value, and the value itself is never read into this response.
    """

    application: str
    stage: str
    backend_status: str
    target_model: str
    provider_configured: bool
    memory_feature_status: str
    scenario_feature_status: str


class ScenarioSummary(BaseModel):
    """Public-safe scenario listing entry. No segment text included."""

    id: str
    title: str
    description: str
    segment_count: int


class SegmentView(BaseModel):
    """One not-yet-sent scenario segment, as previewed to the web UI.

    ``role`` is the existing generic semantic-role key; ``role_label``
    is its public-safe human-readable form (see ``ROLE_LABELS``).
    """

    segment_id: str
    role: str
    role_label: str
    text: str


class ConversationTurn(BaseModel):
    """One already-sent segment, paired with its assistant response.

    ``assistant_text`` and ``error`` are mutually exclusive in
    practice: a successful turn has a response and no error; a failed
    turn (a provider request that failed) has no response and a safe,
    generic error message instead -- never a fabricated response.
    Never includes the memory payload, the system message, or the
    behavioral-use policy text -- only the scenario segment's own text
    and the model's reply to it.
    """

    segment_id: str
    role: str
    role_label: str
    user_text: str
    assistant_text: Optional[str] = None
    reasoning_present: bool = False
    error: Optional[str] = None


class RunState(BaseModel):
    """Full state of one in-memory scenario run.

    ``memory_mode`` is fixed for the lifetime of a run -- it is set
    once at start and never changes. ``current_segment`` is the next
    not-yet-sent segment (``None`` once the run is complete or has
    failed). ``transcript`` holds only segments already sent, each
    paired with its assistant response (or a safe error if that
    segment's provider call failed).
    """

    run_id: str
    scenario_id: str
    scenario_title: str
    mode: str
    memory_mode: str
    total_segments: int
    current_segment_number: int
    completed: bool
    failed: bool
    error: Optional[str] = None
    current_segment: Optional[SegmentView] = None
    transcript: List[ConversationTurn] = []


class StartRunRequest(BaseModel):
    scenario_id: str
    # Optional and defaulting to "off" so an older, pre-M5C request
    # body (scenario_id only) still behaves exactly as Memory OFF.
    # Any other value is rejected (422) by this Literal type -- this is
    # the "validate strictly" requirement for M5C.
    memory_mode: Literal["off", "on"] = "off"


@dataclass
class _RunEntry:
    engine: ScenarioEngine
    scenario_key: str
    memory_mode: str
    runner: CompatibilityRunner
    history: List[Dict[str, str]]
    turns: List[TurnMetadata] = field(default_factory=list)
    failed: bool = False
    error: Optional[str] = None


# Process-local, in-memory only. No database, no disk persistence, no
# writes under .local/ -- a completed or in-progress run's transcript
# is never written to any tracked or runtime-data directory. Cleared
# on every server restart. The lock serializes registry reads/writes
# and per-run mutation (advancing a run) against concurrent requests
# within this one process -- it does not attempt to solve multi-user
# or distributed concurrency, which remains explicitly out of scope.
_RUN_REGISTRY: Dict[str, _RunEntry] = {}
_REGISTRY_LOCK = threading.Lock()


def _segment_view(segment) -> SegmentView:
    return SegmentView(
        segment_id=segment.segment_id,
        role=segment.role,
        role_label=_role_label(segment.role),
        text=segment.text,
    )


def _conversation_turn(record: SentSegmentRecord, turn: Optional[TurnMetadata]) -> ConversationTurn:
    if turn is None:
        return ConversationTurn(
            segment_id=record.segment_id,
            role=record.role,
            role_label=_role_label(record.role),
            user_text=record.text_sent,
        )
    return ConversationTurn(
        segment_id=record.segment_id,
        role=record.role,
        role_label=_role_label(record.role),
        user_text=record.text_sent,
        assistant_text=turn.assistant_text,
        reasoning_present=turn.reasoning_present,
        # A generic, safe message only -- never the underlying
        # exception text (which is itself already scrubbed by
        # NebiusProvider, but this module deliberately does not rely
        # on that and uses its own fixed, generic message instead).
        error=PROVIDER_REQUEST_FAILED_MESSAGE if turn.error is not None else None,
    )


def _run_state(run_id: str, entry: _RunEntry) -> RunState:
    engine = entry.engine
    trace = engine.run_trace()
    total_segments = len(trace.segment_order)

    turns_by_segment: Dict[str, TurnMetadata] = {turn.segment_id: turn for turn in entry.turns}
    transcript = [
        _conversation_turn(record, turns_by_segment.get(record.segment_id))
        for record in trace.sent_segments
    ]

    if entry.failed:
        current_segment = None
        current_segment_number = len(trace.sent_segments)
    elif engine.is_complete:
        current_segment = None
        current_segment_number = total_segments
    else:
        current_segment = _segment_view(engine.preview_next_segment())
        current_segment_number = len(trace.sent_segments) + 1

    return RunState(
        run_id=run_id,
        scenario_id=entry.scenario_key,
        scenario_title=trace.scenario_title,
        mode=trace.mode,
        memory_mode=entry.memory_mode,
        total_segments=total_segments,
        current_segment_number=current_segment_number,
        completed=engine.is_complete and not entry.failed,
        failed=entry.failed,
        error=entry.error,
        current_segment=current_segment,
        transcript=transcript,
    )


def _resolve_memory_payload():
    """Load the one configured Memory ON artifact, opaquely.

    Returns the loaded ``OpaqueMemoryArtifact``. Raises `HTTPException`
    (503, safe generic message) if no artifact is configured or it
    cannot be loaded/verified -- never exposes the configured path,
    the artifact's representation label, or any hash value. The
    payload itself is never parsed, transformed, or inspected here or
    anywhere downstream -- only passed through opaquely to
    `CompatibilityRunner`.
    """

    configured_path = os.environ.get(MEMORY_FILE_ENV_VAR)
    if not configured_path:
        raise HTTPException(status_code=503, detail=MEMORY_NOT_CONFIGURED_MESSAGE)

    try:
        return load_opaque_memory_artifact(configured_path)
    except MemoryArtifactError:
        raise HTTPException(status_code=503, detail=MEMORY_LOAD_FAILED_MESSAGE) from None


def _build_provider():
    """Construct a NebiusProvider from environment configuration only.

    Raises `HTTPException` (503, safe generic message) if no provider
    API key is configured. Never logs, returns, or otherwise exposes
    the key's value.
    """

    try:
        config = load_nebius_config()
    except MissingNebiusAPIKeyError:
        raise HTTPException(status_code=503, detail=PROVIDER_NOT_CONFIGURED_MESSAGE) from None

    return NebiusProvider(config), config.model


app = FastAPI(title=APP_NAME)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/api/status", response_model=StatusResponse)
def status() -> StatusResponse:
    # Presence check only -- the key's value is never read into this
    # response, logged, or otherwise exposed.
    provider_configured = bool(os.environ.get("NEBIUS_API_KEY"))

    return StatusResponse(
        application=APP_NAME,
        stage=STAGE_LABEL,
        backend_status="ok",
        target_model=DEFAULT_NEBIUS_MODEL,
        provider_configured=provider_configured,
        memory_feature_status=MEMORY_FEATURE_STATUS,
        scenario_feature_status=SCENARIO_FEATURE_STATUS,
    )


@app.get("/api/scenarios", response_model=List[ScenarioSummary])
def list_scenarios() -> List[ScenarioSummary]:
    summaries = []
    for scenario_id, build_fixture in BUILTIN_SCENARIOS.items():
        scenario = build_fixture(mode=MODE_FROZEN)
        summaries.append(
            ScenarioSummary(
                id=scenario_id,
                title=scenario.title,
                description=scenario.description,
                segment_count=len(scenario.segments),
            )
        )
    return summaries


@app.post("/api/runs", response_model=RunState, status_code=201)
def start_run(payload: StartRunRequest) -> RunState:
    build_fixture = BUILTIN_SCENARIOS.get(payload.scenario_id)
    if build_fixture is None:
        raise HTTPException(status_code=404, detail="Unknown scenario.")

    # Checked for both Memory OFF and Memory ON -- advancing either
    # condition requires a configured provider, so this is verified
    # up front rather than failing partway through a run.
    provider, model_label = _build_provider()

    memory_payload = None
    memory_payload_sha256 = None
    if payload.memory_mode == MEMORY_ON:
        artifact = _resolve_memory_payload()
        memory_payload = artifact.payload
        memory_payload_sha256 = artifact.content_sha256

    scenario = build_fixture(mode=MODE_FROZEN)
    engine = ScenarioEngine(scenario)

    runner = CompatibilityRunner(
        provider,
        model_label=model_label,
        max_tokens=DEFAULT_MAX_TOKENS,
        memory_payload=memory_payload,
        memory_payload_sha256=memory_payload_sha256,
        # Sent unconditionally, identically, for Memory OFF and Memory
        # ON alike -- never a condition-specific difference. This is
        # the same invariant scripts/run_compatibility.py already
        # relies on; see
        # docs/decisions/SAE_DEMO_M4_CONSUMPTION_BOUNDARY_FREEZE.md.
        behavioral_use_policy=DEFAULT_BEHAVIORAL_USE_POLICY,
    )

    try:
        history, _memory_used = runner.build_history()
    except MemoryPayloadIntegrityError:
        raise HTTPException(status_code=503, detail=MEMORY_INTEGRITY_FAILED_MESSAGE) from None

    run_id = uuid.uuid4().hex
    entry = _RunEntry(
        engine=engine,
        scenario_key=payload.scenario_id,
        memory_mode=payload.memory_mode,
        runner=runner,
        history=history,
    )

    with _REGISTRY_LOCK:
        _RUN_REGISTRY[run_id] = entry

    return _run_state(run_id, entry)


@app.get("/api/runs/{run_id}", response_model=RunState)
def get_run(run_id: str) -> RunState:
    entry = _RUN_REGISTRY.get(run_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Unknown run.")
    return _run_state(run_id, entry)


@app.post("/api/runs/{run_id}/advance", response_model=RunState)
def advance_run(run_id: str) -> RunState:
    with _REGISTRY_LOCK:
        entry = _RUN_REGISTRY.get(run_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Unknown run.")
        if entry.failed:
            raise HTTPException(status_code=409, detail="Run failed and cannot continue.")
        if entry.engine.is_complete:
            raise HTTPException(status_code=409, detail="Run already completed.")

        try:
            sent_record = entry.engine.advance()
        except NoMoreSegmentsError as exc:  # pragma: no cover - defensive
            raise HTTPException(status_code=409, detail="Run already completed.") from exc

        turn = entry.runner.send_turn(
            entry.history, sent_record.segment_id, sent_record.role, sent_record.text_sent
        )
        entry.turns.append(turn)

        if turn.error is not None:
            entry.failed = True
            entry.error = PROVIDER_REQUEST_FAILED_MESSAGE
        else:
            entry.engine.record_model_response(sent_record.segment_id, turn.assistant_text or "")

    return _run_state(run_id, entry)


@app.get("/")
def root() -> FileResponse:
    return FileResponse(INDEX_HTML_PATH)


# Serves styles.css / app.js (and any future static asset) under /static/*.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
