"""Minimal FastAPI web shell for SAE-DEMO (M5A, extended M5B/M5C/M5D/M5E).

This module serves the static frontend and exposes a small, typed
API. M5A added a health/status API only. M5B wired the existing,
unchanged ``ScenarioEngine`` into a Memory-OFF, provider-free
scenario-run flow. M5C connected that same flow to the existing,
unchanged ``NebiusProvider``, opaque memory loader, and M4B
behavioral-use policy, so each "advance" sends the next segment
through a real provider call and returns a real assistant response,
under either Memory OFF or Memory ON. M5D adds a *controlled*
comparison: once a run completes, its opposite-memory-mode condition
can be replayed as a completely fresh run of the *same* scenario, and
once both runs are complete, their transcripts can be viewed side by
side, aligned by segment. M5E adds no backend behavior at all: it is a
static, public-safe conceptual Emotional Memory diagram and a
conservative Experiment 8 evidence card, both served as plain HTML/CSS
content in ``static/index.html`` -- this module does not construct a
provider or load a memory artifact to render them, and they render
identically whether or not a provider or memory artifact is
configured. M5F adds a "Scenario Wizard" / Bring Your Own Story
workflow (see ``sae_demo/custom_scenario.py``): a user supplies plain-
language story ingredients, gets back a locally-generated copyable
prompt for an AI *they* choose (SAE-DEMO never calls one), pastes the
resulting seven-section story back, reviews/edits it, and explicitly
freezes it. A frozen custom scenario is resolved by
``_start_run_entry`` exactly like a built-in one -- see
``_resolve_scenario`` -- so it runs through the *same*, unmodified
controlled Memory OFF/ON comparison machinery M5D already built; no
second run/comparison engine exists for custom scenarios. Custom
scenario drafts are process-local and in-memory only, exactly like
runs and comparisons -- never written to disk, cleared on restart.
M5G is a hardening stage only: no new scientific claim, scoring, or
scenario/memory machinery is added. It resolves the completion-token
budget (``max_tokens``) from one configurable, environment-backed
function (``compatibility_runner.resolve_max_tokens``) instead of a
bare constant, still applied identically to Memory OFF and Memory ON
(see that function's docstring for the rationale), and hardens
``NebiusProvider`` against a malformed/empty provider response so a
provider-side surprise becomes a safe per-turn error instead of an
unhandled exception. It otherwise touches only frontend wording/
polish, error-message safety, and documentation.

M5C/M5D deliberately do not implement a second copy of memory-
placement or behavioral-policy semantics: every run drives
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
to the UI. Run and comparison state (including conversation history
and any loaded memory payload) lives only in process-local, in-memory
registries; nothing is written to disk, and a server restart clears
every run and comparison.

A comparison pair (M5D) is built entirely from the existing single-run
machinery: creating an "alternate" run reuses the exact same scenario
id and the exact same run-construction path (``_start_run_entry``) as
starting any other run, with only the memory mode flipped and a
completely fresh history -- it never reuses or reads the first run's
conversation history. A comparison is never assembled from two
unrelated runs: pairing is recorded only when M5D itself creates the
second run from a specific, already-completed first run.

No response from this module ever includes: the API key, ``.env``
contents, the memory payload, its hash, its file path or
representation label, the system message, the behavioral-use policy
text, or any other private/internal detail -- see ``StatusResponse``,
``RunState``, ``ComparisonState``, and the safe, generic error
messages used throughout. This module performs no automated scoring,
sentiment analysis, or "which response is better" judgment of any
kind -- a comparison is only the two aligned transcripts, for a human
to read.
"""

from __future__ import annotations

import os
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Literal, Optional, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .compatibility_runner import (
    DEFAULT_BEHAVIORAL_USE_POLICY,
    CompatibilityRunner,
    MemoryPayloadIntegrityError,
    TurnMetadata,
    resolve_max_tokens,
)
from .config import DEFAULT_NEBIUS_MODEL, MissingNebiusAPIKeyError, load_nebius_config
from .memory_loader import MemoryArtifactError, load_opaque_memory_artifact
from .nebius_provider import NebiusProvider

