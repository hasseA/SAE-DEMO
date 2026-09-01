"""Minimal FastAPI web shell for SAE-DEMO (M5A).

This module serves the static frontend and exposes a small, typed
health/status API only. It does not make provider calls, does not
load or access any Emotional Memory artifact, does not execute a
scenario, and does not implement Memory OFF/ON or comparison logic --
those are out of scope for M5A and land in later M5 stages (see
``docs/M5_DEMO_SPEC.md``).

``/api/status`` intentionally returns only public-safe, demo-safe
fields: whether a provider API key is present (as a boolean only,
never its value), a public model identifier, and static feature-status
labels. It never reads or returns ``.env`` contents, filesystem paths,
memory artifact names/paths, or anything from the private SAE
repository.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import DEFAULT_NEBIUS_MODEL

APP_NAME = "SAE-DEMO"
STAGE_LABEL = "M5A"
NOT_ACTIVE_LABEL = "not active in M5A"

STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_HTML_PATH = STATIC_DIR / "index.html"


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
        memory_feature_status=NOT_ACTIVE_LABEL,
        scenario_feature_status=NOT_ACTIVE_LABEL,
    )


@app.get("/")
def root() -> FileResponse:
    return FileResponse(INDEX_HTML_PATH)


# Serves styles.css / app.js (and any future static asset) under /static/*.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
