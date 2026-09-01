"""Backend-first, in-memory scenario engine for SAE-DEMO.

Loads a validated `Scenario`, exposes/advances through its segments one
at a time, supports optional editing of not-yet-sent segments in
interactive mode, and records a neutral run trace of exactly what text
was sent. This engine is independent of any model provider: attaching
a model response happens after the fact via `record_model_response`,
so no provider or network code is imported here.

No emotional scoring or SAE scientific interpretation is performed —
this module only tracks structural run state.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Set, Tuple

from .scenario import MODE_FROZEN, Scenario, ScenarioSegment, ValidationReport, validate_scenario


class ScenarioEngineError(RuntimeError):
    """Base class for scenario-engine runtime errors."""


class ScenarioValidationError(ScenarioEngineError):
    """Raised when a scenario fails validation and cannot be loaded."""

    def __init__(self, report: ValidationReport):
        self.report = report
        message = "; ".join(issue.message for issue in report.issues) or (
            "Scenario failed validation."
        )
        super().__init__(message)


class FrozenRunEditError(ScenarioEngineError):
    """Raised when an edit is attempted on a frozen-mode run."""


class SegmentAlreadySentError(ScenarioEngineError):
    """Raised when an edit targets a segment that has already been sent."""


class SegmentNotEditableError(ScenarioEngineError):
    """Raised when an edit targets a segment marked non-editable."""


class UnknownSegmentError(ScenarioEngineError):
    """Raised when a referenced segment id does not exist in this run."""


class NoMoreSegmentsError(ScenarioEngineError):
    """Raised when previewing/advancing past the final segment."""


@dataclass(frozen=True)
class Revision:
    """One edit applied to a not-yet-sent segment.

    `revision_sequence` is a run-local, monotonically increasing
    integer (not a wall-clock timestamp) so ordering is deterministic
    and testable without depending on time.
    """

    segment_id: str
    original_text: str
    revised_text: str
    revision_sequence: int


@dataclass(frozen=True)
class SentSegmentRecord:
    """The exact text sent for one segment, plus its provenance."""

    segment_id: str
    role: str
    original_text: str
    text_sent: str
    was_edited: bool
    model_response: Optional[str] = None


@dataclass(frozen=True)
class RunTrace:
    """A neutral, replayable record of a scenario run.

    Contains no emotional scoring or interpretation — only scenario
    identity, mode, segment order, and exactly what text was sent for
    each segment (plus any revisions and any attached model response).
    """

    scenario_id: str
    scenario_title: str
    mode: str
    segment_order: Tuple[str, ...]
    sent_segments: Tuple[SentSegmentRecord, ...]
    revisions: Tuple[Revision, ...]


class ScenarioEngine:
    """Loads one validated scenario and runs it, segment by segment."""

    def __init__(self, scenario: Scenario):
        report = validate_scenario(scenario)
        if not report.is_valid:
            raise ScenarioValidationError(report)

        self._scenario = scenario
        self._position = 0
        self._sent: List[SentSegmentRecord] = []
        self._revisions: List[Revision] = []
        self._current_text: Dict[str, str] = {
            segment.segment_id: segment.text for segment in scenario.segments
        }
        self._sent_ids: Set[str] = set()

    # -- read-only accessors -------------------------------------------------

    @property
    def scenario(self) -> Scenario:
        return self._scenario

    @property
    def mode(self) -> str:
        return self._scenario.mode

    @property
    def is_complete(self) -> bool:
        return self._position >= len(self._scenario.segments)

    def original_text(self, segment_id: str) -> str:
        return self._segment_by_id(segment_id).text

    # -- traversal ---------------------------------------------------------

    def preview_next_segment(self) -> ScenarioSegment:
        """Return the next unsent segment, reflecting any edit applied to it.

        Does not advance run position or mark anything as sent.
        """

        if self.is_complete:
            raise NoMoreSegmentsError(
                "No more segments: the scenario has already been fully advanced."
            )

        segment = self._scenario.segments[self._position]
        current_text = self._current_text[segment.segment_id]
        return replace(segment, text=current_text)

    def advance(self) -> SentSegmentRecord:
        """Send the next segment, using its current (possibly edited) text."""

        segment = self.preview_next_segment()
        original = self.original_text(segment.segment_id)
        record = SentSegmentRecord(
            segment_id=segment.segment_id,
            role=segment.role,
            original_text=original,
            text_sent=segment.text,
            was_edited=segment.text != original,
            model_response=None,
        )
        self._sent.append(record)
        self._sent_ids.add(segment.segment_id)
        self._position += 1
        return record

    # -- editing (interactive mode only) ------------------------------------

    def edit_upcoming_segment(self, segment_id: str, new_text: str) -> Revision:
        """Edit a not-yet-sent segment's text before it is sent.

        Allowed only in interactive mode, only for a segment that has
        not already been sent, and only if the segment itself is
        marked editable.
        """

        if self.mode == MODE_FROZEN:
            raise FrozenRunEditError("Cannot edit segments in a frozen-mode run.")

        if segment_id in self._sent_ids:
            raise SegmentAlreadySentError(
                f"Segment '{segment_id}' has already been sent and cannot be edited."
            )

        segment = self._segment_by_id(segment_id)
        if not segment.editable:
            raise SegmentNotEditableError(f"Segment '{segment_id}' is marked non-editable.")

        if not new_text.strip():
            raise ValueError("Revised segment text must not be empty.")

        revision_sequence = len(self._revisions) + 1
        revision = Revision(
            segment_id=segment_id,
            original_text=segment.text,
            revised_text=new_text,
            revision_sequence=revision_sequence,
        )
        self._revisions.append(revision)
        self._current_text[segment_id] = new_text
        return revision

    def _segment_by_id(self, segment_id: str) -> ScenarioSegment:
        for segment in self._scenario.segments:
            if segment.segment_id == segment_id:
                return segment
        raise UnknownSegmentError(f"No segment with id '{segment_id}' in this scenario.")

    # -- model response attachment (decoupled from any provider) -----------

    def record_model_response(self, segment_id: str, response_text: str) -> SentSegmentRecord:
        """Attach a model response to an already-sent segment's record.

        The engine never calls a provider itself; a caller sends the
        segment text elsewhere and reports the result back here.
        """

        for index, record in enumerate(self._sent):
            if record.segment_id == segment_id:
                updated = replace(record, model_response=response_text)
                self._sent[index] = updated
                return updated
        raise UnknownSegmentError(f"Segment '{segment_id}' has not been sent yet in this run.")

    # -- run trace -----------------------------------------------------------

    def run_trace(self) -> RunTrace:
        return RunTrace(
            scenario_id=self._scenario.scenario_id,
            scenario_title=self._scenario.title,
            mode=self._scenario.mode,
            segment_order=tuple(segment.segment_id for segment in self._scenario.segments),
            sent_segments=tuple(self._sent),
            revisions=tuple(self._revisions),
        )