# M5F: local, deterministic prompt generation + paste-format parsing +
# process-local draft/freeze support for custom scenarios. See that
# module's docstring -- it never calls a provider or the network, and
# never touches Emotional Memory. `custom_scenario` (the module) is
# used qualified below for everything except `CustomScenarioDraft`
# (used as a registry value type) and `parse_pasted_scenario` (used
# directly in the create-draft route).
from . import custom_scenario
from .custom_scenario import CustomScenarioDraft, parse_pasted_scenario
from .scenario import MODE_FROZEN, VALID_SEMANTIC_ROLES, Scenario
from .scenario import role_label as _role_label
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
STAGE_LABEL = "M5G"
MEMORY_FEATURE_STATUS = "active in M5C (one configured artifact, Memory ON/OFF)"
SCENARIO_FEATURE_STATUS = "active in M5F (built-in fixtures plus frozen custom scenarios)"

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
RUN_NOT_COMPLETE_MESSAGE = "The run must complete before starting a comparison."
RUN_ALREADY_PAIRED_MESSAGE = "This run is already part of a comparison."

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

CUSTOM_SCENARIO_NOT_FOUND_MESSAGE = "Unknown custom scenario."
CUSTOM_SCENARIO_FROZEN_MESSAGE = "This custom scenario is frozen and can no longer be edited."
CUSTOM_SCENARIO_NOT_FROZEN_MESSAGE = "This custom scenario must be frozen before it can be run."
CUSTOM_SCENARIO_INVALID_MESSAGE = "The pasted scenario did not pass validation. See issues below."


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
    segment's provider call failed). ``comparison_id`` is set once
    this run has been paired with an opposite-memory-mode alternate
    (either because this run *is* that alternate, or because
    ``POST /api/runs/{run_id}/alternate`` was called on it) -- ``None``
    for a run that has not been paired.
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
    comparison_id: Optional[str] = None


class StartRunRequest(BaseModel):
    scenario_id: str
    # Optional and defaulting to "off" so an older, pre-M5C request
    # body (scenario_id only) still behaves exactly as Memory OFF.
    # Any other value is rejected (422) by this Literal type -- this is
    # the "validate strictly" requirement for M5C.
    memory_mode: Literal["off", "on"] = "off"


class ComparisonSegmentView(BaseModel):
    """One scenario segment, aligned across the OFF and ON conditions.

    ``text`` is the exact scenario text sent in *both* conditions (the
    controlled-pair invariant); only the two assistant responses
    differ. No internal/system/background message is ever included.
    """

    segment_id: str
    role: str
    role_label: str
    text: str
    off_assistant_text: Optional[str] = None
    on_assistant_text: Optional[str] = None


class ComparisonState(BaseModel):
    """Public-safe state of one controlled Memory OFF/ON comparison.

    ``status`` is ``"pending"`` while either run is still in progress,
    ``"ready"`` once both have completed successfully (only then is
    ``segments`` populated), or ``"failed"`` if either run failed --
    never a completed-looking comparison built from an incomplete or
    failed run. Carries no memory payload, hash, artifact path,
    system message, behavioral-use policy text, API key, or any other
    private detail -- only neutral scenario/run metadata and the two
    aligned, already-public transcripts.
    """

    comparison_id: str
    scenario_id: str
    scenario_title: str
    target_model: str
    total_segments: int
    off_run_id: str
    on_run_id: str
    off_completed: bool
    on_completed: bool
    off_failed: bool
    on_failed: bool
    off_error: Optional[str] = None
    on_error: Optional[str] = None
    status: Literal["pending", "ready", "failed"]
    segments: List[ComparisonSegmentView] = []


# -- M5F: Scenario Wizard / Bring Your Own Story -----------------------------


