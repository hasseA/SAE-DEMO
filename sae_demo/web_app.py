"""Minimal FastAPI web shell for SAE-DEMO (M5A, extended in M5B).

This module serves the static frontend and exposes a small, typed
API. M5A added a health/status API only. M5B adds a scenario-run API
that wires the existing, unchanged ``ScenarioEngine`` into the web
app: listing the two built-in clean-room synthetic fixtures, starting
an in-memory ``frozen``-mode run, and advancing it one segment at a
time.

M5B does not make any provider call, does not load or access any
Emotional Memory artifact, and does not implement Memory OFF/ON or
comparison logic -- those remain out of scope and land in later M5
stages (see ``docs/M5_DEMO_SPEC.md``). Every scenario run in this
module is Memory OFF; the frontend labels each segment's response area
as "Model response will appear in M5C" rather than showing any real or
simulated model output.

Run state lives only in a process-local, in-memory registry (a plain
dict guarded by a lock) -- there is no database and nothing is written
to disk. A server restart clears all runs, and this registry is not a
solution for multi-user or distributed concurrency; it only keeps
concurrent requests inside this one process from corrupting a single
run's state.

``/api/status`` and the scenario endpoints intentionally return only
public-safe, demo-safe fields. Scenario summaries and run state expose
the existing, generic, public-safe semantic-role vocabulary already
used by ``sae_demo/scenario.py`` and the two synthetic fixtures
already used by ``scripts/run_compatibility.py`` and the offline test
suite -- nothing from the private SAE repository, no private artifact
paths, and no API key value ever appears in a response.
"""

from __future__ import annotations

import os
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import DEFAULT_NEBIUS_MODEL
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
STAGE_LABEL = "M5B"
MEMORY_FEATURE_STATUS = "not active in M5B"
SCENARIO_FEATURE_STATUS = "active in M5B (Memory OFF only)"

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
    """One scenario segment as shown to the web UI.

    ``role`` is the existing generic semantic-role key; ``role_label``
    is its public-safe human-readable form (see ``ROLE_LABELS``).
    """

    segment_id: str
    role: str
    role_label: str
    text: str


class RunState(BaseModel):
    """Full state of one in-memory scenario run.

    ``current_segment`` is the next not-yet-sent segment (``None``
    once the run is complete). ``transcript`` holds only segments
    already sent. Neither this model nor any handler that builds it
    ever includes a model response -- M5B makes no provider call.
    """

    run_id: str
    scenario_id: str
    scenario_title: str
    mode: str
    total_segments: int
    current_segment_number: int
    completed: bool
    current_segment: Optional[SegmentView] = None
    transcript: List[SegmentView] = []


class StartRunRequest(BaseModel):
    scenario_id: str


@dataclass
class _RunEntry:
    engine: ScenarioEngine
    scenario_key: str


# Process-local, in-memory only. No database, no disk persistence, no
# writes under .local/. Cleared on every server restart. The lock
# serializes registry reads/writes and per-run mutation (advancing a
# run) against concurrent requests within this one process -- it does
# not attempt to solve multi-user or distributed concurrency, which is
# explicitly out of scope for M5B.
_RUN_REGISTRY: Dict[str, _RunEntry] = {}
_REGISTRY_LOCK = threading.Lock()


def _segment_view(segment) -> SegmentView:
    return SegmentView(
        segment_id=segment.segment_id,
        role=segment.role,
        role_label=_role_label(segment.role),
        text=segment.text,
    )


def _segment_view_from_record(record: SentSegmentRecord) -> SegmentView:
    return SegmentView(
        segment_id=record.segment_id,
        role=record.role,
        role_label=_role_label(record.role),
        text=record.text_sent,
    )


def _run_state(run_id: str, entry: _RunEntry) -> RunState:
    engine = entry.engine
    trace = engine.run_trace()
    transcript = [_segment_view_from_record(record) for record in trace.sent_segments]
    total_segments = len(trace.segment_order)
    completed = engine.is_complete

    if completed:
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
        total_segments=total_segments,
        current_segment_number=current_segment_number,
        completed=completed,
        current_segment=current_segment,
        transcript=transcript,
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


@app.post("/api/runs", response_model=RunState, status_code=201)
def start_run(payload: StartRunRequest) -> RunState:
    build_fixture = BUILTIN_SCENARIOS.get(payload.scenario_id)
    if build_fixture is None:
        raise HTTPException(status_code=404, detail="Unknown scenario.")

    scenario = build_fixture(mode=MODE_FROZEN)
    engine = ScenarioEngine(scenario)
    run_id = uuid.uuid4().hex

    with _REGISTRY_LOCK:
        entry = _RunEntry(engine=engine, scenario_key=payload.scenario_id)
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
        if entry.engine.is_complete:
            raise HTTPException(status_code=409, detail="Run already completed.")
        try:
            entry.engine.advance()
        except NoMoreSegmentsError as exc:  # pragma: no cover - defensive
            raise HTTPException(status_code=409, detail="Run already completed.") from exc

    return _run_state(run_id, entry)


@app.get("/")
def root() -> FileResponse:
    return FileResponse(INDEX_HTML_PATH)


# Serves styles.css / app.js (and any future static asset) under /static/*.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