class WizardIngredientsRequest(BaseModel):
    """Plain-language story ingredients from the wizard's ingredient form.

    Deliberately does not include a target-emotion field of any kind
    -- see ``custom_scenario.INGREDIENT_PROMPTS`` for the exact
    questions this mirrors. Every required field must be non-empty;
    ``tone_notes`` is the one optional field.
    """

    protagonist: str = Field(..., min_length=1)
    long_standing_matter: str = Field(..., min_length=1)
    open_possibility: str = Field(..., min_length=1)
    irreversible_change: str = Field(..., min_length=1)
    neutral_event: str = Field(..., min_length=1)
    meaning: str = Field(..., min_length=1)
    relational_pressure: str = Field(..., min_length=1)
    closure: str = Field(..., min_length=1)
    tone_notes: str = ""


class WizardPromptResponse(BaseModel):
    """A single, locally generated, copyable AI-prompt string.

    Nothing else -- no request id, no server-side record of the
    ingredients is kept; generating this prompt makes no network call
    and stores nothing in any registry.
    """

    prompt: str


class ValidationIssueView(BaseModel):
    code: str
    message: str


class CustomScenarioSegmentView(BaseModel):
    role: str
    role_label: str
    text: str


class CreateCustomScenarioRequest(BaseModel):
    """The user's pasted seven-section story, plus an optional title."""

    pasted_text: str = Field(..., min_length=1)
    title: str = ""


class UpdateCustomScenarioSegmentsRequest(BaseModel):
    """A partial edit: only the roles present in ``segments`` change."""

    segments: Dict[str, str] = {}
    title: Optional[str] = None


class CustomScenarioState(BaseModel):
    """Public-safe state of one process-local custom scenario draft.

    Never includes anything beyond what the user themselves supplied
    via paste or edit -- no private SAE data, no memory payload, no
    provider detail. ``segments`` is always all seven roles, in
    ``ROLE_ORDER``, with whatever text the draft currently holds
    (empty string for a role not yet filled in, which should not
    happen given `parse_pasted_scenario`'s all-or-nothing validation,
    but is handled the same safe way regardless). ``runnable_scenario_id``
    is set only once ``frozen`` is true -- the exact id
    ``POST /api/runs`` accepts to run this scenario.
    """

    custom_scenario_id: str
    title: str
    frozen: bool
    valid: bool
    issues: List[ValidationIssueView] = []
    segments: List[CustomScenarioSegmentView] = []
    runnable_scenario_id: Optional[str] = None


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
    # Set once this run has been paired into a comparison (either as
    # the original run an alternate was created from, or as that
    # alternate itself). A run can be paired at most once.
    comparison_id: Optional[str] = None


@dataclass
class _ComparisonEntry:
    """A controlled pair: one Memory OFF run and one Memory ON run of
    the exact same scenario. Deliberately minimal -- no status field
    of its own; status is always derived from the current state of the
    two referenced runs (see ``_comparison_state``), so it can never
    drift out of sync with them.
    """

    comparison_id: str
    scenario_id: str
    off_run_id: str
    on_run_id: str


# Process-local, in-memory only. No database, no disk persistence, no
# writes under .local/ -- a completed or in-progress run's transcript
# is never written to any tracked or runtime-data directory. Cleared
# on every server restart. The lock serializes registry reads/writes
# and per-run mutation (advancing a run, pairing a comparison) against
# concurrent requests within this one process -- it does not attempt
# to solve multi-user or distributed concurrency, which remains
# explicitly out of scope.
_RUN_REGISTRY: Dict[str, _RunEntry] = {}
_COMPARISON_REGISTRY: Dict[str, _ComparisonEntry] = {}
# M5F: process-local custom scenario drafts, keyed by their own
# (unprefixed) draft id -- see `custom_scenario.CustomScenarioDraft`.
# Governed by the exact same lock and the exact same "no database, no
# disk, cleared on restart" invariant as the two registries above.
_CUSTOM_SCENARIO_REGISTRY: Dict[str, CustomScenarioDraft] = {}
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
        comparison_id=entry.comparison_id,
    )


def _custom_scenario_state(draft: CustomScenarioDraft) -> CustomScenarioState:
    report = custom_scenario.validate_segments(draft.segments_by_role)
    return CustomScenarioState(
        custom_scenario_id=draft.custom_scenario_id,
        title=draft.title,
        frozen=draft.frozen,
        valid=report.is_valid,
        issues=[ValidationIssueView(code=issue.code, message=issue.message) for issue in report.issues],
        segments=[
            CustomScenarioSegmentView(role=role, role_label=_role_label(role), text=text)
            for role, text in draft.segments_in_order()
        ],
        runnable_scenario_id=draft.public_scenario_id if draft.frozen else None,
    )


def _resolve_scenario(scenario_id: str) -> Scenario:
    """Resolve a public scenario id to a `Scenario` -- built-in or custom.

    Built-in ids are checked first, exactly as before M5F
    (`BUILTIN_SCENARIOS`, unchanged). A custom scenario id (see
    `custom_scenario.CUSTOM_SCENARIO_ID_PREFIX`,
    `CustomScenarioDraft.public_scenario_id`) is resolved against the
    process-local `_CUSTOM_SCENARIO_REGISTRY`: it must exist and be
    frozen. An unfrozen draft is a 409 (a recognizable, in-progress
    scenario that simply isn't ready to run yet), kept distinct from
    the 404 an unknown id gets, so the frontend can tell the two
    apart. This is the *only* place scenario lookup happens for a run
    -- both a fresh `POST /api/runs` and M5D's
    `POST /api/runs/{run_id}/alternate` resolve a custom scenario
    exactly the same way a built-in one is resolved, through this one
    function, so there is no second run/comparison code path for
    custom scenarios.
    """

    build_fixture = BUILTIN_SCENARIOS.get(scenario_id)
    if build_fixture is not None:
        return build_fixture(mode=MODE_FROZEN)

    custom_id = custom_scenario.parse_public_scenario_id(scenario_id)
    if custom_id is not None:
        draft = _CUSTOM_SCENARIO_REGISTRY.get(custom_id)
        if draft is None:
            raise HTTPException(status_code=404, detail="Unknown scenario.")
        if not draft.frozen:
            raise HTTPException(status_code=409, detail=CUSTOM_SCENARIO_NOT_FROZEN_MESSAGE)
        return custom_scenario.to_scenario(draft)

    raise HTTPException(status_code=404, detail="Unknown scenario.")


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


def _start_run_entry(scenario_id: str, memory_mode: str) -> Tuple[str, _RunEntry]:
    """Build one fresh, unregistered run for ``scenario_id``/``memory_mode``.

    This is the *only* place a run is constructed -- both
    ``POST /api/runs`` (a user-chosen scenario/mode) and
    ``POST /api/runs/{run_id}/alternate`` (M5D's opposite-condition
    replay) call this same function, so there is exactly one code path
    that resolves the provider, resolves memory, and builds the
    initial conversation history. An alternate run therefore always
    gets a completely independent `ScenarioEngine`, `CompatibilityRunner`,
    and `history` -- it never reads or reuses another run's state.

    Raises `HTTPException` exactly as `POST /api/runs` already did:
    404 for an unknown scenario, 409 for a custom scenario that exists
    but is not yet frozen (see `_resolve_scenario`), 503 for a
    missing/broken provider or (Memory ON only) memory configuration.
    """

    scenario = _resolve_scenario(scenario_id)

    # Checked for both Memory OFF and Memory ON -- advancing either
    # condition requires a configured provider, so this is verified
    # up front rather than failing partway through a run.
    provider, model_label = _build_provider()

    memory_payload = None
    memory_payload_sha256 = None
    if memory_mode == MEMORY_ON:
        artifact = _resolve_memory_payload()
        memory_payload = artifact.payload
        memory_payload_sha256 = artifact.content_sha256

    engine = ScenarioEngine(scenario)

    runner = CompatibilityRunner(
        provider,
        model_label=model_label,
        # M5G: resolved once per run from `SAE_DEMO_MAX_TOKENS` (or the
        # built-in default) via the same single function every caller
        # uses -- see `compatibility_runner.resolve_max_tokens`. This
        # call site is shared by every run (`POST /api/runs` and
        # `.../alternate` alike, built-in and custom scenario alike),
        # so Memory OFF and Memory ON always resolve the identical
        # value from the identical environment; nothing here ever
        # varies the budget by condition.
        max_tokens=resolve_max_tokens(),
        memory_payload=memory_payload,
        memory_payload_sha256=memory_payload_sha256,
        # Sent unconditionally, identically, for Memory OFF and Memory
        # ON alike -- never a condition-specific difference. This is
        # the same invariant scripts/run_compatibility.py already
        # relies on, and the one a controlled M5D comparison depends
        # on; see docs/decisions/SAE_DEMO_M4_CONSUMPTION_BOUNDARY_FREEZE.md.
        behavioral_use_policy=DEFAULT_BEHAVIORAL_USE_POLICY,
    )

    try:
        history, _memory_used = runner.build_history()
    except MemoryPayloadIntegrityError:
        raise HTTPException(status_code=503, detail=MEMORY_INTEGRITY_FAILED_MESSAGE) from None

    run_id = uuid.uuid4().hex
    entry = _RunEntry(
        engine=engine,
        scenario_key=scenario_id,
        memory_mode=memory_mode,
        runner=runner,
        history=history,
    )
    return run_id, entry


def _comparison_state(comparison: _ComparisonEntry) -> ComparisonState:
    off_entry = _RUN_REGISTRY[comparison.off_run_id]
    on_entry = _RUN_REGISTRY[comparison.on_run_id]

    off_completed = off_entry.engine.is_complete and not off_entry.failed
    on_completed = on_entry.engine.is_complete and not on_entry.failed

    status: Literal["pending", "ready", "failed"]
    if off_entry.failed or on_entry.failed:
        status = "failed"
    elif off_completed and on_completed:
        status = "ready"
    else:
        status = "pending"

    segments: List[ComparisonSegmentView] = []
    if status == "ready":
        # Both runs replay the exact same scenario id through the same
        # _start_run_entry path, so their segment order/text are
        # identical by construction -- the OFF run's own trace is used
        # as the shared, canonical segment list for both columns.
        off_trace = off_entry.engine.run_trace()
        off_turns_by_segment = {turn.segment_id: turn for turn in off_entry.turns}
        on_turns_by_segment = {turn.segment_id: turn for turn in on_entry.turns}

        for record in off_trace.sent_segments:
            off_turn = off_turns_by_segment.get(record.segment_id)
            on_turn = on_turns_by_segment.get(record.segment_id)
            segments.append(
                ComparisonSegmentView(
                    segment_id=record.segment_id,
                    role=record.role,
                    role_label=_role_label(record.role),
                    text=record.text_sent,
                    off_assistant_text=off_turn.assistant_text if off_turn else None,
                    on_assistant_text=on_turn.assistant_text if on_turn else None,
                )
            )

    return ComparisonState(
        comparison_id=comparison.comparison_id,
        scenario_id=comparison.scenario_id,
        scenario_title=off_entry.engine.run_trace().scenario_title,
        target_model=DEFAULT_NEBIUS_MODEL,
        total_segments=len(off_entry.engine.run_trace().segment_order),
        off_run_id=comparison.off_run_id,
        on_run_id=comparison.on_run_id,
        off_completed=off_completed,
        on_completed=on_completed,
        off_failed=off_entry.failed,
        on_failed=on_entry.failed,
        off_error=off_entry.error,
        on_error=on_entry.error,
        status=status,
        segments=segments,
    )


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


# -- M5F: Scenario Wizard / Bring Your Own Story -----------------------------


@app.post("/api/scenario-wizard/prompt", response_model=WizardPromptResponse)
def generate_wizard_prompt(payload: WizardIngredientsRequest) -> WizardPromptResponse:
    """Locally generate one copyable AI prompt from plain-language ingredients.

    No provider is constructed and no network call is made here -- the
    ingredients are used only to build the returned prompt string, and
    nothing about this request is stored in any registry. The user
    copies the returned prompt to an AI service of their own choosing;
    SAE-DEMO never sends the ingredients or the prompt anywhere itself.
    """

    prompt = custom_scenario.generate_prompt(payload.model_dump())
    return WizardPromptResponse(prompt=prompt)


@app.post("/api/custom-scenarios", response_model=CustomScenarioState, status_code=201)
def create_custom_scenario(payload: CreateCustomScenarioRequest) -> CustomScenarioState:
    """Parse a pasted seven-section story into a new, unfrozen draft.

    Merges Part C (parse/validate) and the draft-creation step into
    one call: an invalid paste creates nothing and returns a 422 with
    the full validation report so the user can fix and resubmit the
    pasted text; only a fully valid seven-section paste creates a
    draft. No provider is constructed and no memory artifact is
    touched to do this.
    """

    result = parse_pasted_scenario(payload.pasted_text)
    if not result.is_valid:
        raise HTTPException(
            status_code=422,
            detail={
                "message": CUSTOM_SCENARIO_INVALID_MESSAGE,
                "issues": [
                    {"code": issue.code, "message": issue.message} for issue in result.report.issues
                ],
            },
        )

    draft = custom_scenario.new_draft(result.segments_by_role, title=payload.title)
    with _REGISTRY_LOCK:
        _CUSTOM_SCENARIO_REGISTRY[draft.custom_scenario_id] = draft

    return _custom_scenario_state(draft)


@app.get("/api/custom-scenarios/{custom_scenario_id}", response_model=CustomScenarioState)
def get_custom_scenario(custom_scenario_id: str) -> CustomScenarioState:
    draft = _CUSTOM_SCENARIO_REGISTRY.get(custom_scenario_id)
    if draft is None:
        raise HTTPException(status_code=404, detail=CUSTOM_SCENARIO_NOT_FOUND_MESSAGE)
    return _custom_scenario_state(draft)


@app.patch("/api/custom-scenarios/{custom_scenario_id}", response_model=CustomScenarioState)
def update_custom_scenario(
    custom_scenario_id: str, payload: UpdateCustomScenarioSegmentsRequest
) -> CustomScenarioState:
    """Edit one or more segments (and/or the title) of an unfrozen draft.

    Refuses (409) once the draft is frozen -- "once frozen for a
    controlled comparison, the scenario becomes immutable" -- rather
    than silently accepting or ignoring the edit.
    """

    with _REGISTRY_LOCK:
        draft = _CUSTOM_SCENARIO_REGISTRY.get(custom_scenario_id)
        if draft is None:
            raise HTTPException(status_code=404, detail=CUSTOM_SCENARIO_NOT_FOUND_MESSAGE)
        if draft.frozen:
            raise HTTPException(status_code=409, detail=CUSTOM_SCENARIO_FROZEN_MESSAGE)

        for role, text in payload.segments.items():
            if role not in VALID_SEMANTIC_ROLES:
                raise HTTPException(status_code=422, detail=f"Unknown semantic role '{role}'.")
            draft.segments_by_role[role] = text

        if payload.title is not None:
            draft.title = payload.title.strip() or custom_scenario.DEFAULT_DRAFT_TITLE

        return _custom_scenario_state(draft)


@app.post("/api/custom-scenarios/{custom_scenario_id}/freeze", response_model=CustomScenarioState)
def freeze_custom_scenario(custom_scenario_id: str) -> CustomScenarioState:
    """Validate and freeze a draft so it can be run.

    Refuses (409) if already frozen. Otherwise validates all seven
    segments; on success the draft becomes immutable and its
    ``runnable_scenario_id`` becomes available to ``POST /api/runs``,
    exactly like a built-in scenario id. On failure, returns 422 with
    the validation report and leaves the draft unfrozen and editable.
    """

    with _REGISTRY_LOCK:
        draft = _CUSTOM_SCENARIO_REGISTRY.get(custom_scenario_id)
        if draft is None:
            raise HTTPException(status_code=404, detail=CUSTOM_SCENARIO_NOT_FOUND_MESSAGE)
        if draft.frozen:
            raise HTTPException(status_code=409, detail=CUSTOM_SCENARIO_FROZEN_MESSAGE)

        report = custom_scenario.freeze_draft(draft)
        if not report.is_valid:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": CUSTOM_SCENARIO_INVALID_MESSAGE,
                    "issues": [
                        {"code": issue.code, "message": issue.message} for issue in report.issues
                    ],
                },
            )

        return _custom_scenario_state(draft)


@app.post("/api/runs", response_model=RunState, status_code=201)
def start_run(payload: StartRunRequest) -> RunState:
    run_id, entry = _start_run_entry(payload.scenario_id, payload.memory_mode)

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


@app.post("/api/runs/{run_id}/alternate", response_model=RunState, status_code=201)
def create_alternate_run(run_id: str) -> RunState:
    """Start a fresh, opposite-memory-mode run of the same scenario.

    This is M5D's controlled-comparison entry point. The alternate run
    is built by `_start_run_entry` -- the exact same construction path
    `POST /api/runs` uses -- so it gets a completely independent
    engine/runner/history; nothing from the original run's
    conversation is carried over. The original run must already be
    completed (not merely in progress, and not failed) and must not
    already be part of another comparison; a comparison, once formed,
    always pairs exactly one Memory OFF run with exactly one Memory ON
    run of the same scenario id.
    """

    with _REGISTRY_LOCK:
        original = _RUN_REGISTRY.get(run_id)
        if original is None:
            raise HTTPException(status_code=404, detail="Unknown run.")
        if original.comparison_id is not None:
            raise HTTPException(status_code=409, detail=RUN_ALREADY_PAIRED_MESSAGE)
        if original.failed or not original.engine.is_complete:
            raise HTTPException(status_code=409, detail=RUN_NOT_COMPLETE_MESSAGE)

        alternate_mode = MEMORY_OFF if original.memory_mode == MEMORY_ON else MEMORY_ON
        new_run_id, new_entry = _start_run_entry(original.scenario_key, alternate_mode)

        comparison_id = uuid.uuid4().hex
        if original.memory_mode == MEMORY_OFF:
            off_run_id, on_run_id = run_id, new_run_id
        else:
            off_run_id, on_run_id = new_run_id, run_id

        _COMPARISON_REGISTRY[comparison_id] = _ComparisonEntry(
            comparison_id=comparison_id,
            scenario_id=original.scenario_key,
            off_run_id=off_run_id,
            on_run_id=on_run_id,
        )
        original.comparison_id = comparison_id
        new_entry.comparison_id = comparison_id
        _RUN_REGISTRY[new_run_id] = new_entry

    return _run_state(new_run_id, new_entry)


@app.get("/api/comparisons/{comparison_id}", response_model=ComparisonState)
def get_comparison(comparison_id: str) -> ComparisonState:
    comparison = _COMPARISON_REGISTRY.get(comparison_id)
    if comparison is None:
        raise HTTPException(status_code=404, detail="Unknown comparison.")
    return _comparison_state(comparison)


@app.get("/")
def root() -> FileResponse:
    return FileResponse(INDEX_HTML_PATH)


# Serves styles.css / app.js (and any future static asset) under /static/*.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
